import logging
from app.server import run_server


# 5. MCP SUNUCUSUNU BAŞLATMA
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    from app.tools import *
    
    # FastMCP sunucusunu çalıştır
    run_server()