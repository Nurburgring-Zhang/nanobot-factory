import sys, os
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend\imdf')
import uvicorn
if __name__ == "__main__":
    uvicorn.run("api.canvas_web:app", host="127.0.0.1", port=18900, log_level="warning")
