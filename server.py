import os
import pickle
from functools import lru_cache
from typing import Optional

import shutil
from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.responses import (
    HTMLResponse,
    FileResponse,
    RedirectResponse,
    PlainTextResponse,
)
from fastapi.templating import Jinja2Templates

from reader3 import (
    Book,
    process_epub,
    save_to_pickle,
)
from user_data import (
    UserDataManager,
    Highlight,
    Bookmark,
    ReadingProgress,
    SearchQuery,
    generate_id,
)

import sys

app = FastAPI()

# Determine base path for resources (templates)
if getattr(sys, "frozen", False):
    # If run as an executable (PyInstaller)
    base_resource_path = sys._MEIPASS
else:
    # If run as a script
    base_resource_path = os.path.dirname(os.path.abspath(__file__))

templates_dir = os.path.join(base_resource_path, "templates")
templates = Jinja2Templates(directory=templates_dir)

# Where are the book folders located?
# Use environment variable if set (by launcher.py for macOS .app bundles),
# otherwise fall back to executable directory or current directory
if os.environ.get("READER3_BOOKS_DIR"):
    BOOKS_DIR = os.environ["READER3_BOOKS_DIR"]
elif getattr(sys, "frozen", False):
    # Fallback: get the directory containing the .app bundle on macOS
    executable_path = sys.executable
    if ".app/Contents/MacOS" in executable_path:
        app_bundle_path = os.path.dirname(
            os.path.dirname(os.path.dirname(executable_path))
        )
        BOOKS_DIR = os.path.dirname(app_bundle_path)
    else:
        BOOKS_DIR = os.path.dirname(executable_path)
else:
    BOOKS_DIR = "."

# Initialize user data manager
user_data_manager = UserDataManager(BOOKS_DIR)

print(f"Books directory: {BOOKS_DIR}")
print(f"Templates directory: {templates_dir}")
print(f"Current working directory: {os.getcwd()}")


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
            item_path = os.path.join(BOOKS_DIR, item)
            if item.endswith("_data") and os.path.isdir(item_path):
                # Try to load it to get the title
                book = load_book_cached(item)
                if book:
                    books.append(
                        {
                            "id": item,
                            "title": book.metadata.title,
                            "author": ", ".join(book.metadata.authors),
                            "chapters": len(book.spine),
                        }
                    )

    return templates.TemplateResponse(
        "library.html", {"request": request, "books": books}
    )


import tempfile


@app.post("/upload")
async def upload_book(file: UploadFile = File(...)):
    """Handle EPUB file uploads."""

    # Create a temp file to store the upload
    # We use delete=False so we can close it and then read it in process_epub
    # We need to preserve the .epub/.pdf extension for some libraries/checks
    suffix = os.path.splitext(file.filename)[1].lower()
    if suffix not in [".epub", ".pdf"]:
        raise HTTPException(
            status_code=400, detail="Only .epub and .pdf files are supported"
        )

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
        if suffix == ".pdf":
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
        if "full_out_dir" in locals() and os.path.exists(full_out_dir):
            shutil.rmtree(full_out_dir)
        raise HTTPException(status_code=500, detail=f"Failed to process book: {str(e)}")
    finally:
        # Clean up temp file
        if "temp_path" in locals() and os.path.exists(temp_path):
            os.remove(temp_path)

    return RedirectResponse(url="/", status_code=303)


@app.get("/read/{book_id}", response_class=HTMLResponse)
async def redirect_to_first_chapter(request: Request, book_id: str):
    """Helper to just go to chapter 0."""
    return await read_chapter(request=request, book_id=book_id, chapter_index=0)


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

    return templates.TemplateResponse(
        "reader.html",
        {
            "request": request,
            "book": book,
            "current_chapter": current_chapter,
            "chapter_index": chapter_index,
            "book_id": book_id,
            "prev_idx": prev_idx,
            "next_idx": next_idx,
            "is_pdf": book.is_pdf,
        },
    )


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
        pages.append({"index": i, "title": chapter.title, "content": chapter.content})

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
        # Clean up user data for this book
        user_data_manager.cleanup_book_data(safe_book_id)
        return {"status": "deleted"}
    except Exception as e:
        print(f"Error deleting book {safe_book_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete book: {str(e)}")


# ============================================================================
# Reading Progress API
# ============================================================================


@app.get("/api/progress/{book_id}")
async def get_reading_progress(book_id: str):
    """Get reading progress for a book."""
    progress = user_data_manager.get_progress(book_id)
    if progress:
        return {
            "book_id": progress.book_id,
            "chapter_index": progress.chapter_index,
            "scroll_position": progress.scroll_position,
            "last_read": progress.last_read,
            "total_chapters": progress.total_chapters,
            "reading_time_seconds": progress.reading_time_seconds,
        }
    return {"book_id": book_id, "chapter_index": 0, "scroll_position": 0.0}


@app.post("/api/progress/{book_id}")
async def save_reading_progress(book_id: str, request: Request):
    """Save reading progress for a book."""
    data = await request.json()

    progress = ReadingProgress(
        book_id=book_id,
        chapter_index=data.get("chapter_index", 0),
        scroll_position=data.get("scroll_position", 0.0),
        total_chapters=data.get("total_chapters", 0),
        reading_time_seconds=data.get("reading_time_seconds", 0),
    )
    user_data_manager.save_progress(progress)
    return {"status": "saved"}


# ============================================================================
# Bookmarks API
# ============================================================================


@app.get("/api/bookmarks/{book_id}")
async def get_bookmarks(book_id: str):
    """Get all bookmarks for a book."""
    bookmarks = user_data_manager.get_bookmarks(book_id)
    return {
        "book_id": book_id,
        "bookmarks": [
            {
                "id": b.id,
                "chapter_index": b.chapter_index,
                "scroll_position": b.scroll_position,
                "title": b.title,
                "note": b.note,
                "created_at": b.created_at,
            }
            for b in bookmarks
        ],
    }


@app.post("/api/bookmarks/{book_id}")
async def add_bookmark(book_id: str, request: Request):
    """Add a bookmark."""
    data = await request.json()

    bookmark = Bookmark(
        id=generate_id(),
        book_id=book_id,
        chapter_index=data.get("chapter_index", 0),
        scroll_position=data.get("scroll_position", 0.0),
        title=data.get("title", "Bookmark"),
        note=data.get("note"),
    )
    user_data_manager.add_bookmark(bookmark)
    return {"id": bookmark.id, "status": "created"}


@app.delete("/api/bookmarks/{book_id}/{bookmark_id}")
async def delete_bookmark(book_id: str, bookmark_id: str):
    """Delete a bookmark."""
    if user_data_manager.delete_bookmark(book_id, bookmark_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Bookmark not found")


@app.put("/api/bookmarks/{book_id}/{bookmark_id}")
async def update_bookmark(book_id: str, bookmark_id: str, request: Request):
    """Update a bookmark's note."""
    data = await request.json()
    note = data.get("note", "")

    if user_data_manager.update_bookmark_note(book_id, bookmark_id, note):
        return {"status": "updated"}
    raise HTTPException(status_code=404, detail="Bookmark not found")


# ============================================================================
# Highlights API
# ============================================================================


@app.get("/api/highlights/{book_id}")
async def get_highlights(book_id: str, chapter: int = None):
    """Get highlights for a book, optionally filtered by chapter."""
    highlights = user_data_manager.get_highlights(book_id, chapter)
    return {
        "book_id": book_id,
        "highlights": [
            {
                "id": h.id,
                "chapter_index": h.chapter_index,
                "text": h.text,
                "color": h.color,
                "note": h.note,
                "start_offset": h.start_offset,
                "end_offset": h.end_offset,
                "created_at": h.created_at,
            }
            for h in highlights
        ],
    }


@app.post("/api/highlights/{book_id}")
async def add_highlight(book_id: str, request: Request):
    """Add a highlight."""
    data = await request.json()

    highlight = Highlight(
        id=generate_id(),
        book_id=book_id,
        chapter_index=data.get("chapter_index", 0),
        text=data.get("text", ""),
        color=data.get("color", "yellow"),
        note=data.get("note"),
        start_offset=data.get("start_offset", 0),
        end_offset=data.get("end_offset", 0),
    )
    user_data_manager.add_highlight(highlight)
    return {"id": highlight.id, "status": "created"}


@app.delete("/api/highlights/{book_id}/{highlight_id}")
async def delete_highlight(book_id: str, highlight_id: str):
    """Delete a highlight."""
    if user_data_manager.delete_highlight(book_id, highlight_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Highlight not found")


@app.put("/api/highlights/{book_id}/{highlight_id}")
async def update_highlight(book_id: str, highlight_id: str, request: Request):
    """Update a highlight's note."""
    data = await request.json()
    note = data.get("note", "")

    if user_data_manager.update_highlight_note(book_id, highlight_id, note):
        return {"status": "updated"}
    raise HTTPException(status_code=404, detail="Highlight not found")


# ============================================================================
# Search API
# ============================================================================


@app.get("/api/search")
async def search_books(q: str, book_id: str = None):
    """
    Search for text across all books or within a specific book.
    Returns matching passages with context.
    """
    if not q or len(q) < 2:
        return {"results": [], "query": q}

    results = []
    query_lower = q.lower()

    # Determine which books to search
    if book_id:
        book_ids = [book_id]
    else:
        # Search all books
        book_ids = []
        if os.path.exists(BOOKS_DIR):
            for item in os.listdir(BOOKS_DIR):
                item_path = os.path.join(BOOKS_DIR, item)
                if item.endswith("_data") and os.path.isdir(item_path):
                    book_ids.append(item)

    for bid in book_ids:
        book = load_book_cached(bid)
        if not book:
            continue

        for idx, chapter in enumerate(book.spine):
            # Search in plain text
            text = chapter.text if hasattr(chapter, "text") else ""
            text_lower = text.lower()

            # Find all occurrences
            start = 0
            while True:
                pos = text_lower.find(query_lower, start)
                if pos == -1:
                    break

                # Extract context (100 chars before and after)
                context_start = max(0, pos - 100)
                context_end = min(len(text), pos + len(q) + 100)
                context = text[context_start:context_end]

                # Add ellipsis if truncated
                if context_start > 0:
                    context = "..." + context
                if context_end < len(text):
                    context = context + "..."

                results.append(
                    {
                        "book_id": bid,
                        "book_title": book.metadata.title,
                        "chapter_index": idx,
                        "chapter_title": chapter.title,
                        "context": context,
                        "position": pos,
                    }
                )

                start = pos + 1

                # Limit results per chapter
                if (
                    len(
                        [
                            r
                            for r in results
                            if r["book_id"] == bid and r["chapter_index"] == idx
                        ]
                    )
                    >= 5
                ):
                    break

        # Limit total results
        if len(results) >= 50:
            break

    # Record search in history
    search_query = SearchQuery(query=q, book_id=book_id, results_count=len(results))
    user_data_manager.add_search(search_query)

    return {"query": q, "results": results, "total": len(results)}


@app.get("/api/search/history")
async def get_search_history(limit: int = 20):
    """Get recent search history."""
    history = user_data_manager.get_search_history(limit)
    return {
        "history": [
            {
                "query": h.query,
                "book_id": h.book_id,
                "timestamp": h.timestamp,
                "results_count": h.results_count,
            }
            for h in history
        ]
    }


@app.delete("/api/search/history")
async def clear_search_history():
    """Clear search history."""
    user_data_manager.clear_search_history()
    return {"status": "cleared"}


# ============================================================================
# Export API
# ============================================================================


@app.get("/api/export/{book_id}")
async def export_book_data(book_id: str, format: str = "json"):
    """Export highlights and bookmarks for a book."""
    if format not in ["json", "markdown"]:
        raise HTTPException(
            status_code=400, detail="Format must be 'json' or 'markdown'"
        )

    content = user_data_manager.export_book_data(book_id, format)

    if format == "markdown":
        return PlainTextResponse(
            content,
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={book_id}_notes.md"},
        )
    else:
        return PlainTextResponse(
            content,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename={book_id}_notes.json"
            },
        )


@app.get("/api/export")
async def export_all_data():
    """Export all user data."""
    content = user_data_manager.export_all_data()
    return PlainTextResponse(
        content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=reader3_backup.json"},
    )


if __name__ == "__main__":
    import uvicorn

    print("Starting server at http://127.0.0.1:8123")
    uvicorn.run(app, host="127.0.0.1", port=8123)
