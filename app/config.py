import os
from dotenv import load_dotenv
import logging
import google.generativeai as genai

load_dotenv()


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logging.error("GEMINI_API_KEY bulunamadı. Lütfen .env dosyasını kontrol edin.")
    # Uygulamanın başlamasını engelleyebilirsiniz veya sadece uyarı verebilirsiniz.
    exit() 
else:
    genai.configure(api_key=GEMINI_API_KEY)
    logging.info("Gemini API başarıyla yapılandırıldı")
