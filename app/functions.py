import os
import re
import yt_dlp


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
