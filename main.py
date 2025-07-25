import json
import os
import logging
import time
from dotenv import load_dotenv
from fastmcp import FastMCP
import yt_dlp
import re

# Gerekli kütüphaneler
import google.generativeai as genai

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

def video_indir(url, indirme_yolu="./indirilmis_videolar"):
    """
    YouTube'dan video indiren basit fonksiyon - yt-dlp kullanarak düşük kalitede indirme öncelikli
    
    Args:
        url (str): YouTube video URL'si
        indirme_yolu (str): Videonun indirileceği klasör yolu
    
    Returns:
        str: İndirilen dosyanın tam yolu veya hata mesajı
    """
    try:
        # İndirme klasörünü oluştur
        os.makedirs(indirme_yolu, exist_ok=True)
        
        print(f"Video URL'si: {url}")
        
        # yt-dlp seçenekleri - düşük kalite öncelikli
        ydl_opts = {
            'format': 'worst[ext=mp4]/worst',  # En düşük kalite mp4, yoksa en düşük kalite
            'outtmpl': os.path.join(indirme_yolu, '%(title)s.%(ext)s'),  # Çıktı dosya formatı
            'quiet': False,  # Detaylı çıktı
            'no_warnings': False,
            'extractaudio': False,  # Sadece video
            'writeinfojson': False,  # Info dosyası yazma
            'writethumbnail': False,  # Thumbnail yazma
        }
        
        print("Video bilgileri alınıyor...")
        
        # Video bilgilerini al
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            print(f"Video başlığı: {info.get('title', 'Bilinmiyor')}")
            print(f"Kanal: {info.get('uploader', 'Bilinmiyor')}")
            print(f"Süre: {info.get('duration', 0)} saniye")
            print(f"Görüntülenme: {info.get('view_count', 0)}")
        
        print("Video indiriliyor (düşük kalite)...")
        
        # Videoyu indir
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # İndirilen dosyayı bul
        # Dosya adını güvenli hale getir (yt-dlp otomatik yapar ama kontrol edelim)
        guvenli_baslik = re.sub(r'[<>:"/\\|?*]', '_', info.get('title', 'video'))
        
        # Olası dosya uzantıları
        olasi_uzantilar = ['.mp4', '.webm', '.mkv', '.flv']
        indirilen_dosya = None
        
        for uzanti in olasi_uzantilar:
            dosya_yolu = os.path.join(indirme_yolu, f"{guvenli_baslik}{uzanti}")
            if os.path.exists(dosya_yolu):
                indirilen_dosya = dosya_yolu
                break
        
        # Eğer tam eşleşme bulunamazsa, klasördeki en son eklenen dosyayı bul
        if not indirilen_dosya:
            try:
                dosyalar = [f for f in os.listdir(indirme_yolu) if os.path.isfile(os.path.join(indirme_yolu, f))]
                if dosyalar:
                    en_yeni_dosya = max(dosyalar, key=lambda x: os.path.getctime(os.path.join(indirme_yolu, x)))
                    indirilen_dosya = os.path.join(indirme_yolu, en_yeni_dosya)
            except:
                pass
        
        if indirilen_dosya and os.path.exists(indirilen_dosya):
            print(f"Video başarıyla indirildi: {indirilen_dosya}")
            return indirilen_dosya
        else:
            raise Exception("İndirilen dosya bulunamadı")
        
    except Exception as e:
        hata_mesaji = f"Video indirme hatası: {str(e)}"
        print(hata_mesaji)
        print("Olası çözümler:")
        print("1. URL'nin doğru olduğundan emin olun")
        print("2. İnternet bağlantınızı kontrol edin")
        print("3. Video özel veya kısıtlı olabilir")
        print("4. yt-dlp kütüphanesini yükleyin: pip install yt-dlp")
        print("5. yt-dlp'yi güncelleyin: pip install --upgrade yt-dlp")
        return hata_mesaji

# 3. ÇEKİRDEK İŞ MANTIĞI (TOOL'DAN AYRI)
# -----------------------------------------------------------------------------
# Bu en iyi pratiktir: Asıl işi yapan mantığı ayrı bir fonksiyona koymak,
# tool'un kendisini test edilebilir ve yeniden kullanılabilir kılar.
def _videoyu_ozetle_logic(video_url: str = "", video_dosyasi_yolu: str = "", ozet_tipi: str = "kapsamli") -> str:
    """Video özetlemenin tüm çekirdek mantığını içeren, test edilebilir fonksiyon."""
    logging.info("Video özetleme işlemi başlatıldı")
    logging.debug(f"Gelen parametreler - video_url: {video_url}, video_dosyasi_yolu: {video_dosyasi_yolu}, ozet_tipi: {ozet_tipi}")
    
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
                
                # video_indir fonksiyonunu kullanarak videoyu indir
                try:
                    temp_dir = "/tmp/video_downloads"
                    os.makedirs(temp_dir, exist_ok=True)
                    logging.debug(f"Geçici dizin oluşturuldu: {temp_dir}")
                    
                    logging.info("yt-dlp ile video indiriliyor...")
                    video_path = video_indir(video_url, temp_dir)
                    
                    # video_indir fonksiyonu hata durumunda string mesaj döndürür
                    if video_path.startswith("Video indirme hatası:"):
                        logging.error(f"Video indirme başarısız: {video_path}")
                        return json.dumps({"durum": "Hata", "mesaj": video_path}, ensure_ascii=False)
                    
                    if not os.path.exists(video_path):
                        logging.error(f"İndirilen video dosyası bulunamadı: {video_path}")
                        return json.dumps({"durum": "Hata", "mesaj": "Video indirildikten sonra dosya bulunamadı."}, ensure_ascii=False)
                    
                    logging.info(f"Video başarıyla indirildi: {video_path}")
                    logging.debug(f"İndirilen dosya boyutu: {os.path.getsize(video_path)} bytes")
                    temp_dosya = True
                    
                    # Dosya boyutu kontrolü (örn: 100MB sınırı)
                    if os.path.getsize(video_path) > 100 * 1024 * 1024:  # 100MB
                        logging.warning(f"Video çok büyük: {os.path.getsize(video_path)} bytes")
                        return json.dumps({"durum": "Hata", "mesaj": "Video dosyası çok büyük (100MB sınırı). Daha kısa bir video deneyin."}, ensure_ascii=False)
                        
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

        # AI özet oluşturma - özet tipine göre farklı promptlar
        try:
            logging.info(f"Video başarıyla işlendi. AI özet oluşturma başlıyor... Tip: {ozet_tipi}")
            model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
            logging.debug("Gemini model oluşturuldu")
            
            if ozet_tipi == "kisa":
                prompt = """
                Bu videoyu kısaca özetle. Sadece aşağıdaki formatta JSON cevap ver:

                {
                    "konu": "Videonun ana konusu",
                    "kisa_ozet": "2-3 cümle halinde videonun ana fikri ve en önemli noktaları"
                }

                Lütfen yanıtını sadece JSON formatında ver, başka metin ekleme.
                """
            elif ozet_tipi == "genis":
                prompt = """
                Bu videoyu detaylı şekilde analiz et. Aşağıdaki formatta JSON cevap ver:

                {
                    "konu": "Videonun ana konusu ve başlığı",
                    "genis_ozet": "Videonun çok detaylı içeriği, tüm önemli noktaları, öğrenme çıktıları ve açıklamaları paragraflar halinde",
                    "kilit_ogrenme_noktalari": ["Detaylı madde 1", "Detaylı madde 2", "Detaylı madde 3", "..."],
                    "ilgili_konular": ["İlgili konu 1", "İlgili konu 2", "İlgili konu 3"]
                }

                Lütfen yanıtını sadece JSON formatında ver, başka metin ekleme.
                """
            else:  # kapsamli (varsayılan)
                prompt = """
                Bu videoyu bir öğrenciye ders anlatır gibi analiz et. Aşağıdaki formatta bir özet çıkar ve cevabını JSON formatında ver:

                {
                    "konu": "Videonun ana konusu ve başlığı",
                    "kisa_ozet": "Tek paragraf halinde videonun ana fikri ve önemli noktaları",
                    "genis_ozet": "Videonun detaylı içeriği, öğrenme çıktıları ve önemli noktaları paragraflar halinde",
                    "kilit_ogrenme_noktalari": ["Madde 1", "Madde 2", "Madde 3", "..."],
                    "ilgili_konular": ["Konu 1", "Konu 2", "Konu 3"],
                    "yazar_bilgileri": {
                        "kanal_adi": "Video kanalının adı (varsa)",
                        "yazar": "İçerik yaratıcısının adı (varsa)",
                        "sunum_tarzi": "Videonun sunum tarzı ve yaklaşımı hakkında açıklama"
                    }
                }

                Lütfen yanıtını sadece JSON formatında ver, başka metin ekleme.
                """
            
            logging.info("AI'dan özet isteniyor...")
            response = model.generate_content([prompt, video_file])
            logging.info("AI özeti başarıyla oluşturuldu")
            logging.debug(f"Özet uzunluğu: {len(response.text)} karakter")
            
            # JSON cevabını parse et
            try:
                # Gemini'nin cevabını temizle (markdown kod blokları varsa)
                clean_response = response.text.strip()
                if clean_response.startswith('```json'):
                    clean_response = clean_response.replace('```json', '').replace('```', '').strip()
                elif clean_response.startswith('```'):
                    clean_response = clean_response.replace('```', '').strip()
                
                ozet_data = json.loads(clean_response)
                logging.info("AI cevabı başarıyla JSON formatında parse edildi")
                
            except json.JSONDecodeError as json_error:
                logging.error(f"AI cevabı JSON formatında parse edilemedi: {json_error}")
                # Fallback: Ham metni kullan
                if ozet_tipi == "kisa":
                    ozet_data = {
                        "konu": "Video İçeriği",
                        "kisa_ozet": response.text
                    }
                elif ozet_tipi == "genis":
                    ozet_data = {
                        "konu": "Video İçeriği",
                        "genis_ozet": response.text,
                        "kilit_ogrenme_noktalari": [],
                        "ilgili_konular": []
                    }
                else:
                    ozet_data = {
                        "konu": "Video İçeriği",
                        "kisa_ozet": "Video analizi tamamlandı fakat yapılandırılmış format oluşturulamadı.",
                        "genis_ozet": response.text,
                        "kilit_ogrenme_noktalari": [],
                        "ilgili_konular": [],
                        "yazar_bilgileri": {
                            "kanal_adi": "Bilinmiyor",
                            "yazar": "Bilinmiyor",
                            "sunum_tarzi": "Bilinmiyor"
                        }
                    }
                
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
        return json.dumps({"durum": "Başarılı", "video_analizi": ozet_data}, ensure_ascii=False)

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
def videoyu_ozetle(video_url: str = "", video_dosyasi_yolu: str = "", ozet_tipi: str = "kapsamli") -> str:
    """
    VIDEO ÖZETLEME AJANI - Verilen bir videonun içeriğini eğitim odaklı olarak metin formatında özetler.

    Kullanıcı "bu videoyu özetle", "videodaki önemli noktalar neler?" veya bir video linki paylaştığında bu aracı kullan.

    Args:
        video_url (str): Özetlenecek videonun YouTube linki.
        video_dosyasi_yolu (str): (Opsiyonel) Sunucuda bulunan bir video dosyasının yolu.
        ozet_tipi (str): Özet türü - "kisa" (sadece kısa özet), "genis" (sadece detaylı özet), "kapsamli" (her ikisi de). Varsayılan: "kapsamli"
    
    Returns:
        str: Videonun özetini içeren bir JSON string'i.
    """
    logging.info("videoyu_ozetle tool'u çağrıldı")
    # Bu fonksiyon, asıl işi yapan logic fonksiyonunu çağırır.
    return _videoyu_ozetle_logic(video_url=video_url, video_dosyasi_yolu=video_dosyasi_yolu, ozet_tipi=ozet_tipi)


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