import os
import json
import time
import logging
import google.generativeai as genai
from app.server import mcp
from app.config import GEMINI_API_KEY

def _soru_olustur_logic(konu: str, soru_sayisi: int = 5, zorluk: str = "orta", soru_tipi: str = "karisik") -> str:
    """Verilen konuda soru oluşturmanın çekirdek mantığını içeren fonksiyon."""
    logging.info("Soru oluşturma işlemi başlatıldı")
    logging.debug(f"Gelen parametreler - konu: {konu}, soru_sayisi: {soru_sayisi}, zorluk: {zorluk}, soru_tipi: {soru_tipi}")
    
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
        
        Aşağıdaki JSON formatında cevap ver:
        
        {{
            "konu": "{konu}",
            "soru_sayisi": {soru_sayisi},
            "zorluk_seviyesi": "{zorluk}",
            "soru_tipi": "{soru_tipi}",
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
                    "ogrenme_hedefi": "Bu soruyla test edilen öğrenme hedefi"
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
                    "ogrenme_hedefi": "Bu soruyla test edilen öğrenme hedefi"
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
                    "ogrenme_hedefi": "Bu soruyla test edilen öğrenme hedefi"
                }}
            ],
            "genel_bilgiler": {{
                "toplam_puan": "Soruların toplam puanı",
                "sure_tahmini": "Çözüm için tahmini süre (dakika)",
                "konu_dagilimi": ["Ana konu 1: X soru", "Ana konu 2: Y soru"],
                "zorluk_dagilimi": ["Kolay: X soru", "Orta: Y soru", "Zor: Z soru"],
                "tavsiyeler": ["Çalışma tavsiyesi 1", "Tavsiye 2"],
                "kaynak_onerileri": ["Önerilen kaynak 1", "Kaynak 2"]
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
        
        Lütfen yanıtını sadece JSON formatında ver, başka metin ekleme.
        """
        
        logging.info("AI'dan sorular isteniyor...")
        response = model.generate_content(prompt)
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
                        "ogrenme_hedefi": "Konu hakkında temel bilgi düzeyini değerlendirmek"
                    }
                ],
                "genel_bilgiler": {
                    "toplam_puan": "100",
                    "sure_tahmini": "15 dakika",
                    "konu_dagilimi": [f"{konu}: {soru_sayisi} soru"],
                    "zorluk_dagilimi": [f"{zorluk.title()}: {soru_sayisi} soru"],
                    "tavsiyeler": ["Konuyu tekrar edin", "Örnekler üzerinde çalışın"],
                    "kaynak_onerileri": ["İlgili ders kitapları", "Online eğitim materyalleri"]
                }
            }
            
        logging.info("Soru oluşturma işlemi başarıyla tamamlandı")
        return json.dumps({"durum": "Başarılı", "soru_seti": soru_data}, ensure_ascii=False)

    except Exception as e:
        logging.error(f"Beklenmeyen hata: {str(e)}", exc_info=True)
        logging.debug(f"Hata türü: {type(e).__name__}")
        return json.dumps({"durum": "Hata", "mesaj": f"Beklenmeyen bir hata oluştu: {str(e)}"}, ensure_ascii=False)

@mcp.tool(tags={"public"})
def soru_olustur(konu: str, soru_sayisi: int = 5, zorluk: str = "orta", soru_tipi: str = "karisik") -> str:
    """
    EĞİTİM SORU OLUŞTURMA AJANI - Verilen konuda akademik standartlarda sorular oluşturur ve detaylı cevap anahtarları sağlar.

    Kullanıcı "bu konu hakkında soru sor", "test hazırla", "sınav soruları oluştur" dediğinde bu aracı kullan.

    Args:
        konu (str): Sorular oluşturulacak ana konu (örn: "Osmanlı Tarihi", "Matematik Integral", "İngilizce Present Perfect")
        soru_sayisi (int): Oluşturulacak soru adedi (1-20 arası). Varsayılan: 5
        zorluk (str): Zorluk seviyesi - "kolay", "orta", "zor", "karisik". Varsayılan: "orta"
        soru_tipi (str): Soru türü - "test" (çoktan seçmeli), "acik_uclu", "dogru_yanlis", "karisik". Varsayılan: "karisik"
    
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
    """
    logging.info("soru_olustur tool'u çağrıldı")
    # Bu fonksiyon, asıl işi yapan logic fonksiyonunu çağırır.
    return _soru_olustur_logic(konu=konu, soru_sayisi=soru_sayisi, zorluk=zorluk, soru_tipi=soru_tipi)

