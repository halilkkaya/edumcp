# app/server.py

import contextlib
import logging
from collections.abc import AsyncIterator

import anyio
import click
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from pydantic import AnyUrl
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

# 1. ARAÇ FONKSİYONLARINI DOĞRUDAN İÇERİ AKTARMA
# Her bir araç modülünden, artık dekoratörsüz olan ana fonksiyonları import ediyoruz.
from app.tools.pdf_summarizer import pdf_ozetle
from app.tools.quiz_generator import soru_olustur
from app.tools.audio_transcriber import ses_dosyasini_transkript_et
from app.tools.video_summarizer import videoyu_ozetle

# Loglama yapılandırması
logger = logging.getLogger(__name__)


@click.command()
@click.option("--port", default=8000, help="HTTP için dinlenecek port")
@click.option("--host", default="0.0.0.0", help="Sunucunun dinleyeceği host adresi")
@click.option(
    "--log-level",
    default="INFO",
    help="Loglama seviyesi (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
)
@click.option(
    "--json-response",
    is_flag=True,
    default=False,
    help="SSE akışları yerine JSON yanıtları etkinleştir",
)
def main(
    port: int,
    host: str,
    log_level: str,
    json_response: bool,
) -> int:
    # Ana loglama yapılandırması
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),  # Terminale yazdırır
        ]
    )
    
    # Root logger seviyesini ayarla
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Araç modüllerinin loglarını özellikle terminale düşür
    tool_loggers = [
        'app.tools.pdf_summarizer',
        'app.tools.quiz_generator', 
        'app.tools.audio_transcriber',
        'app.tools.video_summarizer'
    ]
    
    for tool_logger_name in tool_loggers:
        tool_logger = logging.getLogger(tool_logger_name)
        tool_logger.setLevel(logging.DEBUG)
        # Eğer handler yoksa ekle
        if not tool_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(
                logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            )
            tool_logger.addHandler(handler)
        # Parent loggerdan devralma
        tool_logger.propagate = True

    # 2. TEMEL MCP NESNESİNİ OLUŞTURMA
    app = Server("Eğitim Araçları")

    # 3. ARAÇLARI MANUEL OLARAK KAYDETME
    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.ContentBlock]:
        logger.info(f"Araç çağrısı: {name} - Argümanlar: {arguments}")
        
        try:
            if name == "pdf_ozetle":
                result = pdf_ozetle(**arguments)
                return [types.TextContent(type="text", text=result)]
            elif name == "soru_olustur":
                result = soru_olustur(**arguments)
                return [types.TextContent(type="text", text=result)]
            elif name == "ses_dosyasini_transkript_et":
                result = ses_dosyasini_transkript_et(**arguments)
                return [types.TextContent(type="text", text=result)]
            elif name == "videoyu_ozetle":
                result = videoyu_ozetle(**arguments)
                return [types.TextContent(type="text", text=result)]
            else:
                logger.error(f"Bilinmeyen araç: {name}")
                return [types.TextContent(type="text", text=f"Hata: '{name}' adlı araç bulunamadı.")]
        except Exception as e:
            logger.error(f"Araç çalıştırma hatası: {str(e)}")
            return [types.TextContent(type="text", text=f"Araç çalıştırma hatası: {str(e)}")]

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="pdf_ozetle",
                description="PDF belgelerini kapsamlı şekilde özetler ve analiz eder. Dökümanların ana noktalarını, önemli bölümlerini ve anahtar bilgilerini çıkarır.",
                inputSchema={
                    "type": "object",
                    "required": ["pdf_dosyasi_yolu"],
                    "properties": {
                        "pdf_dosyasi_yolu": {
                            "type": "string",
                            "description": "Özetlenecek PDF dosyasının tam yolu"
                        },
                        "ozet_tipi": {
                            "type": "string",
                            "description": "Özet türü - 'kisa', 'genis', 'kapsamli'",
                            "default": "kapsamli"
                        },
                        "hedef_dil": {
                            "type": "string",
                            "description": "Özetin hangi dilde olacağı",
                            "default": "otomatik"
                        }
                    }
                }
            ),
            types.Tool(
                name="soru_olustur",
                description="Verilen konuda akademik standartlarda sorular oluşturur ve detaylı cevap anahtarları sağlar.",
                inputSchema={
                    "type": "object",
                    "required": ["konu"],
                    "properties": {
                        "konu": {
                            "type": "string",
                            "description": "Sorular oluşturulacak ana konu"
                        },
                        "soru_sayisi": {
                            "type": "integer",
                            "description": "Oluşturulacak soru adedi (1-20 arası)",
                            "default": 5
                        },
                        "zorluk": {
                            "type": "string",
                            "description": "Zorluk seviyesi - 'kolay', 'orta', 'zor', 'karisik'",
                            "default": "orta"
                        },
                        "soru_tipi": {
                            "type": "string",
                            "description": "Soru türü - 'test', 'acik_uclu', 'dogru_yanlis', 'karisik'",
                            "default": "karisik"
                        }
                    }
                }
            ),
            types.Tool(
                name="ses_dosyasini_transkript_et",
                description="Ses dosyalarını metne dönüştürür ve gelişmiş analiz sunar. Konuşma tanıma, dil algılama ve içerik analizi yapar.",
                inputSchema={
                    "type": "object",
                    "required": ["ses_dosyasi_yolu"],
                    "properties": {
                        "ses_dosyasi_yolu": {
                            "type": "string",
                            "description": "Transkript edilecek ses dosyasının yolu"
                        },
                        "cikti_tipi": {
                            "type": "string",
                            "description": "Çıktı türü - 'transkript', 'ozet', 'kapsamli'",
                            "default": "transkript"
                        },
                        "hedef_dil": {
                            "type": "string",
                            "description": "Hedef dil",
                            "default": "otomatik"
                        }
                    }
                }
            ),
            types.Tool(
                name="videoyu_ozetle",
                description="YouTube videolarını veya yerel video dosyalarını analiz eder ve kapsamlı özetler oluşturur. Görsel ve işitsel içeriği birlikte değerlendirir.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "video_url": {
                            "type": "string",
                            "description": "Özetlenecek videonun YouTube linki"
                        },
                        "video_dosyasi_yolu": {
                            "type": "string",
                            "description": "Sunucuda bulunan bir video dosyasının yolu"
                        },
                        "ozet_tipi": {
                            "type": "string",
                            "description": "Özet türü - 'kisa', 'genis', 'kapsamli'",
                            "default": "kapsamli"
                        },
                        "hedef_dil": {
                            "type": "string",
                            "description": "Özetin hangi dilde olacağı",
                            "default": "otomatik"
                        }
                    }
                }
            )
        ]

    # 4. SESSION MANAGER OLUŞTURMA
    session_manager = StreamableHTTPSessionManager(
        app=app,
        json_response=json_response,
    )

    # ASGI handler for streamable HTTP connections
    async def handle_streamable_http(
        scope: Scope, receive: Receive, send: Send
    ) -> None:
        await session_manager.handle_request(scope, receive, send)

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        """Session manager yaşam döngüsünü yöneten context manager."""
        async with session_manager.run():
            logger.info("Eğitim Araçları MCP sunucusu StreamableHTTP session manager ile başlatıldı!")
            try:
                yield
            finally:
                logger.info("Uygulama kapatılıyor...")

    # 5. STARLETTE UYGULAMASI OLUŞTURMA
    starlette_app = Starlette(
        debug=True,
        routes=[
            Mount("/mcp", app=handle_streamable_http),
        ],
        lifespan=lifespan,
    )

    import uvicorn

    logger.info(f"Sunucu http://{host}:{port}/mcp adresinde başlatılıyor...")
    uvicorn.run(starlette_app, host=host, port=port)

    return 0


def run_server():
    """Ana sunucu çalıştırma fonksiyonu - main.py tarafından çağrılır."""
    main()


# Bu betik doğrudan çalıştırıldığında main() fonksiyonunu çağır.
if __name__ == "__main__":
    main()