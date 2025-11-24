import os
import pickle
from functools import lru_cache
from typing import Optional

import shutil
from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from reader3 import Book, BookMetadata, ChapterContent, TOCEntry, process_epub, save_to_pickle

import sys

app = FastAPI()

# Determine base path for resources (templates)
if getattr(sys, 'frozen', False):
    # If run as an executable (PyInstaller)
    base_resource_path = sys._MEIPASS
else:
    # If run as a script
    base_resource_path = os.path.dirname(os.path.abspath(__file__))

templates_dir = os.path.join(base_resource_path, "templates")
templates = Jinja2Templates(directory=templates_dir)

# Where are the book folders located?
# If frozen, we want the directory of the executable, not the temp dir
if getattr(sys, 'frozen', False):
    BOOKS_DIR = os.path.dirname(sys.executable)
else:
    BOOKS_DIR = "."

@lru_cache(maxsize=10)
def load_book_cached(folder_name: str) -> Optional[Book]:
    """
    Loads the book from the pickle file.
    Cached so we don't re-read the disk on every click.
    """
    file_path = os.path.join(BOOKS_DIR, folder_name, "book.pkl")
    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, "rb") as f:
            book = pickle.load(f)
        return book
    except Exception as e:
        print(f"Error loading book {folder_name}: {e}")
        return None

@app.get("/", response_class=HTMLResponse)
async def library_view(request: Request):
    """Lists all available processed books."""
    books = []

    # Scan directory for folders ending in '_data' that have a book.pkl
    if os.path.exists(BOOKS_DIR):
        for item in os.listdir(BOOKS_DIR):
            if item.endswith("_data") and os.path.isdir(item):
                # Try to load it to get the title
                book = load_book_cached(item)
                if book:
                    books.append({
                        "id": item,
                        "title": book.metadata.title,
                        "author": ", ".join(book.metadata.authors),
                        "chapters": len(book.spine)
                    })

    return templates.TemplateResponse("library.html", {"request": request, "books": books})

import tempfile

@app.post("/upload")
async def upload_book(file: UploadFile = File(...)):
    """Handle EPUB file uploads."""


    # Create a temp file to store the upload
    # We use delete=False so we can close it and then read it in process_epub
    # We need to preserve the .epub/.pdf extension for some libraries/checks
    suffix = os.path.splitext(file.filename)[1].lower()
    if suffix not in ['.epub', '.pdf']:
        raise HTTPException(status_code=400, detail="Only .epub and .pdf files are supported")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        temp_path = tmp.name

    try:
        # Determine output directory based on original filename
        safe_filename = os.path.basename(file.filename)
        out_dir = os.path.splitext(safe_filename)[0] + "_data"
        # Ensure we use the BOOKS_DIR as the base
        full_out_dir = os.path.join(BOOKS_DIR, out_dir)
        
        print(f"Processing {temp_path} -> {full_out_dir}")
        
        # Process the Book
        if suffix == '.pdf':
            from reader3 import process_pdf
            book_obj = process_pdf(temp_path, full_out_dir)
        else:
            book_obj = process_epub(temp_path, full_out_dir)
            
        save_to_pickle(book_obj, full_out_dir)
        
        # Clear cache for this book if it existed
        load_book_cached.cache_clear()
        
    except Exception as e:
        print(f"Error processing book: {e}")
        # Clean up partial data if failed
        if 'full_out_dir' in locals() and os.path.exists(full_out_dir):
            shutil.rmtree(full_out_dir)
        raise HTTPException(status_code=500, detail=f"Failed to process book: {str(e)}")
    finally:
        # Clean up temp file
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)

    return RedirectResponse(url="/", status_code=303)

@app.get("/read/{book_id}", response_class=HTMLResponse)
async def redirect_to_first_chapter(book_id: str):
    """Helper to just go to chapter 0."""
    return await read_chapter(book_id=book_id, chapter_index=0)

@app.get("/read/{book_id}/{chapter_index}", response_class=HTMLResponse)
async def read_chapter(request: Request, book_id: str, chapter_index: int):
    """The main reader interface."""
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if chapter_index < 0 or chapter_index >= len(book.spine):
        raise HTTPException(status_code=404, detail="Chapter not found")

    current_chapter = book.spine[chapter_index]

    # Calculate Prev/Next links
    prev_idx = chapter_index - 1 if chapter_index > 0 else None
    next_idx = chapter_index + 1 if chapter_index < len(book.spine) - 1 else None

    return templates.TemplateResponse("reader.html", {
        "request": request,
        "book": book,
        "current_chapter": current_chapter,
        "chapter_index": chapter_index,
        "book_id": book_id,
        "prev_idx": prev_idx,
        "next_idx": next_idx,
        "is_pdf": book.is_pdf
    })

@app.get("/read/{book_id}/pages/{start}/{count}")
async def get_pages(book_id: str, start: int, count: int):
    """
    Fetches multiple pages for infinite scrolling (PDF only).
    Returns JSON with array of page content.
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Infinite scroll only for PDFs")
    
    total = len(book.spine)
    if start >= total:
        return {"pages": []}
    
    end = min(start + count, total)
    pages = []
    
    for i in range(start, end):
        chapter = book.spine[i]
        pages.append({
            "index": i,
            "title": chapter.title,
            "content": chapter.content
        })
    
    return {"pages": pages, "total": total}

@app.get("/read/{book_id}/images/{image_name}")
async def serve_image(book_id: str, image_name: str):
    """
    Serves images specifically for a book.
    The HTML contains <img src="images/pic.jpg">.
    The browser resolves this to /read/{book_id}/images/pic.jpg.
    """
    # Security check: ensure book_id is clean
    safe_book_id = os.path.basename(book_id)
    safe_image_name = os.path.basename(image_name)

    img_path = os.path.join(BOOKS_DIR, safe_book_id, "images", safe_image_name)

    if not os.path.exists(img_path):
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(img_path)

@app.delete("/delete/{book_id}")
async def delete_book(book_id: str):
    """
    Deletes a book folder and all its contents.
    """
    # Security: ensure book_id is clean and ends with _data
    safe_book_id = os.path.basename(book_id)
    if not safe_book_id.endswith("_data"):
        raise HTTPException(status_code=400, detail="Invalid book ID")

    book_path = os.path.join(BOOKS_DIR, safe_book_id)

    if not os.path.exists(book_path):
        raise HTTPException(status_code=404, detail="Book not found")

    try:
        # Remove the entire book directory
        shutil.rmtree(book_path)
        # Clear the cache
        load_book_cached.cache_clear()
        return {"status": "deleted"}
    except Exception as e:
        print(f"Error deleting book {safe_book_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete book: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print("Starting server at http://127.0.0.1:8123")
    uvicorn.run(app, host="127.0.0.1", port=8123)
