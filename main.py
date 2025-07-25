import json
import os
import logging
import time
from dotenv import load_dotenv
from fastmcp import FastMCP

# Gerekli kütüphaneler
import google.generativeai as genai
from pytube import YouTube

# 1. TEMEL KURULUM
# -----------------------------------------------------------------------------
# .env dosyasındaki ortam değişkenlerini yükle
load_dotenv()

# Logger yapılandırması - Daha detaylı logging için DEBUG seviyesi
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s')

# FastMCP sunucusunu başlat
mcp = FastMCP(
    "Eğitim Araçları",
    include_tags={"public"},
    exclude_tags={"private", "beta"}
)

logging.info("FastMCP sunucusu başlatıldı")

# 2. UZMAN AGENT (GEMINI API) YAPILANDIRMASI
# -----------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logging.error("GEMINI_API_KEY bulunamadı. Lütfen .env dosyasını kontrol edin.")
    # Uygulamanın başlamasını engelleyebilirsiniz veya sadece uyarı verebilirsiniz.
    exit() 
else:
    genai.configure(api_key=GEMINI_API_KEY)
    logging.info("Gemini API başarıyla yapılandırıldı")


# 3. ÇEKİRDEK İŞ MANTIĞI (TOOL'DAN AYRI)
# -----------------------------------------------------------------------------
# Bu en iyi pratiktir: Asıl işi yapan mantığı ayrı bir fonksiyona koymak,
# tool'un kendisini test edilebilir ve yeniden kullanılabilir kılar.
def _videoyu_ozetle_logic(video_url: str = "", video_dosyasi_yolu: str = "") -> str:
    """Video özetlemenin tüm çekirdek mantığını içeren, test edilebilir fonksiyon."""
    logging.info("Video özetleme işlemi başlatıldı")
    logging.debug(f"Gelen parametreler - video_url: {video_url}, video_dosyasi_yolu: {video_dosyasi_yolu}")
    
    if not video_url and not video_dosyasi_yolu:
        logging.warning("Ne video URL'i ne de dosya yolu sağlanmadı")
        return json.dumps({"durum": "Hata", "mesaj": "Bir video URL'i veya dosya yolu sağlamalısınız."}, ensure_ascii=False)

    video_path = None
    temp_dosya = False

    try:
        if video_url:
            logging.info(f"Video URL'i işleniyor: {video_url}")
            if "youtube.com" in video_url or "youtu.be" in video_url:
                logging.info("YouTube videosu tespit edildi, indirme başlıyor...")
                
                # YouTube nesnesi oluşturma ve hata yönetimi
                try:
                    yt = YouTube(video_url)
                    # Önce video erişilebilirlik kontrolü yapalım
                    video_title = yt.title  # Bu satır hata verirse video erişilemez
                    video_length = yt.length
                    logging.debug(f"Video başlığı: {video_title}")
                    logging.debug(f"Video uzunluğu: {video_length} saniye")
                except Exception as yt_error:
                    logging.error(f"YouTube video erişim hatası: {str(yt_error)}")
                    if "400" in str(yt_error):
                        return json.dumps({"durum": "Hata", "mesaj": "Video erişilemiyor. Video yaş kısıtlamalı, özel veya bölgede engelli olabilir."}, ensure_ascii=False)
                    elif "403" in str(yt_error):
                        return json.dumps({"durum": "Hata", "mesaj": "Video erişim izni yok. Video telif hakkı korumalı olabilir."}, ensure_ascii=False)
                    else:
                        return json.dumps({"durum": "Hata", "mesaj": f"YouTube video yüklenirken hata: {str(yt_error)}"}, ensure_ascii=False)
                
                # Video stream'ini alma
                try:
                    stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
                    if not stream:
                        # Alternatif stream arama
                        stream = yt.streams.filter(file_extension='mp4').first()
                        if not stream:
                            logging.error("Hiçbir uygun video akışı bulunamadı")
                            return json.dumps({"durum": "Hata", "mesaj": "Video indirilebilir bir formatta değil."}, ensure_ascii=False)
                    
                    logging.info(f"Stream seçildi: {stream.resolution}, boyut: {stream.filesize} bytes")
                    
                    # Dosya boyutu kontrolü (örn: 100MB sınırı)
                    if stream.filesize and stream.filesize > 100 * 1024 * 1024:  # 100MB
                        logging.warning(f"Video çok büyük: {stream.filesize} bytes")
                        return json.dumps({"durum": "Hata", "mesaj": "Video dosyası çok büyük (100MB sınırı). Daha kısa bir video deneyin."}, ensure_ascii=False)
                        
                except Exception as stream_error:
                    logging.error(f"Video stream alma hatası: {str(stream_error)}")
                    return json.dumps({"durum": "Hata", "mesaj": f"Video stream bilgisi alınamadı: {str(stream_error)}"}, ensure_ascii=False)
                
                # İndirme dizini hazırlama
                temp_dir = "/tmp/video_downloads"
                try:
                    os.makedirs(temp_dir, exist_ok=True)
                    logging.debug(f"Geçici dizin oluşturuldu: {temp_dir}")
                except Exception as dir_error:
                    logging.error(f"Geçici dizin oluşturma hatası: {str(dir_error)}")
                    return json.dumps({"durum": "Hata", "mesaj": "Geçici dosya dizini oluşturulamadı."}, ensure_ascii=False)
                
                # Video indirme
                try:
                    logging.info("Video indirme başlıyor...")
                    video_path = stream.download(output_path=temp_dir)
                    logging.info(f"YouTube videosu başarıyla indirildi: {video_path}")
                    logging.debug(f"İndirilen dosya boyutu: {os.path.getsize(video_path)} bytes")
                    temp_dosya = True
                except Exception as download_error:
                    logging.error(f"Video indirme hatası: {str(download_error)}")
                    return json.dumps({"durum": "Hata", "mesaj": f"Video indirilemedi: {str(download_error)}"}, ensure_ascii=False)
                    
            else:
                logging.error("Desteklenmeyen video URL formatı")
                return json.dumps({"durum": "Hata", "mesaj": "Şu anda sadece YouTube videoları desteklenmektedir."}, ensure_ascii=False)

        elif video_dosyasi_yolu:
            logging.info(f"Yerel video dosyası işleniyor: {video_dosyasi_yolu}")
            if not os.path.exists(video_dosyasi_yolu):
                logging.error(f"Dosya bulunamadı: {video_dosyasi_yolu}")
                return json.dumps({"durum": "Hata", "mesaj": f"Dosya yolu bulunamadı: {video_dosyasi_yolu}"}, ensure_ascii=False)
            video_path = video_dosyasi_yolu
            logging.debug(f"Yerel dosya boyutu: {os.path.getsize(video_path)} bytes")

        # Gemini API'ye yükleme
        try:
            logging.info(f"Video Gemini API'ye yükleniyor: {video_path}")
            video_file = genai.upload_file(path=video_path, mime_type="video/mp4")
            logging.info(f"Yükleme başladı: {video_file.name}. İşlenmesi bekleniyor...")
            logging.debug(f"Video dosyası durumu: {video_file.state.name}")
        except Exception as upload_error:
            logging.error(f"Gemini API yükleme hatası: {str(upload_error)}")
            return json.dumps({"durum": "Hata", "mesaj": f"Video Gemini API'ye yüklenemedi: {str(upload_error)}"}, ensure_ascii=False)

        # Video işleme bekleme
        progress_counter = 0
        max_wait_time = 120  # 2 dakika maksimum bekleme
        while video_file.state.name == "PROCESSING" and progress_counter < max_wait_time // 5:
            progress_counter += 1
            print('.', end='', flush=True)
            logging.debug(f"İşleme devam ediyor... ({progress_counter * 5} saniye geçti)")
            time.sleep(5)
            video_file = genai.get_file(video_file.name)

        print()  # Satır sonu için
        logging.info(f"Video işleme tamamlandı. Final durumu: {video_file.state.name}")

        if video_file.state.name == "FAILED":
            logging.error(f"Video yüklemesi başarısız oldu: {video_file.error}")
            return json.dumps({"durum": "Hata", "mesaj": f"Video işleme başarısız: {video_file.error}"}, ensure_ascii=False)
        
        if video_file.state.name == "PROCESSING":
            logging.error("Video işleme zaman aşımına uğradı")
            return json.dumps({"durum": "Hata", "mesaj": "Video işleme çok uzun sürdü. Daha kısa bir video deneyin."}, ensure_ascii=False)

        # AI özet oluşturma
        try:
            logging.info("Video başarıyla işlendi. AI özet oluşturma başlıyor...")
            model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
            logging.debug("Gemini model oluşturuldu")
            
            prompt = """
            Bu videoyu bir öğrenciye ders anlatır gibi analiz et. Aşağıdaki formatta bir özet çıkar:
            1. **Ana Fikir:** Videonun tek cümlelik özeti.
            2. **Kilit Öğrenme Noktaları:** Maddeler halinde en önemli 3-5 öğrenme çıktısı.
            3. **Detaylı Özet:** Videonun içeriğini paragraflar halinde, anlaşılır bir dille açıkla.
            4. **İlgili Konular:** Videodaki konularla bağlantılı, öğrencinin araştırabileceği 3 ek konu öner.
            """
            
            logging.info("AI'dan özet isteniyor...")
            response = model.generate_content([prompt, video_file])
            logging.info("AI özeti başarıyla oluşturuldu")
            logging.debug(f"Özet uzunluğu: {len(response.text)} karakter")
        except Exception as ai_error:
            logging.error(f"AI özet oluşturma hatası: {str(ai_error)}")
            return json.dumps({"durum": "Hata", "mesaj": f"AI özet oluşturulamadı: {str(ai_error)}"}, ensure_ascii=False)

        # Temizlik
        try:
            logging.info("Yüklenen video dosyası API'den siliniyor...")
            genai.delete_file(video_file.name)
            logging.info(f"Yüklenen dosya ({video_file.name}) API'den başarıyla silindi")
        except Exception as delete_error:
            logging.warning(f"API'den dosya silme hatası: {str(delete_error)}")

        logging.info("Video özetleme işlemi başarıyla tamamlandı")
        return json.dumps({"durum": "Başarılı", "ozet": response.text}, ensure_ascii=False)

    except Exception as e:
        logging.error(f"Beklenmeyen hata: {str(e)}", exc_info=True)
        logging.debug(f"Hata türü: {type(e).__name__}")
        return json.dumps({"durum": "Hata", "mesaj": f"Beklenmeyen bir hata oluştu: {str(e)}"}, ensure_ascii=False)

    finally:
        if temp_dosya and video_path and os.path.exists(video_path):
            try:
                logging.info(f"Geçici video dosyası siliniyor: {video_path}")
                os.remove(video_path)
                logging.info("Geçici video dosyası başarıyla silindi")
            except Exception as e:
                logging.error(f"Geçici dosya silinirken hata: {e}")


# 4. TOOL TANIMLAMASI
# -----------------------------------------------------------------------------
@mcp.tool(tags={"public"})
def videoyu_ozetle(video_url: str = "", video_dosyasi_yolu: str = "") -> str:
    """
    VIDEO ÖZETLEME AJANI - Verilen bir videonun içeriğini eğitim odaklı olarak metin formatında özetler.

    Kullanıcı "bu videoyu özetle", "videodaki önemli noktalar neler?" veya bir video linki paylaştığında bu aracı kullan.

    Args:
        video_url (str): Özetlenecek videonun YouTube linki.
        video_dosyasi_yolu (str): (Opsiyonel) Sunucuda bulunan bir video dosyasının yolu.
    
    Returns:
        str: Videonun özetini içeren bir JSON string'i.
    """
    logging.info("videoyu_ozetle tool'u çağrıldı")
    # Bu fonksiyon, asıl işi yapan logic fonksiyonunu çağırır.
    return _videoyu_ozetle_logic(video_url=video_url, video_dosyasi_yolu=video_dosyasi_yolu)


# 5. MCP SUNUCUSUNU BAŞLATMA
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    logging.info("--- Eğitim Asistanı MCP Sunucusu Başlatılıyor ---")
    print("--- Eğitim Asistanı MCP Sunucusu Başlatılıyor ---")
    print("MCP sunucusu çalışıyor...")
    print("Sunucuyu durdurmak için: CTRL+C")
    logging.info("MCP sunucusu başlatılıyor...")
    
    # FastMCP sunucusunu çalıştır
    mcp.run(transport="streamable-http",host="0.0.0.0", port=8000)