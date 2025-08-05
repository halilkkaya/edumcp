import logging
import asyncio
from fastmcp import FastMCP

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s')

# FastMCP sunucusunu başlat
mcp = FastMCP(
    "Eğitim Araçları",
    include_tags={"public"},
    exclude_tags={"private", "beta"}
)

async def main():
    logging.info("FastMCP sunucusu başlatıldı")
    # Async context'te run_async() kullan
    await mcp.run_async(transport="streamable-http", host="0.0.0.0", port=8000)

if __name__ == "__main__":
    from app.tools import *
    asyncio.run(main())