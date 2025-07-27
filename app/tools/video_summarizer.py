import json
import os
import logging
import time
from dotenv import load_dotenv
from fastmcp import FastMCP
import yt_dlp
import re
from app.functions import video_indir
import google.generativeai as genai
from app.server import mcp
from app.config import GEMINI_API_KEY


def _videoyu_ozetle_logic(video_url: str = "", video_dosyasi_yolu: str = "", ozet_tipi: str = "kapsamli", hedef_dil: str = "otomatik") -> str:
    """Video özetlemenin tüm çekirdek mantığını içeren, test edilebilir fonksiyon."""
    logging.info("Video özetleme işlemi başlatıldı")
    logging.debug(f"Gelen parametreler - video_url: {video_url}, video_dosyasi_yolu: {video_dosyasi_yolu}, ozet_tipi: {ozet_tipi}, hedef_dil: {hedef_dil}")
    
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
            logging.info(f"Video başarıyla işlendi. AI özet oluşturma başlıyor... Tip: {ozet_tipi}, Hedef dil: {hedef_dil}")
            if not GEMINI_API_KEY:
                logging.error("GEMINI_API_KEY bulunamadı")
                return json.dumps({"durum": "Hata", "mesaj": "API anahtarı yapılandırılmamış. Lütfen .env dosyasını kontrol edin."}, ensure_ascii=False)
            # Gemini API'yi yapılandır
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
            logging.debug("Gemini model oluşturuldu")
            
            # Dil ayarları için ek metin
            dil_talimat = ""
            if hedef_dil == "otomatik":
                dil_talimat = "Video hangi dilde ise özetin de o dilde olmasını sağla. Videonun dilini otomatik algıla ve özetin tamamını o dilde yaz."
            elif hedef_dil != "otomatik":
                dil_talimat = f"Özetin tamamını {hedef_dil} dilinde yaz. Video farklı dilde olsa bile, özet {hedef_dil} dilinde olmalı."
            
            if ozet_tipi == "kisa":
                prompt = f"""
                {dil_talimat}
                
                Bu videoyu kısaca özetle. Sadece aşağıdaki formatta JSON cevap ver:

                {{
                    "video_dili": "Algılanan video dili",
                    "konu": "Videonun ana konusu",
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
                    "konu": "Videonun ana konusu ve başlığı",
                    "genis_ozet": "Videonun çok detaylı içeriği, tüm önemli noktaları, öğrenme çıktıları ve açıklamaları paragraflar halinde",
                    "zaman_damgalari": [
                        {{"dakika": "3:15", "konu": "Bahsedilen önemli nokta", "aciklama": "Bu dakikada ne söylendiğinin detaylı açıklaması"}},
                        {{"dakika": "7:22", "konu": "Diğer önemli nokta", "aciklama": "Bu bölümde vurgulanan ana fikir"}}
                    ],
                    "kilit_ogrenme_noktalari": ["Detaylı madde 1", "Detaylı madde 2", "Detaylı madde 3", "..."],
                    "gorsel_aciklamalar": ["Videoda gösterilen grafik/slayt/görsel açıklaması 1", "görsel 2"],
                    "bahsedilen_kaynaklar": ["Kitap/makale/website adı 1", "kaynak 2"],
                    "ilgili_konular": ["İlgili konu 1", "İlgili konu 2", "İlgili konu 3"],
                    "anahtar_kelimeler": ["kelime1", "kelime2", "kelime3", "kelime4", "kelime5"],
                    "etiketler": ["#etiket1", "#etiket2", "#etiket3"],
                    "ogrenme_ciktilari": ["Bu videoyu izledikten sonra öğreneceğiniz şey 1", "şey 2", "şey 3"],
                    "video_sonrasi_ogrenilecekler": "Bu videoyu izledikten sonra şunları öğrenmiş olacaksınız: (detaylı açıklama)"
                }}

                Lütfen yanıtını sadece JSON formatında ver, başka metin ekleme.
                """
            else:  # kapsamli (varsayılan)
                prompt = f"""
                {dil_talimat}
                
                Bu videoyu bir öğrenciye ders anlatır gibi analiz et. Aşağıdaki formatta bir özet çıkar ve cevabını JSON formatında ver:

                {{
                    "video_dili": "Algılanan video dili (örn: Türkçe, İngilizce, vs.)",
                    "konu": "Videonun ana konusu ve başlığı",
                    "kisa_ozet": "Tek paragraf halinde videonun ana fikri ve önemli noktaları",
                    "genis_ozet": "Videonun detaylı içeriği, öğrenme çıktıları ve önemli noktaları paragraflar halinde",
                    "zaman_damgalari": [
                        {{"dakika": "0:45", "konu": "Giriş ve video amacı", "aciklama": "Videonun başında ne amaçla çekildiği ve hangi konuları kapsayacağı açıklanıyor"}},
                        {{"dakika": "3:15", "konu": "Ana fikir sunumu", "aciklama": "Bu dakikada videonun temel konusu ve ana fikri detaylı olarak açıklanmaya başlıyor"}},
                        {{"dakika": "7:22", "konu": "Önemli örnek", "aciklama": "Konuyu anlaşılır kılmak için verilen pratik örnek ve açıklaması"}},
                        {{"dakika": "12:10", "konu": "Kritik bilgi", "aciklama": "Bu bölümde videonun en önemli noktalarından biri vurgulanıyor"}}
                    ],
                    "kilit_ogrenme_noktalari": ["Madde 1", "Madde 2", "Madde 3", "..."],
                    "gorsel_aciklamalar": ["Videoda gösterilen grafik/slayt/görsel açıklaması", "İkinci önemli görsel açıklaması"],
                    "bahsedilen_kaynaklar": ["Videoda bahsedilen kitap/makale/website adı", "İkinci kaynak"],
                    "ilgili_konular": ["Konu 1", "Konu 2", "Konu 3"],
                    "anahtar_kelimeler": ["kelime1", "kelime2", "kelime3", "kelime4", "kelime5"],
                    "etiketler": ["#etiket1", "#etiket2", "#etiket3"],
                    "ogrenme_ciktilari": ["Bu videoyu izledikten sonra şunu öğrenmiş olacaksınız", "İkinci öğrenme çıktısı", "Üçüncü beceri"],
                    "video_sonrasi_ogrenilecekler": "Bu videoyu izledikten sonra şunları öğrenmiş olacaksınız: (kapsamlı özet)",
                    "yazar_bilgileri": {{
                        "kanal_adi": "Video kanalının adı (varsa)",
                        "yazar": "İçerik yaratıcısının adı (varsa)",
                        "sunum_tarzi": "Videonun sunum tarzı ve yaklaşımı hakkında açıklama"
                    }}
                }}

                Özel olarak dikkat et:
                - Zaman damgaları için videodaki gerçek zamanları kullan
                - Her önemli bölüm için dakika:saniye formatında zaman belirt
                - Videonun farklı bölümlerinde vurgulanan ana fikirleri ayrı ayrı not et
                - Görsel materyaller varsa (grafik, slayt, diagram) bunları da açıkla
                - Bahsedilen kaynakları, kitapları, web sitelerini listele
                - "video_sonrasi_ogrenilecekler" alanında bu videoyu tamamen izleyen bir kişinin hangi bilgi ve becerileri kazanacağını özetle

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
                        "video_dili": "Algılanamadı",
                        "konu": "Video İçeriği",
                        "kisa_ozet": response.text,
                        "anahtar_kelimeler": [],
                        "ogrenme_ciktilari": [],
                        "video_sonrasi_ogrenilecekler": "Bu videoyu izledikten sonra çeşitli bilgiler edinmiş olacaksınız."
                    }
                elif ozet_tipi == "genis":
                    ozet_data = {
                        "video_dili": "Algılanamadı",
                        "konu": "Video İçeriği",
                        "genis_ozet": response.text,
                        "zaman_damgalari": [],
                        "kilit_ogrenme_noktalari": [],
                        "gorsel_aciklamalar": [],
                        "bahsedilen_kaynaklar": [],
                        "ilgili_konular": [],
                        "anahtar_kelimeler": [],
                        "etiketler": [],
                        "ogrenme_ciktilari": [],
                        "video_sonrasi_ogrenilecekler": "Bu videoyu izledikten sonra konu hakkında detaylı bilgiler edinmiş olacaksınız."
                    }
                else:
                    ozet_data = {
                        "video_dili": "Algılanamadı",
                        "konu": "Video İçeriği",
                        "kisa_ozet": "Video analizi tamamlandı fakat yapılandırılmış format oluşturulamadı.",
                        "genis_ozet": response.text,
                        "zaman_damgalari": [],
                        "kilit_ogrenme_noktalari": [],
                        "gorsel_aciklamalar": [],
                        "bahsedilen_kaynaklar": [],
                        "ilgili_konular": [],
                        "anahtar_kelimeler": [],
                        "etiketler": [],
                        "ogrenme_ciktilari": [],
                        "video_sonrasi_ogrenilecekler": "Bu videoyu izledikten sonra çeşitli konularda bilgi ve beceriler edinmiş olacaksınız.",
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

@mcp.tool(tags={"public"})
def videoyu_ozetle(video_url: str = "", video_dosyasi_yolu: str = "", ozet_tipi: str = "kapsamli", hedef_dil: str = "otomatik") -> str:
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
    logging.info("videoyu_ozetle tool'u çağrıldı")
    # Bu fonksiyon, asıl işi yapan logic fonksiyonunu çağırır.
    return _videoyu_ozetle_logic(video_url=video_url, video_dosyasi_yolu=video_dosyasi_yolu, ozet_tipi=ozet_tipi, hedef_dil=hedef_dil)
