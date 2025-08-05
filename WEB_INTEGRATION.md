# Web Entegrasyonu Kullanım Kılavuzu

Bu doküman, web sitesinden dosya yükleme ve MCP araçlarıyla işleme sürecini açıklar.

## Sistem Mimarisi

```
Web Site → Flask Server → MCP Tools → Gemini AI → Sonuç
```

## 1. Flask Server Başlatma

```bash
# Flask server'ı başlat (port 5000)
python flask_server.py

# MCP server'ı başlat (port 8000) 
python main.py
```

## 2. API Endpoint'leri

### Dosya Yükleme
```http
POST /upload-file
Content-Type: multipart/form-data

Form Data:
- file: Dosya
- file_type: "pdf" | "audio" | "video"
```

**Örnek Response:**
```json
{
  "success": true,
  "file_path": "mcp_uploads/pdf_20241201_143022_abc123.pdf",
  "file_type": "pdf",
  "original_filename": "document.pdf",
  "file_size": 1024000,
  "upload_time": "2024-12-01T14:30:22"
}
```

### Dosya İşleme
```http
POST /process-file
Content-Type: application/json

{
  "file_path": "mcp_uploads/pdf_20241201_143022_abc123.pdf",
  "file_type": "pdf",
  "options": {
    "ozet_tipi": "kapsamli",
    "hedef_dil": "Türkçe"
  }
}
```

### Dosya Temizleme
```http
POST /cleanup-files
Content-Type: application/json

{
  "file_paths": [
    "mcp_uploads/pdf_20241201_143022_abc123.pdf"
  ]
}
```

## 3. Desteklenen Dosya Türleri

### PDF Dosyaları
- **Uzantılar:** `.pdf`
- **Maksimum boyut:** 50MB
- **İşlem:** Özetleme ve analiz

### Ses Dosyaları
- **Uzantılar:** `.mp3`, `.wav`, `.flac`, `.m4a`, `.aac`, `.ogg`, `.webm`
- **Maksimum boyut:** 100MB
- **İşlem:** Transkripsiyon ve analiz

### Video Dosyaları
- **Uzantılar:** `.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`, `.flv`
- **Maksimum boyut:** 100MB
- **İşlem:** Özetleme ve analiz

## 4. JavaScript Kullanım Örneği

```javascript
// Dosya yükleme
async function uploadFile(file, fileType) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('file_type', fileType);
    
    const response = await fetch('http://localhost:5000/upload-file', {
        method: 'POST',
        body: formData
    });
    
    return await response.json();
}

// Dosya işleme
async function processFile(filePath, fileType, options = {}) {
    const response = await fetch('http://localhost:5000/process-file', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            file_path: filePath,
            file_type: fileType,
            options: options
        })
    });
    
    return await response.json();
}

// Kullanım örneği
async function handleFileUpload() {
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];
    const fileType = 'pdf'; // veya 'audio', 'video'
    
    try {
        // 1. Dosyayı yükle
        const uploadResult = await uploadFile(file, fileType);
        console.log('Dosya yüklendi:', uploadResult);
        
        // 2. Dosyayı işle
        const processResult = await processFile(
            uploadResult.file_path, 
            uploadResult.file_type,
            {
                ozet_tipi: 'kapsamli',
                hedef_dil: 'Türkçe'
            }
        );
        console.log('İşlem sonucu:', processResult);
        
        // 3. Dosyayı temizle
        await fetch('http://localhost:5000/cleanup-files', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                file_paths: [uploadResult.file_path]
            })
        });
        
    } catch (error) {
        console.error('Hata:', error);
    }
}
```

## 5. MCP Tool'ları

### Web PDF Özetleme
```python
await web_pdf_ozetle(
    uploaded_file_path="mcp_uploads/pdf_20241201_143022_abc123.pdf",
    ozet_tipi="kapsamli",
    hedef_dil="Türkçe"
)
```

### Web Ses Transkripsiyon
```python
await web_ses_transkript_et(
    uploaded_file_path="mcp_uploads/audio_20241201_143022_abc123.mp3",
    cikti_tipi="ozet",
    hedef_dil="Türkçe"
)
```

### Web Video Özetleme
```python
await web_video_ozetle(
    uploaded_file_path="mcp_uploads/video_20241201_143022_abc123.mp4",
    ozet_tipi="kapsamli",
    hedef_dil="Türkçe"
)
```

## 6. Güvenlik Önlemleri

- Dosya uzantısı kontrolü
- Dosya boyutu sınırlaması
- Güvenli dosya adı oluşturma
- Geçici dosya temizleme
- CORS ayarları (gerekirse)

## 7. Hata Yönetimi

```javascript
// Hata durumları
const errorMessages = {
    'FILE_NOT_FOUND': 'Dosya bulunamadı',
    'INVALID_FILE_TYPE': 'Geçersiz dosya türü',
    'FILE_TOO_LARGE': 'Dosya çok büyük',
    'PROCESSING_ERROR': 'İşleme hatası'
};
```

## 8. Performans Optimizasyonu

- Asenkron dosya işleme
- Progress tracking
- Dosya boyutu kontrolü
- Otomatik temizlik
- Caching (gelecekte)

## 9. Test Etme

```bash
# Test dosyası yükleme
curl -X POST -F "file=@test.pdf" -F "file_type=pdf" http://localhost:5000/upload-file

# Test dosya işleme
curl -X POST -H "Content-Type: application/json" \
  -d '{"file_path":"mcp_uploads/test.pdf","file_type":"pdf","options":{"ozet_tipi":"kapsamli"}}' \
  http://localhost:5000/process-file
``` 