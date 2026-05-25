import os

import uvicorn


if __name__ == "__main__":
    reload_enabled = os.getenv("QUANT_FOREX_RELOAD", "1").lower() not in {"0", "false", "no"}
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, reload=reload_enabled)
