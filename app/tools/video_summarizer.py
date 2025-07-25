import json
import os
import logging
from urllib.parse import urlparse
import google.generativeai as genai
from pytube import YouTube
from moviepy import VideoFileClip
from dotenv import load_dotenv
from fastmcp import FastMCP
import time
# Proje ana dizinindeki .env dosyasını yükle
# Bu satır, .env dosyasındaki değişkenleri ortam değişkeni olarak kullanılabilir hale getirir.
load_dotenv() 

mcp = FastMCP(
    "Video Özetleme Tool",
    include_tags={"public"},  # sadece public tag'i olan tool'lar görünür olacak
    exclude_tags={"private", "beta"}  # private ve beta tag'i olan tool'lar görünür olmayacak
)




# Logger yapılandırması
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- UZMAN AGENT (GEMINI API) YAPILANDIRMASI ---
# API anahtarını ortam değişkenlerinden güvenli bir şekilde al
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logging.warning("GEMINI_API_KEY bulunamadı. Lütfen .env dosyasını kontrol edin.")
else:
    genai.configure(api_key=GEMINI_API_KEY)


@mcp.tool(tags={"public"})
def videoyu_ozetle(video_url: str = "", video_dosyasi_yolu: str = "") -> str:
    """
    ℹ️ VİDEO ÖZETLEME AJANI - Verilen bir videonun içeriğini eğitim odaklı olarak metin formatında özetler.

    Kullanıcı "bu videoyu özetle", "videodaki önemli noktalar neler?" veya bir video linki paylaştığında bu aracı kullan.

    Args:
        video_url (str): Özetlenecek videonun YouTube veya doğrudan .mp4 linki.
        video_dosyasi_yolu (str): (Opsiyonel) Sunucuda bulunan bir video dosyasının yolu.
    
    Returns:
        str: Videonun ana fikirlerini, kilit öğrenme noktalarını ve detaylı özetini içeren bir JSON string'i.
    """
    if not video_url and not video_dosyasi_yolu:
        return json.dumps({
            "durum": "Hata",
            "mesaj": "Özetlemek için bir video URL'i veya dosya yolu sağlamalısınız."
        }, ensure_ascii=False, indent=2)

    video_path = None
    temp_dosya = False # İndirilen dosyayı daha sonra silmek için işaretçi

    try:
        # 1. Video Kaynağını İşle: URL mi, yerel dosya mı?
        if video_url:
            logging.info(f"Video URL'i işleniyor: {video_url}")
            # YouTube linki mi kontrol et
            if "youtube.com" in video_url or "youtu.be" in video_url:
                yt = YouTube(video_url)
                stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
                video_path = stream.download(output_path="/tmp") # Geçici bir klasöre indir
                logging.info(f"YouTube videosu indirildi: {video_path}")
            else:
                # Doğrudan video linki ise (örn: .../video.mp4)
                # Bu özellik için `requests` kütüphanesi gerekebilir. Şimdilik temel bir varsayım yapıyoruz.
                raise NotImplementedError("Doğrudan video URL'den indirme henüz desteklenmiyor. Lütfen YouTube linki kullanın.")
            temp_dosya = True

        elif video_dosyasi_yolu:
            logging.info(f"Yerel video dosyası işleniyor: {video_dosyasi_yolu}")
            if not os.path.exists(video_dosyasi_yolu):
                return json.dumps({"durum": "Hata", "mesaj": f"Belirtilen dosya yolu bulunamadı: {video_dosyasi_yolu}"}, ensure_ascii=False, indent=2)
            video_path = video_dosyasi_yolu

        # --- UZMAN AGENT ÇAĞRISI (GEMINI 1.5 PRO) ---
        logging.info(f"Video Gemini'ye yükleniyor: {video_path}")
        
        # Videoyu API'ye yükle
        video_file = genai.upload_file(path=video_path, mime_type="video/mp4")
        logging.info(f"Video başarıyla yüklendi: {video_file.name}")
        
        # Yüklemenin tamamlandığından emin olmak için bekle
        while video_file.state.name == "PROCESSING":
            print('.', end='')
            time.sleep(10)
            video_file = genai.get_file(video_file.name)

        if video_file.state.name == "FAILED":
            return json.dumps({"durum": "Hata", "mesaj": "Video yüklemesi başarısız oldu."}, ensure_ascii=False, indent=2)

        # Gemini 1.5 Pro modelini çağır
        model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")

        # Eğitim odaklı bir prompt oluştur
        prompt = """
        Bu videoyu bir öğrenciye ders anlatır gibi analiz et.
        Aşağıdaki formatta bir özet çıkar:
        
        1.  **Ana Fikir:** Videonun tek cümlelik özeti.
        2.  **Kilit Öğrenme Noktaları:** Maddeler halinde videodaki en önemli 3-5 öğrenme çıktısı.
        3.  **Detaylı Özet:** Videonun içeriğini paragraflar halinde, başlangıcı, gelişmesi ve sonucuyla birlikte açıkla. Anlaşılması zor terimleri basitçe izah et.
        4.  **İlgili Konular:** Bu videodaki konularla bağlantılı, öğrencinin araştırabileceği 3 ek konu öner.
        """

        logging.info("Gemini'den video özeti isteniyor...")
        # Modeli video ve prompt ile çalıştır
        response = model.generate_content([prompt, video_file])

        # API'ye yüklenen dosyayı sil
        genai.delete_file(video_file.name)
        logging.info(f"Yüklenen dosya ({video_file.name}) API'den silindi.")

        return json.dumps({
            "durum": "Başarılı",
            "ozet": response.text
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        logging.error(f"Video işleme sırasında beklenmedik bir hata oluştu: {str(e)}")
        return json.dumps({
            "durum": "Hata",
            "mesaj": f"Video özetlenirken bir hata oluştu: {str(e)}"
        }, ensure_ascii=False, indent=2)

    finally:
        # Eğer video geçici olarak indirildiyse, yerel kopyayı sil
        if temp_dosya and video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
                logging.info(f"Geçici video dosyası silindi: {video_path}")
            except Exception as e:
                logging.error(f"Geçici video dosyası silinirken hata: {e}")

# Bu blok, dosyayı doğrudan çalıştırarak tool'u test etmenizi sağlar.
if __name__ == '__main__':
    print("--- Video Özetleme Tool Testi ---")
    
    # Test 1: YouTube URL'i ile
    test_youtube_url = "https://youtu.be/-CxauCeQ_SQ?si=Lqgg9Hj-zfWhU6M6"
    print(f"\n[TEST 1] YouTube URL'i ile özetleme başlatılıyor: {test_youtube_url}")
    ozet_json_1 = videoyu_ozetle(video_url=test_youtube_url)
    print("Sonuç:")
    # JSON'u daha okunaklı yazdırmak için
    print(json.dumps(json.loads(ozet_json_1), ensure_ascii=False, indent=4))
    
    # Test 2: Hatalı giriş ile
    print("\n[TEST 2] Hatalı giriş testi (URL veya dosya yok)")
    ozet_json_2 = videoyu_ozetle()
    print("Sonuç:")
    print(json.dumps(json.loads(ozet_json_2), ensure_ascii=False, indent=4))