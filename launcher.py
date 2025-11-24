import os
import sys
import webbrowser
import threading
import time
import uvicorn
from server import app

def open_browser():
    """Open the browser after a short delay to ensure server is running."""
    time.sleep(1.5)
    webbrowser.open("http://127.0.0.1:8123")

def main():
    # Ensure we're running in the correct directory for relative paths (like templates)
    # When running as an executable, sys._MEIPASS is the temp folder where resources are extracted
    if getattr(sys, 'frozen', False):
        # If bundled, we might need to adjust paths or change directory
        # However, server.py uses "templates" relative path.
        # We should change directory to where the executable is, or where resources are.
        base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        
        # If we want to support drag-and-drop or local files, we might want to stay in the exe dir.
        # But for internal resources (templates), we need to make sure FastAPI finds them.
        # FastAPI/Jinja2 looks in 'templates' directory relative to CWD by default.
        
        # If using PyInstaller --onedir, resources are in internal dir.
        # If using --onefile, they are in sys._MEIPASS.
        
        if hasattr(sys, '_MEIPASS'):
            # We are in onefile mode (or onedir internal)
            # We need to tell Jinja2 where templates are.
            # But server.py initializes Jinja2Templates(directory="templates") at module level.
            # This might be tricky if we don't patch it or change CWD.
            os.chdir(sys._MEIPASS)
    
    # Start browser in a separate thread
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Run server
    print("Starting Reader3...")
    uvicorn.run(app, host="127.0.0.1", port=8123, log_level="info")

if __name__ == "__main__":
    main()
