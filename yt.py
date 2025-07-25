import os
import time
import re
from pytube import YouTube

def video_indir(url, indirme_yolu="./indirilmis_videolar"):
    """
    YouTube'dan video indiren basit fonksiyon
    
    Args:
        url (str): YouTube video URL'si
        indirme_yolu (str): Videonun indirileceği klasör yolu
    
    Returns:
        str: İndirilen dosyanın tam yolu veya hata mesajı
    """
    try:
        # İndirme klasörünü oluştur
        os.makedirs(indirme_yolu, exist_ok=True)
        
        # URL'yi temizle - yaygın parametreleri kaldır
        temiz_url = url.split('&')[0].split('?si=')[0]
        print(f"Temizlenmiş URL: {temiz_url}")
        
        # YouTube nesnesini oluştur - ek parametrelerle
        print("YouTube nesnesine bağlanılıyor...")
        yt = YouTube(
            temiz_url,
            use_oauth=False,
            allow_oauth_cache=False
        )
        
        # Biraz bekle - rate limiting için
        time.sleep(1)
        
        print(f"Video bilgileri alınıyor...")
        print(f"Video başlığı: {yt.title}")
        print(f"Kanal: {yt.author}")
        print(f"Süre: {yt.length} saniye")
        
        # Kullanılabilir stream'leri listele
        print("Kullanılabilir stream'ler:")
        for stream in yt.streams.filter(progressive=True, file_extension='mp4'):
            print(f"  - {stream.resolution} ({stream.mime_type})")
        
        # Önce progressive mp4 stream'i dene
        video_stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
        
        if not video_stream:
            # Eğer progressive bulunamazsa, en yüksek kaliteli adaptive stream'i al
            print("Progressive stream bulunamadı, adaptive stream deneniyor...")
            video_stream = yt.streams.filter(adaptive=True, file_extension='mp4').order_by('resolution').desc().first()
        
        if not video_stream:
            # Son çare olarak herhangi bir video stream'i al
            print("Adaptive stream bulunamadı, herhangi bir video stream'i deneniyor...")
            video_stream = yt.streams.filter(only_video=True).first()
        
        if not video_stream:
            raise Exception("Hiçbir video stream'i bulunamadı")
        
        print(f"Seçilen stream: {video_stream.resolution} - {video_stream.mime_type}")
        
        # Dosya ismini güvenli hale getir
        guvenli_baslik = re.sub(r'[<>:"/\\|?*]', '_', yt.title)
        
        print("Video indiriliyor...")
        # Videoyu indir
        indirilen_dosya = video_stream.download(
            output_path=indirme_yolu,
            filename=f"{guvenli_baslik}.{video_stream.subtype}"
        )
        
        print(f"Video başarıyla indirildi: {indirilen_dosya}")
        return indirilen_dosya
        
    except Exception as e:
        hata_mesaji = f"Video indirme hatası: {str(e)}"
        print(hata_mesaji)
        print("Olası çözümler:")
        print("1. URL'nin doğru olduğundan emin olun")
        print("2. İnternet bağlantınızı kontrol edin")
        print("3. Video özel veya kısıtlı olabilir")
        print("4. pytube kütüphanesini güncelleyin: pip install --upgrade pytube")
        return hata_mesaji

# Kullanım örneği
if __name__ == "__main__":
    # YouTube video URL'sini buraya koy
    video_url = input("YouTube video URL'sini giriniz: ")
    
    if video_url:
        sonuc = video_indir(video_url)
        print(f"İşlem sonucu: {sonuc}")
    else:
        print("Geçerli bir URL giriniz!")
