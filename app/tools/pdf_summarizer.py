import os
import json
import asyncio  # Asenkron operasyonlar için temel kütüphane
import time
import anyio
import logging
import google.generativeai as genai
from app.config import GEMINI_API_KEY
from app.server import mcp

# Ortak klasör yolu
SHARED_UPLOADS_DIR = r'C:\mcpler\education_mcp\shared_uploads'

async def _pdf_ozetle_logic(pdf_dosyasi_yolu: str, ozet_tipi: str = "kisa", hedef_dil: str = "otomatik") -> str:
    """PDF özetlemenin tüm çekirdek mantığını içeren, test edilebilir ve asenkron çalışan fonksiyon."""
    logging.info("Asenkron PDF özetleme işlemi başlatıldı")
    logging.debug(f"Gelen parametreler - pdf_dosyasi_yolu: {pdf_dosyasi_yolu}, ozet_tipi: {ozet_tipi}, hedef_dil: {hedef_dil}")
    
    if not pdf_dosyasi_yolu:
        logging.warning("PDF dosya yolu sağlanmadı")
        return json.dumps({"durum": "Hata", "mesaj": "Bir PDF dosya yolu sağlamalısınız."}, ensure_ascii=False)

    # Dosya yolunu işle - tam yoldan sadece dosya adını al
    if os.path.sep in pdf_dosyasi_yolu:
        # Tam yol verilmiş, sadece dosya adını al
        dosya_adi = os.path.basename(pdf_dosyasi_yolu)
        logging.info(f"Tam yol verildi, dosya adı çıkarıldı: {dosya_adi}")
    else:
        # Sadece dosya adı verilmiş
        dosya_adi = pdf_dosyasi_yolu
        logging.info(f"Sadece dosya adı verildi: {dosya_adi}")
    
    # Dosya yolunu ortak klasörden oluştur
    full_pdf_path = os.path.join(SHARED_UPLOADS_DIR, dosya_adi)
    logging.info(f"PDF dosyası aranıyor: {full_pdf_path}")

    try:
        # Dosya varlığını kontrol et (asenkron)
        if not await anyio.to_thread.run_sync(os.path.exists, full_pdf_path):
            logging.error(f"PDF dosyası bulunamadı: {full_pdf_path}")
            return json.dumps({"durum": "Hata", "mesaj": f"PDF dosyası bulunamadı: {dosya_adi}. Ortak klasörde dosya var mı kontrol edin."}, ensure_ascii=False)
        
        # Dosya uzantısını kontrol et
        if not full_pdf_path.lower().endswith('.pdf'):
            logging.error(f"Dosya PDF formatında değil: {full_pdf_path}")
            return json.dumps({"durum": "Hata", "mesaj": "Sadece PDF dosyaları desteklenmektedir."}, ensure_ascii=False)
        
        # Dosya boyutu kontrolü (asenkron)
        dosya_boyutu = await anyio.to_thread.run_sync(os.path.getsize, full_pdf_path)
        logging.debug(f"PDF dosya boyutu: {dosya_boyutu} bytes")
        if dosya_boyutu > 50 * 1024 * 1024:  # 50MB
            logging.warning(f"PDF çok büyük: {dosya_boyutu} bytes")
            return json.dumps({"durum": "Hata", "mesaj": "PDF dosyası çok büyük (50MB sınırı). Daha küçük bir dosya deneyin."}, ensure_ascii=False)

        # Gemini API'ye yükleme (asenkron)
        try:
            logging.info(f"PDF Gemini API'ye yükleniyor: {full_pdf_path}")
            # genai.upload_file'ı anyio ile asenkron çalıştır
            def upload_pdf():
                return genai.upload_file(path=full_pdf_path, mime_type="application/pdf")
            
            pdf_file = await anyio.to_thread.run_sync(upload_pdf)
            logging.info(f"Yükleme başladı: {pdf_file.name}. İşlenmesi bekleniyor...")
            logging.debug(f"PDF dosyası durumu: {pdf_file.state.name}")
        except Exception as upload_error:
            logging.error(f"Gemini API yükleme hatası: {str(upload_error)}")
            return json.dumps({"durum": "Hata", "mesaj": f"PDF Gemini API'ye yüklenemedi: {str(upload_error)}"}, ensure_ascii=False)

        # PDF işleme bekleme (asenkron)
        progress_counter = 0
        max_wait_time = 180  # 3 dakika maksimum bekleme (PDF'ler daha uzun sürebilir)
        while pdf_file.state.name == "PROCESSING" and progress_counter < max_wait_time // 5:
            progress_counter += 1
            print('.', end='', flush=True)
            logging.debug(f"İşleme devam ediyor... ({progress_counter * 5} saniye geçti)")
            # asyncio.sleep ile asenkron bekleme
            await asyncio.sleep(5)
            pdf_file = await anyio.to_thread.run_sync(genai.get_file, pdf_file.name)

        print()  # Satır sonu için
        logging.info(f"PDF işleme tamamlandı. Final durumu: {pdf_file.state.name}")

        if pdf_file.state.name == "FAILED":
            logging.error(f"PDF yüklemesi başarısız oldu: {pdf_file.error}")
            return json.dumps({"durum": "Hata", "mesaj": f"PDF işleme başarısız: {pdf_file.error}"}, ensure_ascii=False)
        
        if pdf_file.state.name == "PROCESSING":
            logging.error("PDF işleme zaman aşımına uğradı")
            return json.dumps({"durum": "Hata", "mesaj": "PDF işleme çok uzun sürdü. Daha küçük bir dosya deneyin."}, ensure_ascii=False)

        # AI özet oluşturma (asenkron)
        try:
            logging.info(f"PDF başarıyla işlendi. AI özet oluşturma başlıyor... Tip: {ozet_tipi}, Hedef dil: {hedef_dil}")
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
                dil_talimat = "PDF hangi dilde ise özetin de o dilde olmasını sağla. PDF'in dilini otomatik algıla ve özetin tamamını o dilde yaz."
            elif hedef_dil != "otomatik":
                dil_talimat = f"Özetin tamamını {hedef_dil} dilinde yaz. PDF farklı dilde olsa bile, özet {hedef_dil} dilinde olmalı."
            
            if ozet_tipi == "kisa":
                prompt = f"""
                {dil_talimat}
                
                Bu PDF belgesini kısaca özetle. Sadece aşağıdaki formatta JSON cevap ver:

                {{
                    "belge_dili": "Algılanan belge dili",
                    "baslik": "Belgenin başlığı veya ana konusu",
                    "kisa_ozet": "2-3 cümle halinde belgenin ana fikri ve en önemli noktaları",
                    "anahtar_kelimeler": ["kelime1", "kelime2", "kelime3"],
                    "ogrenme_ciktilari": ["Bu belgeyi okuduktan sonra öğreneceğiniz şey 1", "şey 2"],
                    "belge_sonrasi_ogrenilecekler": "Bu belgeyi okuduktan sonra şunları öğrenmiş olacaksınız: (kısa bir özet)"
                }}

                Lütfen yanıtını sadece JSON formatında ver, başka metin ekleme.
                """
            elif ozet_tipi == "genis":
                prompt = f"""
                {dil_talimat}
                
                Bu PDF belgesini detaylı şekilde analiz et. Aşağıdaki formatta JSON cevap ver:

                {{
                    "belge_dili": "Algılanan belge dili",
                    "baslik": "Belgenin başlığı ve ana konusu",
                    "genis_ozet": "Belgenin çok detaylı içeriği, tüm önemli bölümler ve açıklamaları paragraflar halinde",
                    "sayfa_ozetleri": [
                        {{"sayfa": "1-5", "konu": "Giriş bölümü", "aciklama": "Bu sayfalarda belgenin giriş kısmı ve temel kavramlar açıklanıyor"}},
                        {{"sayfa": "6-12", "konu": "Ana içerik", "aciklama": "Bu bölümde belgenin ana konusu detaylı olarak işleniyor"}}
                    ],
                    "kilit_ogrenme_noktalari": ["Detaylı madde 1", "Detaylı madde 2", "Detaylı madde 3", "..."],
                    "tablolar_ve_grafikler": ["Belgede bulunan tablo/grafik açıklaması 1", "görsel 2"],
                    "bahsedilen_kaynaklar": ["Kitap/makale/website adı 1", "kaynak 2"],
                    "ilgili_konular": ["İlgili konu 1", "İlgili konu 2", "İlgili konu 3"],
                    "anahtar_kelimeler": ["kelime1", "kelime2", "kelime3", "kelime4", "kelime5"],
                    "etiketler": ["#etiket1", "#etiket2", "#etiket3"],
                    "ogrenme_ciktilari": ["Bu belgeyi okuduktan sonra öğreneceğiniz şey 1", "şey 2", "şey 3"],
                    "belge_sonrasi_ogrenilecekler": "Bu belgeyi okuduktan sonra şunları öğrenmiş olacaksınız: (detaylı açıklama)"
                }}

                Lütfen yanıtını sadece JSON formatında ver, başka metin ekleme.
                """
            elif ozet_tipi == "kapsamli":  # kapsamli (varsayılan)
                prompt = f"""
                {dil_talimat}
                
                Bu PDF belgesini bir öğrenciye ders materyali anlatır gibi analiz et. Aşağıdaki formatta bir özet çıkar ve cevabını JSON formatında ver:

                {{
                    "belge_dili": "Algılanan belge dili (örn: Türkçe, İngilizce, vs.)",
                    "baslik": "Belgenin başlığı ve ana konusu",
                    "belge_tipi": "Akademik makale/ders notu/kitap bölümü/rapor/sunum/vb.",
                    "kisa_ozet": "Tek paragraf halinde belgenin ana fikri ve önemli noktaları",
                    "genis_ozet": "Belgenin detaylı içeriği, öğrenme çıktıları ve önemli noktaları paragraflar halinde",
                    "sayfa_ozetleri": [
                        {{"sayfa": "1-3", "konu": "Giriş ve amaç", "aciklama": "Belgenin başında amacı, kapsamı ve metodolojisi açıklanıyor"}},
                        {{"sayfa": "4-8", "konu": "Literatür taraması", "aciklama": "Bu bölümde konu ile ilgili mevcut çalışmalar ve kuramsal çerçeve sunuluyor"}},
                        {{"sayfa": "9-15", "konu": "Ana bulgular", "aciklama": "Belgenin ana içeriği ve önemli bulgular bu bölümde detaylandırılıyor"}},
                        {{"sayfa": "16-20", "konu": "Sonuç ve öneriler", "aciklama": "Çalışmanın sonuçları ve gelecek çalışmalar için öneriler sunuluyor"}}
                    ],
                    "kilit_ogrenme_noktalari": ["Madde 1", "Madde 2", "Madde 3", "..."],
                    "tablolar_ve_grafikler": ["Belgede bulunan tablo/grafik/şekil açıklaması", "İkinci görsel açıklaması"],
                    "bahsedilen_kaynaklar": ["Belgede atıf yapılan kitap/makale/kaynak 1", "İkinci kaynak"],
                    "metodoloji": "Belge eğer araştırma içeriyorsa kullanılan yöntem ve yaklaşım",
                    "ilgili_konular": ["Konu 1", "Konu 2", "Konu 3"],
                    "anahtar_kelimeler": ["kelime1", "kelime2", "kelime3", "kelime4", "kelime5"],
                    "etiketler": ["#etiket1", "#etiket2", "#etiket3"],
                    "ogrenme_ciktilari": ["Bu belgeyi okuduktan sonra şunu öğrenmiş olacaksınız", "İkinci öğrenme çıktısı", "Üçüncü beceri"],
                    "belge_sonrasi_ogrenilecekler": "Bu belgeyi okuduktan sonra şunları öğrenmiş olacaksınız: (kapsamlı özet)",
                    "yazar_bilgileri": {{
                        "yazarlar": "Belgenin yazarları (varsa)",
                        "kurum": "Yazarların bağlı olduğu kurum (varsa)",
                        "yayim_tarihi": "Belgenin yayım tarihi (varsa)",
                        "yayin_yeri": "Dergi/konferans/yayınevi adı (varsa)"
                    }},
                    "alinti_onerileri": [
                        "Bu belgedeki önemli alıntı 1",
                        "Önemli alıntı 2"
                    ]
                }}

                Özel olarak dikkat et:
                - Sayfa özetleri için belgedeki gerçek sayfa numaralarını kullan
                - Her önemli bölüm için sayfa aralığı belirt
                - Belgenin farklı bölümlerinde vurgulanan ana fikirleri ayrı ayrı not et
                - Tablolar, grafikler, şekiller varsa bunları da açıkla
                - Kaynakça ve referansları listele
                - "belge_sonrasi_ogrenilecekler" alanında bu belgeyi tamamen okuyan bir kişinin hangi bilgi ve becerileri kazanacağını özetle
                - Önemli alıntıları ve anahtar cümleleri not et

                Lütfen yanıtını sadece JSON formatında ver, başka metin ekleme.
                """
            
            logging.info("AI'dan PDF özeti isteniyor (asenkron)...")
            # model.generate_content anyio ile asenkron çalıştırılır
            response = await anyio.to_thread.run_sync(model.generate_content, [prompt, pdf_file])
            logging.info("AI PDF özeti başarıyla oluşturuldu")
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
                        "belge_dili": "Algılanamadı",
                        "baslik": "PDF İçeriği",
                        "kisa_ozet": response.text,
                        "anahtar_kelimeler": [],
                        "ogrenme_ciktilari": [],
                        "belge_sonrasi_ogrenilecekler": "Bu belgeyi okuduktan sonra çeşitli bilgiler edinmiş olacaksınız."
                    }
                elif ozet_tipi == "genis":
                    ozet_data = {
                        "belge_dili": "Algılanamadı",
                        "baslik": "PDF İçeriği",
                        "genis_ozet": response.text,
                        "sayfa_ozetleri": [],
                        "kilit_ogrenme_noktalari": [],
                        "tablolar_ve_grafikler": [],
                        "bahsedilen_kaynaklar": [],
                        "ilgili_konular": [],
                        "anahtar_kelimeler": [],
                        "etiketler": [],
                        "ogrenme_ciktilari": [],
                        "belge_sonrasi_ogrenilecekler": "Bu belgeyi okuduktan sonra konu hakkında detaylı bilgiler edinmiş olacaksınız."
                    }
                else:
                    ozet_data = {
                        "belge_dili": "Algılanamadı",
                        "baslik": "PDF İçeriği",
                        "belge_tipi": "Bilinmiyor",
                        "kisa_ozet": "PDF analizi tamamlandı fakat yapılandırılmış format oluşturulamadı.",
                        "genis_ozet": response.text,
                        "sayfa_ozetleri": [],
                        "kilit_ogrenme_noktalari": [],
                        "tablolar_ve_grafikler": [],
                        "bahsedilen_kaynaklar": [],
                        "metodoloji": "Bilinmiyor",
                        "ilgili_konular": [],
                        "anahtar_kelimeler": [],
                        "etiketler": [],
                        "ogrenme_ciktilari": [],
                        "belge_sonrasi_ogrenilecekler": "Bu belgeyi okuduktan sonra çeşitli konularda bilgi ve beceriler edinmiş olacaksınız.",
                        "yazar_bilgileri": {
                            "yazarlar": "Bilinmiyor",
                            "kurum": "Bilinmiyor",
                            "yayim_tarihi": "Bilinmiyor",
                            "yayin_yeri": "Bilinmiyor"
                        },
                        "alinti_onerileri": []
                    }
                
        except Exception as ai_error:
            logging.error(f"AI PDF özet oluşturma hatası: {str(ai_error)}")
            return json.dumps({"durum": "Hata", "mesaj": f"AI PDF özeti oluşturulamadı: {str(ai_error)}"}, ensure_ascii=False)

        # Temizlik (asenkron)
        try:
            logging.info("Yüklenen PDF dosyası API'den siliniyor...")
            await anyio.to_thread.run_sync(genai.delete_file, pdf_file.name)
            logging.info(f"Yüklenen dosya ({pdf_file.name}) API'den başarıyla silindi")
        except Exception as delete_error:
            logging.warning(f"API'den dosya silme hatası: {str(delete_error)}")

        logging.info("PDF özetleme işlemi başarıyla tamamlandı")
        return json.dumps({"durum": "Başarılı", "belge_analizi": ozet_data}, ensure_ascii=False)

    except Exception as e:
        logging.error(f"Beklenmeyen hata: {str(e)}", exc_info=True)
        logging.debug(f"Hata türü: {type(e).__name__}")
        return json.dumps({"durum": "Hata", "mesaj": f"Beklenmeyen bir hata oluştu: {str(e)}"}, ensure_ascii=False)

@mcp.tool(tags={"public"})
async def pdf_ozetle(pdf_dosyasi_yolu: str, ozet_tipi: str = "kisa", hedef_dil: str = "otomatik") -> str:
    """
    GELİŞMİŞ PDF ÖZETLEME AJANI - Verilen bir PDF belgesinin içeriğini sayfa özetleri, tablolar, kaynaklar ve alıntılar ile birlikte eğitim odaklı olarak özetler.

    Kullanıcı "bu PDF'i özetle", "belgedeki önemli noktalar neler?", "bu makaleyi analiz et" veya bir PDF dosya yolu verdiğinde bu aracı kullan.

    Args:
        pdf_dosyasi_yolu (str): Özetlenecek PDF dosyasının tam yolu.
        ozet_tipi (str): Özet türü - "kisa" (sadece kısa özet), "genis" (sadece detaylı özet), "kapsamli" (her ikisi de + sayfa özetleri). Varsayılan: "kapsamli"
        hedef_dil (str): Özetin hangi dilde olmasını istediğiniz - "otomatik" (belge dilinde), "Türkçe", "İngilizce", "Almanca" vb. Varsayılan: "otomatik"
    
    Returns:
        str: PDF'in gelişmiş özetini içeren bir JSON string'i. İçerik:
        - Belge dilini otomatik algılama
        - Sayfa özetleri ile önemli bölümler (örn: "1-5: Giriş bölümü")
        - Tablolar ve grafikler açıklamaları
        - Bahsedilen kaynaklar ve referanslar
        - Anahtar kelimeler ve etiketler
        - Bu belgeyi okuyarak öğrenilecek çıktılar
        - Detaylı analiz ve öğrenme noktaları
        - Metodoloji (varsa)
        - Yazar bilgileri ve yayın detayları
        - Önemli alıntılar ve anahtar cümleler
        - Belge sonrası öğrenilecekler özeti
    """
    logging.info("pdf_ozetle async tool'u çağrıldı")
    # Bu fonksiyon, asıl işi yapan asenkron logic fonksiyonunu çağırır.
    return await _pdf_ozetle_logic(pdf_dosyasi_yolu=pdf_dosyasi_yolu, ozet_tipi=ozet_tipi, hedef_dil=hedef_dil)

