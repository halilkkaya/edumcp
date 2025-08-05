import logging
import asyncio
from app.server import main


# 5. MCP SUNUCUSUNU BAŞLATMA
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    from app.tools import *
    
    # FastMCP sunucusunu çalıştır
    asyncio.run(main())