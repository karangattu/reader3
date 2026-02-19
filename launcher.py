import os
import sys
import webbrowser
import threading
import time
import subprocess
import traceback
import multiprocessing
from datetime import datetime


def get_error_log_path():
    """Get the path for the error log file."""
    return os.path.expanduser("~/Documents/Reader3_error.log")


def log_error(message, include_traceback=True):
    """Log an error message to file."""
    try:
        error_log = get_error_log_path()
        with open(error_log, "a") as f:
            f.write(f"\n[{datetime.now().isoformat()}]\n")
            f.write(f"{message}\n")
            if include_traceback:
                f.write(traceback.format_exc())
                f.write("\n")
    except Exception:
        pass


def log_info(message):
    """Log an info message to file."""
    try:
        error_log = get_error_log_path()
        with open(error_log, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] INFO: {message}\n")
    except Exception:
        pass


def get_books_directory():
    """
    Get the directory where books should be stored.
    For macOS .app bundles, this should be the directory containing the .app,
    NOT the internal _MEIPASS directory.
    """
    if getattr(sys, 'frozen', False):
        # We're running as a bundled executable
        executable_path = sys.executable
        
        # For macOS .app bundles, the executable is at:
        # Reader3.app/Contents/MacOS/Reader3
        # We want to get the directory containing Reader3.app
        if '.app/Contents/MacOS' in executable_path:
            # Go up 3 levels from the executable to get outside the .app bundle
            app_bundle_path = os.path.dirname(os.path.dirname(os.path.dirname(executable_path)))
            books_dir = os.path.dirname(app_bundle_path)
        else:
            # Non-macOS or onedir mode - use executable's directory
            books_dir = os.path.dirname(executable_path)
        
        return books_dir
    else:
        # Running as a script - use current directory
        return os.getcwd()


def open_browser():
    """Open the browser after a short delay to ensure server is running."""
    time.sleep(2)
    try:
        webbrowser.open("http://127.0.0.1:8123")
    except Exception:
        # Fallback: use macOS open command
        try:
            subprocess.run(["open", "http://127.0.0.1:8123"], check=False)
        except Exception as e:
            log_error(f"Failed to open browser: {e}", include_traceback=False)


def main():
    try:
        if getattr(sys, 'frozen', False) and sys.platform == 'win32':
            multiprocessing.freeze_support()

        # Set the BOOKS_DIR environment variable for server.py to use
        books_dir = get_books_directory()
        os.environ['READER3_BOOKS_DIR'] = books_dir
        
        if getattr(sys, 'frozen', False):
            log_info("Starting Reader3")
            log_info(f"Executable: {sys.executable}")
            log_info(f"Books directory: {books_dir}")
            if hasattr(sys, '_MEIPASS'):
                log_info(f"Resources directory: {sys._MEIPASS}")
        
        # Import here after setting up the environment
        import uvicorn
        from server import app
        
        # When running as a PyInstaller executable (especially on Windows),
        # sys.stdout may be None, which breaks uvicorn's logging.
        # Redirect stdout/stderr to prevent AttributeError in uvicorn logging.
        if getattr(sys, 'frozen', False) and sys.stdout is None:
            # Redirect output to null device
            null_file = open(os.devnull, 'w')
            sys.stdout = null_file
            sys.stderr = null_file
        
        # Start browser in a separate thread
        threading.Thread(target=open_browser, daemon=True).start()

        # Run server
        uvicorn_kwargs = {
            "host": "127.0.0.1",
            "port": 8123,
            "log_level": "info",
        }

        # Prefer uvloop/httptools for faster event loop and HTTP parsing
        if sys.platform != "win32":
            uvicorn_kwargs.update({"loop": "uvloop", "http": "httptools"})
        else:
            # Prefer pure-Python HTTP parser for frozen Windows portability
            uvicorn_kwargs.update({"http": "h11"})

        uvicorn.run(app, **uvicorn_kwargs)
    except Exception as e:
        # Log errors to a file when running as executable
        log_error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()
