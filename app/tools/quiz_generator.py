import os
import json
import asyncio  # Asenkron operasyonlar için temel kütüphane
import time
import anyio
import logging
import requests
import google.generativeai as genai
from app.config import GEMINI_API_KEY
from app.server import mcp
from dotenv import load_dotenv

load_dotenv()

# Ortak klasör yolu
SHARED_UPLOADS_DIR = r'C:\mcpler\education_mcp\shared_uploads'


async def search_web(query, max_results=5):
    """Google Custom Search API ile web araması yap (asenkron)"""
    try:
        # Google Custom Search API ayarları
        GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
        GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")  # Custom Search Engine ID
        
        if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
            logging.warning("Google API anahtarları bulunamadı, web araması yapılamıyor")
            return []
        
        # API anahtarlarının geçerli olup olmadığını kontrol et
        if GOOGLE_API_KEY == "your_google_api_key_here" or GOOGLE_CSE_ID == "your_custom_search_engine_id_here":
            logging.warning("Google API anahtarları varsayılan değerlerde, web araması yapılamıyor")
            return []
        
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            'key': GOOGLE_API_KEY,
            'cx': GOOGLE_CSE_ID,  # Custom Search Engine ID
            'q': query,
            'num': max_results,
            'dateRestrict': 'm1',  # Son 1 ay
            'sort': 'date'  # Tarihe göre sırala
        }
        
        
        # requests.get'i anyio ile asenkron çalıştır
        def make_request():
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        
        data = await anyio.to_thread.run_sync(make_request)
        results = []
        
        if 'items' in data:
            for item in data['items']:
                results.append({
                    'title': item.get('title', ''),
                    'snippet': item.get('snippet', ''),
                    'link': item.get('link', ''),
                    'date': item.get('pagemap', {}).get('metatags', [{}])[0].get('article:published_time', '')
                })
        
        logging.info(f"Web araması tamamlandı: {len(results)} sonuç bulundu")
        return results
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Web arama network hatası: {str(e)}")
        return []
    except Exception as e:
        logging.error(f"Web arama genel hatası: {str(e)}")
        return []

async def _soru_olustur_logic(konu: str, soru_sayisi: int = 5, zorluk: str = "orta", soru_tipi: str = "karisik", web_arama: bool = False) -> str:
    """Verilen konuda soru oluşturmanın çekirdek mantığını içeren asenkron fonksiyon."""
    logging.info("Asenkron soru oluşturma işlemi başlatıldı")
    logging.debug(f"Gelen parametreler - konu: {konu}, soru_sayisi: {soru_sayisi}, zorluk: {zorluk}, soru_tipi: {soru_tipi}, web_arama: {web_arama}")
    
    if not konu or konu.strip() == "":
        logging.warning("Konu belirtilmedi")
        return json.dumps({"durum": "Hata", "mesaj": "Bir konu belirtmelisiniz."}, ensure_ascii=False)
    
    if soru_sayisi < 1 or soru_sayisi > 20:
        logging.warning(f"Geçersiz soru sayısı: {soru_sayisi}")
        return json.dumps({"durum": "Hata", "mesaj": "Soru sayısı 1 ile 20 arasında olmalıdır."}, ensure_ascii=False)
    
    zorluk_seviyeleri = ["kolay", "orta", "zor", "karisik"]
    if zorluk not in zorluk_seviyeleri:
        logging.warning(f"Geçersiz zorluk seviyesi: {zorluk}")
        return json.dumps({"durum": "Hata", "mesaj": f"Zorluk seviyesi şunlardan biri olmalıdır: {', '.join(zorluk_seviyeleri)}"}, ensure_ascii=False)
    
    soru_tipleri = ["test", "acik_uclu", "dogru_yanlis", "karisik"]
    if soru_tipi not in soru_tipleri:
        logging.warning(f"Geçersiz soru tipi: {soru_tipi}")
        return json.dumps({"durum": "Hata", "mesaj": f"Soru tipi şunlardan biri olmalıdır: {', '.join(soru_tipleri)}"}, ensure_ascii=False)

    try:
        # Web araması yap (asenkron)
        web_bilgileri = ""
        if web_arama:
            logging.info(f"'{konu}' konusunda web araması yapılıyor...")
            search_results = await search_web(f"{konu} güncel bilgiler 2024", max_results=3)
            
            if search_results:
                web_bilgileri = "\n\nGÜNCEL WEB BİLGİLERİ:\n"
                for i, result in enumerate(search_results, 1):
                    web_bilgileri += f"""
{i}. {result['title']}
   {result['snippet']}
   Kaynak: {result['link']}
   Tarih: {result['date'] if result['date'] else 'Bilinmiyor'}
"""
                logging.info("Web araması başarılı, güncel bilgiler eklendi")
            else:
                logging.warning("Web araması sonuç vermedi, sadece model bilgileri kullanılacak")
                web_bilgileri = "\n\nNot: Web araması yapılamadı, sadece model bilgileri kullanılacak."
        else:
            logging.info("Web araması devre dışı, sadece model bilgileri kullanılacak")
            web_bilgileri = "\n\nNot: Web araması devre dışı, sadece model bilgileri kullanılacak."
        
        logging.info(f"AI'dan {konu} konusunda {soru_sayisi} adet {zorluk} seviyesinde {soru_tipi} türünde sorular isteniyor...")
        if not GEMINI_API_KEY:
            logging.error("GEMINI_API_KEY bulunamadı")
            return json.dumps({"durum": "Hata", "mesaj": "API anahtarı yapılandırılmamış. Lütfen .env dosyasını kontrol edin."}, ensure_ascii=False)
        # Gemini API'yi yapılandır
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
        logging.debug("Gemini model oluşturuldu")
        
        # Zorluk seviyesi açıklamaları
        zorluk_aciklamasi = {
            "kolay": "Temel bilgi düzeyinde, basit kavramları test eden sorular",
            "orta": "Orta düzeyde anlama ve uygulama gerektiren sorular",
            "zor": "İleri düzeyde analiz, sentez ve değerlendirme gerektiren sorular",
            "karisik": "Farklı zorluk seviyelerinden karışık sorular"
        }
        
        # Soru tipi açıklamaları
        tip_aciklamasi = {
            "test": "Çoktan seçmeli sorular (A, B, C, D şıklı)",
            "acik_uclu": "Açık uçlu sorular (uzun cevap gerektiren)",
            "dogru_yanlis": "Doğru/Yanlış soruları",
            "karisik": "Farklı tiplerden karışık sorular"
        }
        
        prompt = f"""
        '{konu}' konusunda {soru_sayisi} adet eğitici soru oluştur.
        
        Özellikler:
        - Zorluk seviyesi: {zorluk} ({zorluk_aciklamasi[zorluk]})
        - Soru tipi: {soru_tipi} ({tip_aciklamasi[soru_tipi]})
        - Web araması: {'Aktif' if web_arama else 'Pasif'}
        
        {web_bilgileri}
        
        Aşağıdaki JSON formatında cevap ver:
        
        {{
            "konu": "{konu}",
            "soru_sayisi": {soru_sayisi},
            "zorluk_seviyesi": "{zorluk}",
            "soru_tipi": "{soru_tipi}",
            "web_arama_yapildi": {str(web_arama).lower()},
            "sorular": [
                {{
                    "soru_no": 1,
                    "tip": "test/acik_uclu/dogru_yanlis",
                    "zorluk": "kolay/orta/zor",
                    "soru": "Sorunun tam metni",
                    "secenekler": ["A) Seçenek 1", "B) Seçenek 2", "C) Seçenek 3", "D) Seçenek 4"],
                    "dogru_cevap": "A) Seçenek 1",
                    "aciklama": "Neden bu cevabın doğru olduğunun detaylı açıklaması",
                    "konular": ["Alt konu 1", "Alt konu 2"],
                    "ogrenme_hedefi": "Bu soruyla test edilen öğrenme hedefi",
                    "kaynak_bilgisi": "Bu soru için kullanılan kaynak (web aramasından geliyorsa belirt)"
                }},
                {{
                    "soru_no": 2,
                    "tip": "acik_uclu",
                    "zorluk": "orta",
                    "soru": "Açık uçlu sorunun tam metni",
                    "secenekler": [],
                    "dogru_cevap": "Örnek doğru cevap veya cevap anahtarı",
                    "aciklama": "Cevap kriterlerinin detaylı açıklaması",
                    "konular": ["Alt konu 1", "Alt konu 2"],
                    "ogrenme_hedefi": "Bu soruyla test edilen öğrenme hedefi",
                    "kaynak_bilgisi": "Bu soru için kullanılan kaynak"
                }},
                {{
                    "soru_no": 3,
                    "tip": "dogru_yanlis",
                    "zorluk": "kolay",
                    "soru": "Doğru/Yanlış sorusunun ifadesi",
                    "secenekler": ["Doğru", "Yanlış"],
                    "dogru_cevap": "Doğru",
                    "aciklama": "Neden doğru veya yanlış olduğunun açıklaması",
                    "konular": ["Alt konu 1"],
                    "ogrenme_hedefi": "Bu soruyla test edilen öğrenme hedefi",
                    "kaynak_bilgisi": "Bu soru için kullanılan kaynak"
                }}
            ],
            "genel_bilgiler": {{
                "toplam_puan": "Soruların toplam puanı",
                "sure_tahmini": "Çözüm için tahmini süre (dakika)",
                "konu_dagilimi": ["Ana konu 1: X soru", "Ana konu 2: Y soru"],
                "zorluk_dagilimi": ["Kolay: X soru", "Orta: Y soru", "Zor: Z soru"],
                "tavsiyeler": ["Çalışma tavsiyesi 1", "Tavsiye 2"],
                "kaynak_onerileri": ["Önerilen kaynak 1", "Kaynak 2"],
                "web_arama_sonuclari": {{
                    "arama_yapildi": {str(web_arama).lower()},
                    "bulunan_kaynak_sayisi": len(search_results) if web_arama else 0,
                    "kullanilan_kaynaklar": [result['link'] for result in search_results] if web_arama and search_results else []
                }}
            }}
        }}
        
        Önemli kurallar:
        1. Sorular akademik standartlarda ve net olmalı
        2. Çoktan seçmeli sorularda 4 seçenek olmalı ve sadece 1 tanesi doğru
        3. Açık uçlu sorularda "secenekler" boş array olmalı
        4. Doğru/Yanlış sorularında sadece "Doğru" ve "Yanlış" seçenekleri olmalı
        5. Her sorunun detaylı açıklaması olmalı
        6. Konuyla ilgili olmayan sorular sorma
        7. Her soru farklı bir alt konuyu kapsamalı
        8. Soruların zorluk seviyesi belirtilen kriterlere uymalı
        9. Türkçe dilbilgisi kurallarına dikkat et
        10. Öğretici ve eğitici içerik oluştur
        11. Web aramasından gelen güncel bilgileri kullan
        12. Güncel olaylar, yeni teknolojiler, son gelişmeler varsa bunları dahil et
        
        Lütfen yanıtını sadece JSON formatında ver, başka metin ekleme.
        """
        
        logging.info("AI'dan sorular isteniyor (asenkron)...")
        # model.generate_content anyio ile asenkron çalıştırılır
        response = await anyio.to_thread.run_sync(model.generate_content, prompt)
        logging.info("AI soruları başarıyla oluşturdu")
        logging.debug(f"Cevap uzunluğu: {len(response.text)} karakter")
        
        # JSON cevabını parse et
        try:
            # Gemini'nin cevabını temizle (markdown kod blokları varsa)
            clean_response = response.text.strip()
            if clean_response.startswith('```json'):
                clean_response = clean_response.replace('```json', '').replace('```', '').strip()
            elif clean_response.startswith('```'):
                clean_response = clean_response.replace('```', '').strip()
            
            soru_data = json.loads(clean_response)
            logging.info("AI cevabı başarıyla JSON formatında parse edildi")
            
        except json.JSONDecodeError as json_error:
            logging.error(f"AI cevabı JSON formatında parse edilemedi: {json_error}")
            # Fallback: Basit format kullan
            soru_data = {
                "konu": konu,
                "soru_sayisi": soru_sayisi,
                "zorluk_seviyesi": zorluk,
                "soru_tipi": soru_tipi,
                "web_arama_yapildi": web_arama,
                "sorular": [
                    {
                        "soru_no": 1,
                        "tip": "acik_uclu",
                        "zorluk": zorluk,
                        "soru": f"{konu} hakkında ne biliyorsunuz? Açıklayınız.",
                        "secenekler": [],
                        "dogru_cevap": "Konu hakkında temel bilgiler ve kavramların açıklanması beklenir.",
                        "aciklama": "Bu soru konuyla ilgili genel bilgi düzeyini ölçer.",
                        "konular": [konu],
                        "ogrenme_hedefi": "Konu hakkında temel bilgi düzeyini değerlendirmek",
                        "kaynak_bilgisi": "Model bilgileri"
                    }
                ],
                "genel_bilgiler": {
                    "toplam_puan": "100",
                    "sure_tahmini": "15 dakika",
                    "konu_dagilimi": [f"{konu}: {soru_sayisi} soru"],
                    "zorluk_dagilimi": [f"{zorluk.title()}: {soru_sayisi} soru"],
                    "tavsiyeler": ["Konuyu tekrar edin", "Örnekler üzerinde çalışın"],
                    "kaynak_onerileri": ["İlgili ders kitapları", "Online eğitim materyalleri"],
                    "web_arama_sonuclari": {
                        "arama_yapildi": web_arama,
                        "bulunan_kaynak_sayisi": len(search_results) if web_arama else 0,
                        "kullanilan_kaynaklar": [result['link'] for result in search_results] if web_arama and search_results else []
                    }
                }
            }
            
        logging.info("Soru oluşturma işlemi başarıyla tamamlandı")
        return json.dumps({"durum": "Başarılı", "soru_seti": soru_data}, ensure_ascii=False)

    except Exception as e:
        logging.error(f"Beklenmeyen hata: {str(e)}", exc_info=True)
        logging.debug(f"Hata türü: {type(e).__name__}")
        return json.dumps({"durum": "Hata", "mesaj": f"Beklenmeyen bir hata oluştu: {str(e)}"}, ensure_ascii=False)

@mcp.tool(tags={"public"})
async def soru_olustur(konu: str, soru_sayisi: int = 5, zorluk: str = "orta", soru_tipi: str = "karisik", web_arama: bool = False) -> str:
    """
    EĞİTİM SORU OLUŞTURMA AJANI - Verilen konuda akademik standartlarda sorular oluşturur ve detaylı cevap anahtarları sağlar.
    Web araması özelliği ile güncel bilgileri kullanır. kullanıcının istediği zaman web araması yapılabilir.

    Kullanıcı "bu konu hakkında soru sor", "test hazırla", "sınav soruları oluştur" dediğinde bu aracı kullan.

    Args:
        konu (str): Sorular oluşturulacak ana konu (örn: "Osmanlı Tarihi", "Matematik Integral", "İngilizce Present Perfect")
        soru_sayisi (int): Oluşturulacak soru adedi (1-20 arası). Varsayılan: 5
        zorluk (str): Zorluk seviyesi - "kolay", "orta", "zor", "karisik". Varsayılan: "orta"
        soru_tipi (str): Soru türü - "test" (çoktan seçmeli), "acik_uclu", "dogru_yanlis", "karisik". Varsayılan: "karisik"
        web_arama (bool): Web araması yapılıp yapılmayacağı - True/False. Varsayılan: True
    
    Returns:
        str: Oluşturulan soruları içeren bir JSON string'i. İçerik:
        - Konuya özel akademik sorular
        - Her soru için detaylı cevap açıklamaları
        - Çoktan seçmeli sorularda 4 seçenek
        - Soru zorluk seviyeleri ve tip bilgileri
        - Alt konu dağılımları
        - Öğrenme hedefleri
        - Çözüm süre tahminleri
        - Çalışma tavsiyeleri ve kaynak önerileri
        - Puanlama rehberi
        - Web arama sonuçları ve kullanılan kaynaklar
        - Güncel bilgiler ve son gelişmeler
    """
    logging.info("soru_olustur async tool'u çağrıldı")
    # Bu fonksiyon, asıl işi yapan asenkron logic fonksiyonunu çağırır.
    return await _soru_olustur_logic(konu=konu, soru_sayisi=soru_sayisi, zorluk=zorluk, soru_tipi=soru_tipi, web_arama=web_arama)

