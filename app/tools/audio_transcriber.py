
# education_mcp/app/tools/audio_transcriber.py

import json
import os
import logging
import asyncio  # Asenkron operasyonlar için temel kütüphane
import time
import anyio
from dotenv import load_dotenv
from app.server import mcp
import google.generativeai as genai
from app.config import GEMINI_API_KEY

# Ortak klasör yolu
SHARED_UPLOADS_DIR = r'C:\mcpler\education_mcp\shared_uploads'

async def _ses_transkript_logic(ses_kaynagi: str, cikti_tipi: str = "ozet", hedef_dil: str = "otomatik") -> str:
    """Ses transkripsiyon işleminin tüm çekirdek mantığını içeren, test edilebilir ve asenkron çalışan fonksiyon."""
    logging.info("Asenkron ses transkripsiyon işlemi başlatıldı")
    logging.debug(f"Gelen parametreler - ses_kaynagi: {ses_kaynagi}, cikti_tipi: {cikti_tipi}, hedef_dil: {hedef_dil}")
    
    if not ses_kaynagi:
        logging.warning("Ses kaynağı sağlanmadı")
        return json.dumps({"durum": "Hata", "mesaj": "Bir ses dosyası yolu veya URL'i sağlamalısınız."}, ensure_ascii=False)

    # Dosya yolunu işle - tam yoldan sadece dosya adını al
    if os.path.sep in ses_kaynagi:
        # Tam yol verilmiş, sadece dosya adını al
        dosya_adi = os.path.basename(ses_kaynagi)
        logging.info(f"Tam yol verildi, dosya adı çıkarıldı: {dosya_adi}")
    else:
        # Sadece dosya adı verilmiş
        dosya_adi = ses_kaynagi
        logging.info(f"Sadece dosya adı verildi: {dosya_adi}")
    
    # Dosya yolunu ortak klasörden oluştur
    full_audio_path = os.path.join(SHARED_UPLOADS_DIR, dosya_adi)
    logging.info(f"Ses dosyası aranıyor: {full_audio_path}")

    try:
        # Dosya varlığını kontrol et (asenkron)
        if not await anyio.to_thread.run_sync(os.path.exists, full_audio_path):
            logging.error(f"Ses dosyası bulunamadı: {full_audio_path}")
            return json.dumps({"durum": "Hata", "mesaj": f"Ses dosyası bulunamadı: {dosya_adi}. Ortak klasörde dosya var mı kontrol edin."}, ensure_ascii=False)
        
        # Desteklenen ses formatlarını kontrol et
        desteklenen_formatlar = ['.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.webm']
        dosya_uzantisi = os.path.splitext(full_audio_path)[1].lower()
        if dosya_uzantisi not in desteklenen_formatlar:
            logging.error(f"Desteklenmeyen ses formatı: {dosya_uzantisi}")
            return json.dumps({"durum": "Hata", "mesaj": f"Desteklenen formatlar: {', '.join(desteklenen_formatlar)}"}, ensure_ascii=False)
        
        # Dosya boyutu kontrolü (asenkron)
        dosya_boyutu = await anyio.to_thread.run_sync(os.path.getsize, full_audio_path)
        logging.debug(f"Ses dosya boyutu: {dosya_boyutu} bytes")
        if dosya_boyutu > 100 * 1024 * 1024:  # 100MB
            logging.warning(f"Ses dosyası çok büyük: {dosya_boyutu} bytes")
            return json.dumps({"durum": "Hata", "mesaj": "Ses dosyası çok büyük (100MB sınırı). Daha küçük bir dosya deneyin."}, ensure_ascii=False)

        # Gemini API'ye yükleme (asenkron)
        try:
            logging.info(f"Ses dosyası Gemini API'ye yükleniyor: {full_audio_path}")
            # MIME type'ı belirle
            mime_map = {
                '.mp3': 'audio/mp3',
                '.wav': 'audio/wav', 
                '.flac': 'audio/flac',
                '.m4a': 'audio/m4a',
                '.aac': 'audio/aac',
                '.ogg': 'audio/ogg',
                '.webm': 'audio/webm'
            }
            mime_type = mime_map.get(dosya_uzantisi, 'audio/mpeg')
            
            # genai.upload_file'ı anyio ile asenkron çalıştır
            def upload_audio():
                return genai.upload_file(path=full_audio_path, mime_type=mime_type)
            
            ses_dosyasi = await anyio.to_thread.run_sync(upload_audio)
            logging.info(f"Yükleme başladı: {ses_dosyasi.name}. İşlenmesi bekleniyor...")
            logging.debug(f"Ses dosyası durumu: {ses_dosyasi.state.name}")
        except Exception as upload_error:
            logging.error(f"Gemini API yükleme hatası: {str(upload_error)}")
            return json.dumps({"durum": "Hata", "mesaj": f"Ses dosyası Gemini API'ye yüklenemedi: {str(upload_error)}"}, ensure_ascii=False)

        # Ses işleme bekleme (asenkron)
        progress_counter = 0
        max_wait_time = 120  # 2 dakika maksimum bekleme
        while ses_dosyasi.state.name == "PROCESSING" and progress_counter < max_wait_time // 5:
            progress_counter += 1
            print('.', end='', flush=True)
            logging.debug(f"İşleme devam ediyor... ({progress_counter * 5} saniye geçti)")
            # asyncio.sleep ile asenkron bekleme
            await asyncio.sleep(5)
            ses_dosyasi = await anyio.to_thread.run_sync(genai.get_file, ses_dosyasi.name)

        print()  # Satır sonu için
        logging.info(f"Ses işleme tamamlandı. Final durumu: {ses_dosyasi.state.name}")

        if ses_dosyasi.state.name == "FAILED":
            logging.error(f"Ses yüklemesi başarısız oldu: {ses_dosyasi.error}")
            return json.dumps({"durum": "Hata", "mesaj": f"Ses işleme başarısız: {ses_dosyasi.error}"}, ensure_ascii=False)
        
        if ses_dosyasi.state.name == "PROCESSING":
            logging.error("Ses işleme zaman aşımına uğradı")
            return json.dumps({"durum": "Hata", "mesaj": "Ses işleme çok uzun sürdü. Daha küçük bir dosya deneyin."}, ensure_ascii=False)

        # AI transkripsiyon ve analiz (asenkron)
        try:
            logging.info(f"Ses başarıyla işlendi. AI transkripsiyon başlıyor... Tip: {cikti_tipi}, Hedef dil: {hedef_dil}")
            if not GEMINI_API_KEY:
                logging.error("GEMINI_API_KEY bulunamadı")
                return json.dumps({"durum": "Hata", "mesaj": "API anahtarı yapılandırılmamış. Lütfen .env dosyasını kontrol edin."}, ensure_ascii=False)
            
            # Gemini API'yi yapılandır
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel(model_name="gemini-1.5-pro")
            logging.debug("Gemini model oluşturuldu")
            
            # Dil ayarları için ek metin
            dil_talimat = ""
            if hedef_dil == "otomatik":
                dil_talimat = "Ses hangi dilde ise transkriptin de o dilde olmasını sağla. Ses dilini otomatik algıla ve tüm çıktıyı o dilde yaz."
            elif hedef_dil != "otomatik":
                dil_talimat = f"Tüm çıktıyı {hedef_dil} dilinde yaz. Ses farklı dilde olsa bile, transkript ve analiz {hedef_dil} dilinde olmalı."
            
            if cikti_tipi == "transkript":
                prompt = f"""
                {dil_talimat}
                
                Bu ses dosyasını yazıya çevir (transkripsiyon yap). Aşağıdaki formatta JSON cevap ver:

                {{
                    "ses_dili": "Algılanan ses dili",
                    "sure": "Tahmini ses süresi (dakika:saniye formatında)",
                    "transkript": "Sesin tam yazıya çevrilmiş hali, noktalama işaretleri ve paragraflarla düzenlenmiş",
                    "konusmaci_sayisi": "Tespit edilen konuşmacı sayısı (tahmini)",
                    "kalite_degerlendirmesi": "Ses kalitesi değerlendirmesi (iyi/orta/zayıf)",
                    "anahtar_kelimeler": ["kelime1", "kelime2", "kelime3"]
                }}

                Lütfen yanıtını sadece JSON formatında ver, başka metin ekleme.
                ÖNEMLİ: Transkriptte konuşmacılar varsa [Konuşmacı 1], [Konuşmacı 2] şeklinde ayır.
                """
            elif cikti_tipi == "ozet":
                prompt = f"""
                {dil_talimat}
                
                Bu ses dosyasını önce yazıya çevir, sonra detaylı analiz et. Aşağıdaki formatta JSON cevap ver:

                {{
                    "ses_dili": "Algılanan ses dili",
                    "sure": "Tahmini ses süresi (dakika:saniye formatında)",
                    "baslik": "Ses kaydının ana konusu veya başlığı",
                    "kisa_transkript": "Sesin kısaltılmış yazıya çevrilmiş hali",
                    "detayli_ozet": "Ses içeriğinin çok detaylı özeti, tüm önemli noktalar paragraflar halinde",
                    "onemli_noktalar": ["VURGULU: Önemli nokta 1", "VURGULU: Önemli nokta 2", "VURGULU: Önemli nokta 3"],
                    "zaman_damgalari": [
                        {{"zaman": "0:00-2:30", "konu": "Giriş ve tanıtım", "onem": "orta"}},
                        {{"zaman": "2:30-5:15", "konu": "Ana konu açıklaması", "onem": "yuksek"}},
                        {{"zaman": "5:15-8:00", "konu": "Örnekler ve detaylar", "onem": "yuksek"}}
                    ],
                    "konusmaci_analizi": {{
                        "konusmaci_sayisi": "Tespit edilen konuşmacı sayısı",
                        "konusmaci_rolleri": ["Sunan", "Konuk", "Moderatör"],
                        "konusma_tarzi": "Ses tonunun analizi (resmi/gayri resmi/eğitici)"
                    }},
                    "icerik_kategorisi": "Ses kaydının kategorisi (ders, sunum, röportaj, podcast vb.)",
                    "hedef_kitle": "Bu ses kaydının hedef kitlesi",
                    "anahtar_kelimeler": ["kelime1", "kelime2", "kelime3", "kelime4", "kelime5"],
                    "etiketler": ["#etiket1", "#etiket2", "#etiket3"],
                    "ogrenme_ciktilari": ["Bu ses kaydını dinledikten sonra öğreneceğiniz şey 1", "şey 2", "şey 3"],
                    "ses_sonrasi_ogrenilecekler": "Bu ses kaydını dinledikten sonra şunları öğrenmiş olacaksınız: (detaylı açıklama)",
                    "bahsedilen_kaynaklar": ["Ses kaydında bahsedilen kitap/makale/website 1", "kaynak 2"],
                    "ilgili_konular": ["İlgili konu 1", "İlgili konu 2", "İlgili konu 3"]
                }}

                ÖNEMLİ NOTLAR:
                - Önemli noktaları "VURGULU:" başlığıyla işaretle
                - Zaman damgalarını mümkün olduğunca doğru tahmin et
                - Eğitim değeri yüksek olan kısımları özellikle vurgula
                - Lütfen yanıtını sadece JSON formatında ver, başka metin ekleme.
                """
            
            # AI'dan yanıt al (asenkron)
            logging.debug("Gemini API'ye istek gönderiliyor...")
            response = await anyio.to_thread.run_sync(model.generate_content, [ses_dosyasi, prompt])
            logging.debug("Gemini API yanıtı alındı")
            
            if not response.text:
                logging.error("Gemini API'den boş yanıt geldi")
                return json.dumps({"durum": "Hata", "mesaj": "AI'dan yanıt alınamadı. Lütfen tekrar deneyin."}, ensure_ascii=False)
            
            # JSON yanıtını parse et
            try:
                transkript_data = json.loads(response.text)
                logging.info("AI yanıtı başarıyla parse edildi")
                logging.debug(f"Parse edilen veri anahtarları: {list(transkript_data.keys())}")
            except json.JSONDecodeError as json_error:
                logging.error(f"JSON parse hatası: {str(json_error)}")
                logging.debug(f"Ham AI yanıtı: {response.text[:500]}...")
                # JSON parse hatası durumunda yedek yanıt
                transkript_data = {
                    "ses_dili": "Tespit edilemedi",
                    "sure": "Bilinmiyor",
                    "ham_yanit": response.text,
                    "parse_hatasi": "AI yanıtı JSON formatında değil, ham yanıt ham_yanit alanında bulunuyor."
                }
                
        except Exception as ai_error:
            logging.error(f"AI transkripsiyon hatası: {str(ai_error)}")
            return json.dumps({"durum": "Hata", "mesaj": f"AI transkripsiyon oluşturulamadı: {str(ai_error)}"}, ensure_ascii=False)

        # Temizlik (asenkron)
        try:
            logging.info("Yüklenen ses dosyası API'den siliniyor...")
            await anyio.to_thread.run_sync(genai.delete_file, ses_dosyasi.name)
            logging.info(f"Yüklenen dosya ({ses_dosyasi.name}) API'den başarıyla silindi")
        except Exception as delete_error:
            logging.warning(f"API'den dosya silme hatası: {str(delete_error)}")

        logging.info("Ses transkripsiyon işlemi başarıyla tamamlandı")
        return json.dumps({"durum": "Başarılı", "ses_analizi": transkript_data}, ensure_ascii=False)

    except Exception as e:
        logging.error(f"Beklenmeyen hata: {str(e)}", exc_info=True)
        logging.debug(f"Hata türü: {type(e).__name__}")
        return json.dumps({"durum": "Hata", "mesaj": f"Beklenmeyen bir hata oluştu: {str(e)}"}, ensure_ascii=False)

@mcp.tool(tags={"public"})
async def ses_dosyasini_transkript_et(ses_dosyasi_yolu: str, cikti_tipi: str = "ozet", hedef_dil: str = "otomatik") -> str:
    """
    GELİŞMİŞ SES TRANSKRİPSİYON AJANI - Verilen ses dosyasını yazıya çevirir ve detaylı analiz yapar.

    Kullanıcı "bu ses dosyasını yazıya çevir", "ses kaydını transkript et" veya ses analizi istediğinde bu aracı kullan.

    Args:
        ses_dosyasi_yolu (str): Transkript edilecek ses dosyasının yolu.
        cikti_tipi (str): Çıktı türü - "transkript" (sadece yazıya çevirme), "ozet" (transkript + detaylı analiz + önemli noktalar vurgulamalı). Varsayılan: "ozet"
        hedef_dil (str): Çıktının hangi dilde olmasını istediğiniz - "otomatik" (ses dilinde), "Türkçe", "İngilizce", "Almanca" vb. Varsayılan: "otomatik"
    
    Returns:
        str: Ses dosyasının transkript ve analizini içeren bir JSON string'i. İçerik:
        - Ses dilini otomatik algılama
        - Tam transkripsiyon (konuşmacı ayrımıyla)
        - Zaman damgaları ile önemli anlar
        - VURGULU önemli noktalar
        - Konuşmacı analizi ve ses tonunu değerlendirme
        - Bahsedilen kaynaklar
        - Anahtar kelimeler ve etiketler
        - Bu ses kaydını dinleyerek öğrenilecek çıktılar
        - Detaylı analiz ve öğrenme noktaları
        - Ses sonrası öğrenilecekler özeti
        
    Desteklenen formatlar: MP3, WAV, FLAC, M4A, AAC, OGG, WebM
    """
    logging.info("ses_dosyasini_transkript_et async tool'u çağrıldı")
    # Bu fonksiyon, asıl işi yapan asenkron logic fonksiyonunu çağırır.
    return await _ses_transkript_logic(ses_kaynagi=ses_dosyasi_yolu, cikti_tipi=cikti_tipi, hedef_dil=hedef_dil)

