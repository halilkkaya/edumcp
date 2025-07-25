# gemini_emlak_assistant.py
import os
import time
import json
import asyncio
import hashlib
from dotenv import load_dotenv

# --- 3p SDK'ler --------------------------------------------------------------
from google import genai                         # Google Gemini SDK
from google.genai import types
from fastmcp import Client                       # MCP istemcisi
# -----------------------------------------------------------------------------

load_dotenv()



# --------------------------- Ortam / Bağlantılar -----------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MCP_URL        = os.getenv("MCP_URL")      # ngrok vb. "https://.../mcp"

if not GEMINI_API_KEY or not MCP_URL:
    raise RuntimeError("GEMINI_API_KEY ve MCP_URL .env'de tanımlı olmalı!")

# Gemini istemcisi (asenkron API'ye ihtiyacımız var → .aio alt-modülü)
gemini = genai.Client(api_key=GEMINI_API_KEY)

# Uzak MCP sunucusuna bağlanacak FastMCP istemcisi
mcp_client = Client(
    MCP_URL
    # token yoksa BearerAuth'ı atlamak için koşullu ekle
    )

MCP = {
    "type": "url",
    "url": os.getenv("MCP_URL"),
    "name": "Eğitim Asistanı"
    }

# --------------------------- S# ===============================================
SYSTEM_PROMPT = """
Eğitim Asistanısın. Kullanıcının sorusuna cevap ver. gerekli toolları çağır.


"""

# --------------------------- Ana LLM Çağrısı ---------------------------------
async def ai_chat(messages, system_prompt):
    """
    Gemini + MCP ile sohbet
    """
    try:
        # 1) MCP oturumunu aç → session otomatik keşif + araç çağrıları
        async with mcp_client:
            # 2) Mesajları Gemini formatında düzenle
            content_list = []
            
            # Sistem promptu ilk kullanıcı mesajıyla birleştir
            if messages:
                first_user_msg = messages[0]["content"]
                system_with_user = f"{system_prompt}\n\nKullanıcı: {first_user_msg}"
                content_list.append(
                    types.Content(role="user", parts=[types.Part(text=system_with_user)])
                )
                
                # Geri kalan mesajları ekle
                for msg in messages[1:]:
                    role = "model" if msg["role"] == "assistant" else "user"
                    content_list.append(
                        types.Content(role=role, parts=[types.Part(text=msg["content"])])
                    )

            # 3) Gemini'ye istek gönder
            response = await gemini.aio.models.generate_content(
                model="gemini-2.5-pro",
                contents=content_list,
                config=types.GenerateContentConfig(
                    tools=[mcp_client.session],   # MCP araç listesini ekle
                    max_output_tokens=8192*2, 
                    temperature=0.5,
                )
            )

            print("Eğitim Asistanı: ", end="", flush=True)
            content_out = response.text if response.text else ""
            print(content_out)
            return content_out.strip()

    except Exception as e:
        print(f"Hata oluştu: {e}")
        return ""

# --------------------------- CLI Yardımcıları --------------------------------
def print_welcome():
    print("\n" + "="*62)
    print("           G E M I N I   E Ğ İ T İ M   A S İ S T A N I")
    print("="*62)
    print("-" * 62)



async def main():
    print_welcome()
    
    
    # Kullanıcı tercihlerini sistem mesajına ekle
    user_prefs_text = f"""

KULLANICI TERCİHLERİ:


Bu bilgileri dikkate alarak kullanıcıya yardımcı ol."""
    
    # İlk sistem mesajında chat_id'yi ve kullanıcı tercihlerini ekle
    system_message_with_id = SYSTEM_PROMPT + f"""



KRİTİK KURALLAR: 
- JSON verisini okunaklı formata çevir
- Sonuç yoksa sadece "Bulunamadı" de
"""
    
    messages = []
    
    # İlk hoşgeldin mesajı
    print("Eğitim Asistanı: Merhaba! Size nasıl yardımcı olabilirim? ")
    print("Örnek: 'Bu kriterlere uygun daire göster' veya 'Fiyat analizi yap'")
    print("-" * 62)
    
    while True:
        try:
            user_input = input("Kullanıcı: ").strip()
            if user_input.lower() == "/çıkış":
                print("Uygulamadan çıkılıyor...")
                break
            if not user_input:
                continue
                
            messages.append({"role": "user", "content": user_input})
            answer = await ai_chat(messages, system_message_with_id)
            
            # Gelen yanıt boşsa (örneğin API veri döndürmediyse) mesaj listesine ekleme
            if answer and answer.strip():
                messages.append({"role": "assistant", "content": answer})
            else:
                print("Asistan'dan boş yanıt geldi. Lütfen sorunuzu tekrar deneyin.")
                # Boş yanıtları mesaj geçmişine ekleme
                messages.pop()  # Son kullanıcı mesajını da geri al
                
        except (EOFError, KeyboardInterrupt):
            print("\nUygulamadan çıkılıyor...")
            break
        except Exception as e:
            print(f"Hata: {e}")

if __name__ == "__main__":
    asyncio.run(main())
