import json
import os
import logging
import asyncio  # Asenkron operasyonlar için temel kütüphane
import time
import anyio
import uuid
from dotenv import load_dotenv
from app.server import mcp
import yt_dlp
import re
import google.generativeai as genai
from app.config import GEMINI_API_KEY

# Ortak klasör yolu
SHARED_UPLOADS_DIR = r'C:\mcpler\education_mcp\shared_uploads'


import os
import re
import yt_dlp


def video_indir(url, indirme_yolu=SHARED_UPLOADS_DIR):
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
        
        # Benzersiz dosya adı için timestamp ve UUID ekle
        timestamp = str(int(time.time()))
        unique_id = str(uuid.uuid4())[:8]
        
        # yt-dlp seçenekleri - düşük kalite öncelikli ve benzersiz dosya adı
        ydl_opts = {
            'format': 'worst[ext=mp4]/worst',  # En düşük kalite mp4, yoksa en düşük kalite
            'outtmpl': os.path.join(indirme_yolu, f'video_{timestamp}_{unique_id}.%(ext)s'),  # Benzersiz dosya adı
            'quiet': False,  # Detaylı çıktı
            'no_warnings': False,
            'extractaudio': False,  # Sadece video
            'writeinfojson': False,  # Info dosyası yazma
            'writethumbnail': False,  # Thumbnail yazma
            'concurrent_fragment_downloads': 30,  # Eşzamanlı indirme sayısını sınırla
            'retries': 3,  # Yeniden deneme sayısı
            'fragment_retries': 3,  # Fragment yeniden deneme sayısı
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
        
        # İndirilen dosyayı bul - benzersiz dosya adı ile
        olasi_uzantilar = ['.mp4', '.webm', '.mkv', '.flv']
        indirilen_dosya = None
        
        # Benzersiz dosya adı ile dosyayı ara
        for uzanti in olasi_uzantilar:
            dosya_yolu = os.path.join(indirme_yolu, f"video_{timestamp}_{unique_id}{uzanti}")
            if os.path.exists(dosya_yolu):
                indirilen_dosya = dosya_yolu
                break
        
        # Eğer tam eşleşme bulunamazsa, klasördeki en son eklenen dosyayı bul
        if not indirilen_dosya:
            try:
                dosyalar = [f for f in os.listdir(indirme_yolu) if os.path.isfile(os.path.join(indirme_yolu, f))]
                if dosyalar:
                    # Son 10 saniye içinde oluşturulan dosyaları filtrele
                    yeni_dosyalar = []
                    current_time = time.time()
                    for dosya in dosyalar:
                        dosya_yolu = os.path.join(indirme_yolu, dosya)
                        if current_time - os.path.getctime(dosya_yolu) < 10:  # Son 10 saniye
                            yeni_dosyalar.append(dosya)
                    
                    if yeni_dosyalar:
                        en_yeni_dosya = max(yeni_dosyalar, key=lambda x: os.path.getctime(os.path.join(indirme_yolu, x)))
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



async def _videoyu_ozetle_logic(video_url: str = "", video_dosyasi_yolu: str = "", ozet_tipi: str = "kapsamli", hedef_dil: str = "otomatik") -> str:
    """Video özetlemenin tüm çekirdek mantığını içeren, test edilebilir ve asenkron çalışan fonksiyon."""
    logging.info("Asenkron video özetleme işlemi başlatıldı")
    logging.debug(f"Gelen parametreler - video_url: {video_url}, video_dosyasi_yolu: {video_dosyasi_yolu}, ozet_tipi: {ozet_tipi}, hedef_dil: {hedef_dil}")
    
    if not video_url and not video_dosyasi_yolu:
        logging.warning("Video URL'si veya dosya yolu sağlanmadı")
        return json.dumps({"durum": "Hata", "mesaj": "Bir video URL'si veya dosya yolu sağlamalısınız."}, ensure_ascii=False)

    video_dosyasi_path = ""
    
    if video_dosyasi_yolu:
        # Dosya yolunu işle - tam yoldan sadece dosya adını al
        if os.path.sep in video_dosyasi_yolu:
            # Tam yol verilmiş, sadece dosya adını al
            dosya_adi = os.path.basename(video_dosyasi_yolu)
            logging.info(f"Tam yol verildi, dosya adı çıkarıldı: {dosya_adi}")
        else:
            # Sadece dosya adı verilmiş
            dosya_adi = video_dosyasi_yolu
            logging.info(f"Sadece dosya adı verildi: {dosya_adi}")
        
        # Dosya yolunu ortak klasörden oluştur
        video_dosyasi_path = os.path.join(SHARED_UPLOADS_DIR, dosya_adi)
        logging.info(f"Video dosyası aranıyor: {video_dosyasi_path}")
        
        # Dosya varlığını kontrol et
        if not await anyio.to_thread.run_sync(os.path.exists, video_dosyasi_path):
            logging.error(f"Video dosyası bulunamadı: {video_dosyasi_path}")
            return json.dumps({"durum": "Hata", "mesaj": f"Video dosyası bulunamadı: {dosya_adi}. Ortak klasörde dosya var mı kontrol edin."}, ensure_ascii=False)
    
    elif video_url:
        # YouTube URL'sinden video indir
        try:
            logging.info(f"YouTube video indiriliyor: {video_url}")
            
            # Video indir (ortak klasöre)
            video_dosyasi_path = await anyio.to_thread.run_sync(video_indir, video_url)
            
            if not video_dosyasi_path or not await anyio.to_thread.run_sync(os.path.exists, video_dosyasi_path):
                logging.error("Video indirme başarısız")
                return json.dumps({"durum": "Hata", "mesaj": "Video indirilemedi. URL'yi kontrol edin."}, ensure_ascii=False)
            
            logging.info(f"Video başarıyla indirildi: {video_dosyasi_path}")
            
        except Exception as e:
            logging.error(f"Video indirme hatası: {str(e)}")
            return json.dumps({"durum": "Hata", "mesaj": f"Video indirme hatası: {str(e)}"}, ensure_ascii=False)

    # Video dosya boyutu kontrolü
    try:
        dosya_boyutu = await anyio.to_thread.run_sync(os.path.getsize, video_dosyasi_path)
        logging.debug(f"Video dosya boyutu: {dosya_boyutu} bytes")
        if dosya_boyutu > 500 * 1024 * 1024:  # 500MB
            logging.warning(f"Video çok büyük: {dosya_boyutu} bytes")
            return json.dumps({"durum": "Hata", "mesaj": "Video dosyası çok büyük (500MB sınırı). Daha küçük bir dosya deneyin."}, ensure_ascii=False)
    except Exception as e:
        logging.error(f"Dosya boyutu kontrolü hatası: {str(e)}")
        return json.dumps({"durum": "Hata", "mesaj": f"Dosya boyutu kontrolü hatası: {str(e)}"}, ensure_ascii=False)

    # Gemini API'ye yükleme (asenkron)
    try:
        logging.info(f"Video Gemini API'ye yükleniyor: {video_dosyasi_path}")
        
        # Video MIME type'ını belirle
        dosya_uzantisi = os.path.splitext(video_dosyasi_path)[1].lower()
        mime_map = {
            '.mp4': 'video/mp4',
            '.webm': 'video/webm',
            '.mkv': 'video/x-matroska',
            '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime',
            '.flv': 'video/x-flv'
        }
        mime_type = mime_map.get(dosya_uzantisi, 'video/mp4')
        
        # genai.upload_file'ı anyio ile asenkron çalıştır
        def upload_video():
            return genai.upload_file(path=video_dosyasi_path, mime_type=mime_type)
        
        video_file = await anyio.to_thread.run_sync(upload_video)
        logging.info(f"Yükleme başladı: {video_file.name}. İşlenmesi bekleniyor...")
        logging.debug(f"Video dosyası durumu: {video_file.state.name}")
    except Exception as upload_error:
        logging.error(f"Gemini API yükleme hatası: {str(upload_error)}")
        return json.dumps({"durum": "Hata", "mesaj": f"Video Gemini API'ye yüklenemedi: {str(upload_error)}"}, ensure_ascii=False)

    # Video işleme bekleme (asenkron)
    progress_counter = 0
    max_wait_time = 120
    while video_file.state.name == "PROCESSING" and progress_counter < max_wait_time // 5:
        progress_counter += 1
        print('.', end='', flush=True)
        logging.debug(f"İşleme devam ediyor... ({progress_counter * 5} saniye geçti)")
        # asyncio.sleep ile asenkron bekleme
        await asyncio.sleep(5) 
        video_file = await anyio.to_thread.run_sync(genai.get_file, video_file.name)

    print()
    logging.info(f"Video işleme tamamlandı. Final durumu: {video_file.state.name}")

    if video_file.state.name == "FAILED":
        logging.error(f"Video işleme başarısız: {video_file.error}")
        return json.dumps({"durum": "Hata", "mesaj": f"Video işleme başarısız: {video_file.error}"}, ensure_ascii=False)
    
    if video_file.state.name == "PROCESSING":
        logging.error("Video işleme çok uzun sürdü")
        return json.dumps({"durum": "Hata", "mesaj": "Video işleme çok uzun sürdü. Daha kısa bir video deneyin."}, ensure_ascii=False)

    # AI özet oluşturma (asenkron)
    try:
        # genai.configure'ı senkron çalıştır - api_key parametresini direkt olarak kullan
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
        
        # Dil talimatı
        if hedef_dil == "otomatik":
            dil_talimat = "Video hangi dildeyse aynı dilde yanıt ver. Video dilini otomatik algıla ve o dilde özet oluştur."
        else:
            dil_talimat = f"Yanıtını {hedef_dil} dilinde ver."
        
        if ozet_tipi == "kisa":
            prompt = f"""
            {dil_talimat}
            
            Bu videoyu kısaca özetle. Sadece aşağıdaki formatta JSON cevap ver:

            {{
                "video_dili": "Algılanan video dili",
                "baslik": "Videonun başlığı veya ana konusu",
                "kisa_ozet": "2-3 cümle halinde videonun ana fikri ve en önemli noktaları",
                "anahtar_kelimeler": ["kelime1", "kelime2", "kelime3"],
                "ogrenme_ciktilari": ["Bu videoyu izledikten sonra öğreneceğiniz şey 1", "şey 2"],
                "video_sonrasi_ogrenilecekler": "Bu videoyu izledikten sonra şunları öğrenmiş olacaksınız: (kısa bir özet)"
            }}

            Lütfen yanıtını sadece JSON formatında ver, başka metin ekleme.
            """
        elif ozet_tipi == "genis":
            prompt = f"""
            {dil_talimat}
            
            Bu videoyu detaylı şekilde analiz et. Aşağıdaki formatta JSON cevap ver:

            {{
                "video_dili": "Algılanan video dili",
                "baslik": "Videonun başlığı veya ana konusu",
                "detayli_ozet": "Videonun kapsamlı özetini 4-6 paragraf halinde açıkla",
                "anahtar_kelimeler": ["kelime1", "kelime2", "kelime3", "kelime4", "kelime5"],
                "ogrenme_ciktilari": ["Bu videoyu izledikten sonra öğreneceğiniz şey 1", "şey 2", "şey 3"],
                "video_sonrasi_ogrenilecekler": "Bu videoyu izledikten sonra şunları öğrenmiş olacaksınız: (detaylı özet)"
            }}

            Lütfen yanıtını sadece JSON formatında ver, başka metin ekleme.
            """
        else:  # kapsamli
            prompt = f"""
            {dil_talimat}
            
            Bu videoyu kapsamlı şekilde analiz et ve eğitim odaklı bir özet oluştur. Aşağıdaki formatta JSON cevap ver:

            {{
                "video_dili": "Algılanan video dili",
                "baslik": "Videonun başlığı veya ana konusu",
                "kisa_ozet": "2-3 cümle halinde videonun ana fikri",
                "detayli_ozet": "Videonun kapsamlı özetini 4-6 paragraf halinde açıkla",
                "zaman_damgalari": [
                    {{"zaman": "0:30", "aciklama": "Giriş ve konu tanıtımı"}},
                    {{"zaman": "2:15", "aciklama": "Ana fikrin açıklanması"}},
                    {{"zaman": "5:45", "aciklama": "Örnek gösterim"}}
                ],
                "gorsel_materyaller": ["Video boyunca görülen grafik, slayt, yazı vs. açıklamaları"],
                "bahsedilen_kaynaklar": ["Videoda geçen kitap, makale, web sitesi isimleri"],
                "anahtar_kelimeler": ["kelime1", "kelime2", "kelime3", "kelime4", "kelime5"],
                "etiketler": ["etiket1", "etiket2", "etiket3"],
                "ogrenme_ciktilari": ["Bu videoyu izledikten sonra öğreneceğiniz şey 1", "şey 2", "şey 3"],
                "detayli_analiz": "Videonun eğitim değeri, öğretim yöntemi ve içerik kalitesi hakkında analiz",
                "video_sonrasi_ogrenilecekler": "Bu videoyu izledikten sonra şunları öğrenmiş olacaksınız: (kapsamlı özet)"
            }}

            Lütfen yanıtını sadece JSON formatında ver, başka metin ekleme.
            """
        
        logging.info("AI'dan özet isteniyor (asenkron)...")
        # model.generate_content anyio ile asenkron çalıştırılır
        response = await anyio.to_thread.run_sync(model.generate_content, [prompt, video_file])
        logging.info("AI özeti başarıyla oluşturuldu")

        # JSON parse etme
        try:
            clean_response = response.text.strip().replace('```json', '').replace('```', '').strip()
            ozet_data = json.loads(clean_response)
            logging.debug("AI yanıtı başarıyla JSON'a dönüştürüldü")
        except json.JSONDecodeError as json_error:
            logging.error(f"AI yanıtı JSON formatında değil: {json_error}")
            # Fallback: Ham yanıtı döndür
            ozet_data = {
                "video_dili": "Bilinmiyor",
                "baslik": "Video Özeti",
                "ham_yanit": response.text,
                "hata": "JSON formatında olmayan yanıt"
            }
        
    except Exception as ai_error:
        logging.error(f"AI özet oluşturma hatası: {str(ai_error)}")
        return json.dumps({"durum": "Hata", "mesaj": f"AI özet oluşturulamadı: {str(ai_error)}"}, ensure_ascii=False)

    # Temizlik (asenkron) - AI işlemi tamamlandıktan sonra
    try:
        logging.info("Yüklenen video dosyası API'den siliniyor...")
        await anyio.to_thread.run_sync(genai.delete_file, video_file.name)
        logging.info(f"Yüklenen dosya ({video_file.name}) API'den başarıyla silindi")
    except Exception as delete_error:
        logging.warning(f"API'den dosya silme hatası: {str(delete_error)}")

    # Yerel dosya temizliği - AI işlemi tamamlandıktan sonra
    if video_dosyasi_path and await anyio.to_thread.run_sync(os.path.exists, video_dosyasi_path):
        try:
            logging.info(f"Video dosyası siliniyor: {video_dosyasi_path}")
            await anyio.to_thread.run_sync(os.remove, video_dosyasi_path)
            logging.info("Video dosyası başarıyla silindi")
        except Exception as e:
            logging.error(f"Dosya silinirken hata: {e}")

    logging.info("Video özetleme işlemi başarıyla tamamlandı")
    return json.dumps({"durum": "Başarılı", "video_analizi": ozet_data}, ensure_ascii=False)

@mcp.tool(tags={"public"})
async def videoyu_ozetle(video_url: str = "", video_dosyasi_yolu: str = "", ozet_tipi: str = "kapsamli", hedef_dil: str = "otomatik") -> str:
    """
    GELİŞMİŞ VIDEO ÖZETLEME AJANI - Verilen bir videonun içeriğini zaman damgaları, görsel açıklamalar ve kaynaklar ile birlikte eğitim odaklı olarak özetler.

    Kullanıcı "bu videoyu özetle", "videodaki önemli noktalar neler?" veya bir video linki paylaştığında bu aracı kullan.

    Args:
        video_url (str): Özetlenecek videonun YouTube linki.
        video_dosyasi_yolu (str): (Opsiyonel) Sunucuda bulunan bir video dosyasının yolu.
        ozet_tipi (str): Özet türü - "kisa" (sadece kısa özet), "genis" (sadece detaylı özet), "kapsamli" (her ikisi de + zaman damgaları). Varsayılan: "kapsamli"
        hedef_dil (str): Özetin hangi dilde olmasını istediğiniz - "otomatik" (video dilinde), "Türkçe", "İngilizce", "Almanca" vb. Varsayılan: "otomatik"
    
    Returns:
        str: Videonun gelişmiş özetini içeren bir JSON string'i. İçerik:
        - Video dilini otomatik algılama
        - Zaman damgaları ile önemli anlar (örn: "3:15 - Ana fikir açıklaması")
        - Görsel materyaller (grafik, slayt) açıklamaları
        - Bahsedilen kaynaklar (kitap, makale, web sitesi)
        - Anahtar kelimeler ve etiketler
        - Bu videoyu izleyerek öğrenilecek çıktılar
        - Detaylı analiz ve öğrenme noktaları
        - Video sonrası öğrenilecekler özeti
    """
    logging.info("videoyu_ozetle async tool'u çağrıldı")
    # Asıl işi yapan asenkron mantık fonksiyonunu çağırır ve sonucunu bekler.
    return await _videoyu_ozetle_logic(video_url=video_url, video_dosyasi_yolu=video_dosyasi_yolu, ozet_tipi=ozet_tipi, hedef_dil=hedef_dil)
