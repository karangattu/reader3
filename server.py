import os
import pickle
from functools import lru_cache
from typing import Optional
import tempfile
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
    get_pdf_page_stats,
    search_pdf_text_positions,
)
from user_data import (
    UserDataManager,
    Highlight,
    Bookmark,
    ReadingProgress,
    SearchQuery,
    ReadingSession,
    VocabularyWord,
    Annotation,
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


@lru_cache(maxsize=50)
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
async def library_view(request: Request, sort: str = "recent"):
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
                            "added_at": book.added_at or book.processed_at,
                            "cover_image": book.cover_image,
                        }
                    )

    # Sort books based on the sort parameter
    if sort == "recent":
        books.sort(key=lambda x: x["added_at"], reverse=True)
    elif sort == "alpha":
        books.sort(key=lambda x: x["title"].lower())
    elif sort == "author":
        books.sort(key=lambda x: x["author"].lower())

    return templates.TemplateResponse(
        "library.html", {"request": request, "books": books, "sort": sort}
    )


@app.get("/cover/{book_id}")
async def get_cover_image(book_id: str):
    """Serve cover image for a book."""
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.cover_image:
        raise HTTPException(status_code=404, detail="No cover image available")

    # Construct the full path to the cover image
    cover_path = os.path.join(BOOKS_DIR, book_id, book.cover_image)

    # Security: ensure the path is within the book directory
    safe_book_id = os.path.basename(book_id)
    expected_base = os.path.join(BOOKS_DIR, safe_book_id)
    if not os.path.abspath(cover_path).startswith(expected_base):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(cover_path):
        raise HTTPException(status_code=404, detail="Cover image not found")

    return FileResponse(cover_path)


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

    # Check if this is an old-style PDF (text-based instead of image-based)
    needs_reprocess = False
    if book.is_pdf and len(book.spine) > 0:
        # Old-style PDFs have HTML content with positioned text
        # New-style PDFs have simple img tags
        first_content = book.spine[0].content
        if '<div id="page' in first_content or 'style="top:' in first_content:
            needs_reprocess = True

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
            "needs_reprocess": needs_reprocess,
        },
    )


@app.get("/read/{book_id}/pages/{start}/{count}")
async def get_pages(book_id: str, start: int, count: int):
    """
    Fetches multiple pages for infinite scrolling (PDF only).
    Returns JSON with array of page content including text for copy.
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
            "content": chapter.content,
            "text": chapter.text  # Include text for copy functionality
        })

    return {"pages": pages, "total": total}


@app.post("/api/chapters/text")
async def get_chapters_text(request: Request):
    """
    Fetches text content from multiple chapters for copying.
    Expects JSON body: {"book_id": "...", "chapter_hrefs": [...]}
    Returns JSON with text content for each chapter.
    """
    body = await request.json()
    book_id = body.get("book_id")
    chapter_hrefs = body.get("chapter_hrefs", [])

    if not book_id:
        raise HTTPException(status_code=400, detail="book_id is required")

    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Build a map of href -> chapter
    href_to_chapter = {ch.href: ch for ch in book.spine}

    # Collect text content
    chapters_data = []
    for href in chapter_hrefs:
        chapter = href_to_chapter.get(href)
        if chapter:
            chapters_data.append({
                "href": href,
                "title": chapter.title,
                "text": chapter.text
            })

    return {"chapters": chapters_data}


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
        raise HTTPException(
            status_code=500, detail=f"Failed to delete book: {str(e)}"
        )


@app.post("/api/reprocess/{book_id}")
async def reprocess_pdf(book_id: str):
    """
    Reprocess a PDF book with the latest rendering method.
    This is needed for PDFs that were processed with old text-based rendering.
    """
    safe_book_id = os.path.basename(book_id)
    if not safe_book_id.endswith("_data"):
        raise HTTPException(status_code=400, detail="Invalid book ID")

    book = load_book_cached(safe_book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Only PDF books can be reprocessed")

    # Find the original PDF file
    pdf_name = safe_book_id.replace("_data", ".pdf")
    pdf_path = os.path.join(BOOKS_DIR, pdf_name)

    if not os.path.exists(pdf_path):
        raise HTTPException(
            status_code=400,
            detail="Original PDF not found. Please re-upload the PDF."
        )

    try:
        from reader3 import process_pdf

        book_path = os.path.join(BOOKS_DIR, safe_book_id)

        # Reprocess the PDF
        book_obj = process_pdf(pdf_path, book_path)
        save_to_pickle(book_obj, book_path)

        # Clear cache
        load_book_cached.cache_clear()

        return {"status": "success", "message": "PDF reprocessed successfully"}
    except Exception as e:
        print(f"Error reprocessing PDF {safe_book_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to reprocess PDF: {str(e)}"
        )


# ============================================================================
# Reading Progress API
# ============================================================================


@app.get("/api/progress/{book_id}")
async def get_reading_progress(book_id: str):
    """Get reading progress for a book."""
    progress = user_data_manager.get_progress(book_id)
    chapter_progress = user_data_manager.get_chapter_progress(book_id)
    
    # Calculate overall progress percentage from chapter progress
    overall_progress = 0.0
    if chapter_progress:
        # Get the book to know total chapters
        book = load_book_cached(book_id)
        if book and len(book.spine) > 0:
            total_chapters = len(book.spine)
            # Sum up all chapter progress and divide by total chapters
            total_progress = sum(chapter_progress.values())
            overall_progress = total_progress / total_chapters
        elif chapter_progress:
            # Fallback: average of recorded chapters
            overall_progress = sum(chapter_progress.values()) / len(chapter_progress)
    
    if progress:
        return {
            "book_id": progress.book_id,
            "chapter_index": progress.chapter_index,
            "scroll_position": progress.scroll_position,
            "last_read": progress.last_read,
            "total_chapters": progress.total_chapters,
            "reading_time_seconds": progress.reading_time_seconds,
            "progress_percent": overall_progress,
        }
    return {
        "book_id": book_id,
        "chapter_index": 0,
        "scroll_position": 0.0,
        "progress_percent": overall_progress,
    }


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


@app.put("/api/highlights/{book_id}/{highlight_id}/color")
async def update_highlight_color(book_id: str, highlight_id: str, request: Request):
    """Update a highlight's color."""
    data = await request.json()
    color = data.get("color", "yellow")

    if user_data_manager.update_highlight_color(book_id, highlight_id, color):
        return {"status": "updated"}
    raise HTTPException(status_code=404, detail="Highlight not found")


# ============================================================================
# Search API
# ============================================================================


def get_all_book_ids():
    """Get list of all book IDs in the library."""
    book_ids = []
    if os.path.exists(BOOKS_DIR):
        for item in os.listdir(BOOKS_DIR):
            item_path = os.path.join(BOOKS_DIR, item)
            if item.endswith("_data") and os.path.isdir(item_path):
                pkl_path = os.path.join(item_path, "book.pkl")
                if os.path.exists(pkl_path):
                    book_ids.append(item)
    return book_ids


@app.get("/api/search")
async def search_books(q: str, book_id: str = None):
    """
    Search for text across all books or within a specific book.
    Returns all matching passages with context and position data.
    """
    if not q or len(q) < 2:
        return {"results": [], "query": q, "total": 0}

    results = []
    query_lower = q.lower()
    # Total results limit (allow more to show all instances)
    max_total_results = 500

    # Determine which books to search
    book_ids = [book_id] if book_id else get_all_book_ids()

    for bid in book_ids:
        if len(results) >= max_total_results:
            break

        book = load_book_cached(bid)
        if not book:
            continue

        book_title = book.metadata.title

        for idx, chapter in enumerate(book.spine):
            if len(results) >= max_total_results:
                break

            # Search in plain text
            text = getattr(chapter, "text", "") or ""
            if not text:
                continue

            text_lower = text.lower()

            # Quick check: skip if query not in chapter at all
            if query_lower not in text_lower:
                continue

            # Find ALL occurrences in this chapter
            start = 0
            while True:
                pos = text_lower.find(query_lower, start)
                if pos == -1:
                    break

                # Extract context (100 chars before and after)
                context_start = max(0, pos - 100)
                context_end = min(len(text), pos + len(q) + 100)
                context = text[context_start:context_end]

                # Clean up context - trim to word boundaries
                if context_start > 0:
                    space_idx = context.find(" ")
                    if space_idx > 0 and space_idx < 30:
                        context = context[space_idx + 1:]
                    context = "..." + context
                if context_end < len(text):
                    space_idx = context.rfind(" ")
                    if space_idx > len(context) - 30:
                        context = context[:space_idx]
                    context = context + "..."

                results.append({
                    "book_id": bid,
                    "book_title": book_title,
                    "chapter_index": idx,
                    "chapter_href": chapter.href,
                    "chapter_title": chapter.title,
                    "context": context.strip(),
                    "position": pos,
                    "match_length": len(q),
                })

                if len(results) >= max_total_results:
                    break

                start = pos + len(q)  # Skip past this match

    # Record search in history
    search_query = SearchQuery(
        query=q, book_id=book_id, results_count=len(results)
    )
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


# ============================================================================
# Chapter Progress API (per-chapter tracking)
# ============================================================================


@app.get("/api/chapter-progress/{book_id}")
async def get_chapter_progress(book_id: str):
    """Get reading progress for each chapter in a book."""
    progress = user_data_manager.get_chapter_progress(book_id)
    return {"book_id": book_id, "progress": progress}


@app.post("/api/chapter-progress/{book_id}/{chapter_index}")
async def save_chapter_progress(
    book_id: str,
    chapter_index: int,
    request: Request,
    progress: Optional[float] = None
):
    """Save reading progress for a specific chapter."""
    # Support both query parameter (for sendBeacon) and JSON body
    if progress is not None:
        progress_percent = progress
    else:
        try:
            data = await request.json()
            progress_percent = data.get("progress", 0)
        except Exception:
            progress_percent = 0
    
    user_data_manager.save_chapter_progress(
        book_id, chapter_index, progress_percent
    )
    return {"status": "saved"}


# ============================================================================
# Reading Time Estimates API
# ============================================================================


@app.get("/api/reading-times/{book_id}")
async def get_reading_times(book_id: str):
    """Get estimated reading times for all chapters in a book."""
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    # Average reading speed: 225 words per minute
    words_per_minute = 225
    times = {}

    for idx, chapter in enumerate(book.spine):
        # Get text content
        text = getattr(chapter, "text", "") or ""
        if not text:
            # Fallback: strip HTML tags from content
            import re

            content = chapter.content or ""
            text = re.sub(r"<[^>]+>", " ", content)

        # Count words
        word_count = len(text.split())
        minutes = max(1, round(word_count / words_per_minute))
        times[idx] = minutes

    return {"book_id": book_id, "times": times}


# ============================================================================
# PDF-Specific API Endpoints
# ============================================================================


@app.get("/api/pdf/{book_id}/stats")
async def get_pdf_stats(book_id: str):
    """
    Get comprehensive statistics about a PDF book.
    Includes page count, word count, annotations, images, reading time.
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    stats = get_pdf_page_stats(book)
    return {"book_id": book_id, **stats}


@app.get("/api/pdf/{book_id}/thumbnails")
async def list_pdf_thumbnails(book_id: str):
    """
    List all available thumbnails for a PDF book.
    Returns array of thumbnail URLs.
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    if not book.pdf_thumbnails_generated:
        return {"book_id": book_id, "thumbnails": [], "available": False}

    thumbnails = []
    for i in range(book.pdf_total_pages):
        thumbnails.append({
            "page": i,
            "url": f"/read/{book_id}/thumbnails/thumb_{i + 1}.png"
        })

    return {"book_id": book_id, "thumbnails": thumbnails, "available": True}


@app.get("/read/{book_id}/thumbnails/{thumb_name}")
async def serve_thumbnail(book_id: str, thumb_name: str):
    """Serve a PDF page thumbnail image."""
    safe_book_id = os.path.basename(book_id)
    safe_thumb_name = os.path.basename(thumb_name)

    thumb_path = os.path.join(
        BOOKS_DIR, safe_book_id, "thumbnails", safe_thumb_name
    )

    if not os.path.exists(thumb_path):
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    return FileResponse(thumb_path, media_type="image/png")


@app.get("/api/pdf/{book_id}/annotations")
async def get_pdf_annotations(book_id: str, page: int = None):
    """
    Get annotations from a PDF book.
    Optionally filter by page number.
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    annotations = []
    pages_to_check = (
        [page] if page is not None
        else range(book.pdf_total_pages)
    )

    for page_num in pages_to_check:
        if page_num in book.pdf_page_data:
            page_data = book.pdf_page_data[page_num]
            for annot in page_data.annotations:
                annotations.append({
                    "page": annot.page,
                    "type": annot.type,
                    "content": annot.content,
                    "rect": annot.rect,
                    "color": annot.color,
                    "author": annot.author,
                    "created": annot.created
                })

    return {
        "book_id": book_id,
        "annotations": annotations,
        "total": len(annotations)
    }


@app.get("/api/pdf/{book_id}/search-positions")
async def search_pdf_positions(book_id: str, q: str, page: int = None):
    """
    Search for text in a PDF and return positions for highlighting.
    Returns bounding box coordinates for each match.
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    if not q or len(q) < 2:
        return {"query": q, "results": [], "total": 0}

    results = search_pdf_text_positions(book, q, page)

    return {
        "query": q,
        "book_id": book_id,
        "results": results[:100],  # Limit results
        "total": len(results)
    }


@app.get("/api/pdf/{book_id}/page/{page_num}")
async def get_pdf_page_info(book_id: str, page_num: int):
    """
    Get detailed information about a specific PDF page.
    Includes dimensions, rotation, word count, annotations.
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    if page_num < 0 or page_num >= book.pdf_total_pages:
        raise HTTPException(status_code=404, detail="Page not found")

    if page_num not in book.pdf_page_data:
        return {
            "page": page_num,
            "available": False
        }

    page_data = book.pdf_page_data[page_num]
    return {
        "page": page_num,
        "available": True,
        "width": page_data.width,
        "height": page_data.height,
        "rotation": page_data.rotation,
        "word_count": page_data.word_count,
        "has_images": page_data.has_images,
        "annotation_count": len(page_data.annotations),
        "text_block_count": len(page_data.text_blocks)
    }


@app.get("/api/pdf/{book_id}/outline")
async def get_pdf_outline(book_id: str):
    """
    Get the PDF's table of contents/outline structure.
    Returns the hierarchical TOC if available.
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    def toc_to_dict(entries):
        result = []
        for entry in entries:
            item = {
                "title": entry.title,
                "href": entry.href,
                "page": int(entry.href.replace("page_", "")) - 1
                if entry.href.startswith("page_") else 0
            }
            if entry.children:
                item["children"] = toc_to_dict(entry.children)
            result.append(item)
        return result

    return {
        "book_id": book_id,
        "has_native_toc": book.pdf_has_toc,
        "outline": toc_to_dict(book.toc)
    }


@app.post("/api/pdf/{book_id}/export")
async def export_pdf_pages_endpoint(book_id: str, request: Request):
    """
    Export a range of pages from a PDF to a new PDF file.
    Request body: { "start_page": 0, "end_page": 10 }
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    data = await request.json()
    start_page = data.get("start_page", 0)
    end_page = data.get("end_page", book.pdf_total_pages - 1)

    # Validate range
    start_page = max(0, start_page)
    end_page = min(end_page, book.pdf_total_pages - 1)

    if start_page > end_page:
        raise HTTPException(
            status_code=400,
            detail="start_page must be less than or equal to end_page"
        )

    # We need the original PDF file to export
    # Check if it exists in the uploads or can be reconstructed
    original_pdf = None
    possible_paths = [
        os.path.join(BOOKS_DIR, book.source_file),
        os.path.join(BOOKS_DIR, book_id.replace("_data", ".pdf")),
    ]

    for path in possible_paths:
        if os.path.exists(path):
            original_pdf = path
            break

    if not original_pdf:
        raise HTTPException(
            status_code=400,
            detail="Original PDF not found. Export requires the source PDF."
        )

    # Create export in a temp location
    import tempfile
    from reader3 import export_pdf_pages

    with tempfile.NamedTemporaryFile(
        delete=False, suffix=".pdf"
    ) as tmp:
        export_path = tmp.name

    success = export_pdf_pages(
        book, export_path, start_page, end_page, original_pdf
    )

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to export PDF pages"
        )

    # Return the file
    filename = f"{book_id}_pages_{start_page + 1}-{end_page + 1}.pdf"
    return FileResponse(
        export_path,
        media_type="application/pdf",
        filename=filename,
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@app.get("/api/pdf/{book_id}/text-layer/{page_num}")
async def get_pdf_text_layer(book_id: str, page_num: int):
    """
    Get the text layer (positioned text blocks) for a PDF page.
    Useful for implementing accurate text selection and highlighting.
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    if page_num < 0 or page_num >= book.pdf_total_pages:
        raise HTTPException(status_code=404, detail="Page not found")

    if page_num not in book.pdf_page_data:
        return {"page": page_num, "text_blocks": []}

    page_data = book.pdf_page_data[page_num]
    blocks = [
        {
            "text": b.text,
            "x0": b.x0,
            "y0": b.y0,
            "x1": b.x1,
            "y1": b.y1,
            "block_no": b.block_no,
            "line_no": b.line_no,
            "word_no": b.word_no
        }
        for b in page_data.text_blocks
    ]

    return {
        "page": page_num,
        "width": page_data.width,
        "height": page_data.height,
        "text_blocks": blocks
    }


# ============================================================================
# Reading Sessions API
# ============================================================================


@app.post("/api/sessions/start")
async def start_reading_session(request: Request):
    """Start a new reading session."""
    data = await request.json()
    
    session = ReadingSession(
        id=generate_id(),
        book_id=data.get("book_id", ""),
        book_title=data.get("book_title", ""),
        chapter_index=data.get("chapter_index", 0),
        chapter_title=data.get("chapter_title", ""),
    )
    user_data_manager.start_reading_session(session)
    return {"session_id": session.id, "status": "started"}


@app.post("/api/sessions/{session_id}/end")
async def end_reading_session(session_id: str, request: Request):
    """End a reading session."""
    data = await request.json()
    
    success = user_data_manager.end_reading_session(
        session_id=session_id,
        duration_seconds=data.get("duration_seconds", 0),
        pages_read=data.get("pages_read", 0),
        scroll_position=data.get("scroll_position", 0.0)
    )
    
    if success:
        return {"status": "ended"}
    raise HTTPException(status_code=404, detail="Session not found")


@app.get("/api/sessions")
async def get_reading_sessions(book_id: str = None, limit: int = 20):
    """Get reading sessions."""
    sessions = user_data_manager.get_reading_sessions(book_id, limit)
    return {
        "sessions": [
            {
                "id": s.id,
                "book_id": s.book_id,
                "book_title": s.book_title,
                "chapter_index": s.chapter_index,
                "chapter_title": s.chapter_title,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "duration_seconds": s.duration_seconds,
                "pages_read": s.pages_read,
            }
            for s in sessions
        ]
    }


@app.get("/api/sessions/stats")
async def get_reading_stats(book_id: str = None):
    """Get reading statistics."""
    stats = user_data_manager.get_reading_stats(book_id)
    return stats


# ============================================================================
# Vocabulary/Dictionary API
# ============================================================================


@app.post("/api/vocabulary/{book_id}")
async def add_vocabulary_word(book_id: str, request: Request):
    """Add a word to vocabulary."""
    data = await request.json()
    
    word = VocabularyWord(
        id=generate_id(),
        book_id=book_id,
        word=data.get("word", ""),
        definition=data.get("definition", ""),
        phonetic=data.get("phonetic"),
        part_of_speech=data.get("part_of_speech"),
        example=data.get("example"),
        chapter_index=data.get("chapter_index", 0),
        context=data.get("context", ""),
    )
    saved_word = user_data_manager.add_vocabulary_word(word)
    return {"id": saved_word.id, "status": "saved"}


@app.get("/api/vocabulary/{book_id}")
async def get_vocabulary(book_id: str):
    """Get vocabulary words for a book."""
    words = user_data_manager.get_vocabulary(book_id)
    return {
        "book_id": book_id,
        "words": [
            {
                "id": w.id,
                "word": w.word,
                "definition": w.definition,
                "phonetic": w.phonetic,
                "part_of_speech": w.part_of_speech,
                "example": w.example,
                "chapter_index": w.chapter_index,
                "context": w.context,
                "created_at": w.created_at,
                "reviewed_count": w.reviewed_count,
            }
            for w in words
        ]
    }


@app.get("/api/vocabulary")
async def get_all_vocabulary():
    """Get all vocabulary words across all books."""
    words = user_data_manager.get_vocabulary()
    return {
        "words": [
            {
                "id": w.id,
                "book_id": w.book_id,
                "word": w.word,
                "definition": w.definition,
                "phonetic": w.phonetic,
                "part_of_speech": w.part_of_speech,
                "example": w.example,
                "chapter_index": w.chapter_index,
                "context": w.context,
                "created_at": w.created_at,
                "reviewed_count": w.reviewed_count,
            }
            for w in words
        ]
    }


@app.delete("/api/vocabulary/{book_id}/{word_id}")
async def delete_vocabulary_word(book_id: str, word_id: str):
    """Delete a vocabulary word."""
    if user_data_manager.delete_vocabulary_word(book_id, word_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Word not found")


@app.get("/api/vocabulary/search")
async def search_vocabulary(q: str):
    """Search vocabulary words."""
    if not q or len(q) < 2:
        return {"results": [], "query": q}
    
    words = user_data_manager.search_vocabulary(q)
    return {
        "query": q,
        "results": [
            {
                "id": w.id,
                "book_id": w.book_id,
                "word": w.word,
                "definition": w.definition,
                "phonetic": w.phonetic,
                "part_of_speech": w.part_of_speech,
            }
            for w in words
        ]
    }


# ============================================================================
# Annotations API
# ============================================================================


@app.post("/api/annotations/{book_id}")
async def add_annotation(book_id: str, request: Request):
    """Add an annotation."""
    data = await request.json()
    
    annotation = Annotation(
        id=generate_id(),
        book_id=book_id,
        chapter_index=data.get("chapter_index", 0),
        note_text=data.get("note_text", ""),
        highlight_id=data.get("highlight_id"),
        bookmark_id=data.get("bookmark_id"),
        position_offset=data.get("position_offset", 0),
        tags=data.get("tags", []),
    )
    user_data_manager.add_annotation(annotation)
    return {"id": annotation.id, "status": "created"}


@app.get("/api/annotations/{book_id}")
async def get_annotations(book_id: str, chapter: int = None):
    """Get annotations for a book."""
    annotations = user_data_manager.get_annotations(book_id, chapter)
    return {
        "book_id": book_id,
        "annotations": [
            {
                "id": a.id,
                "chapter_index": a.chapter_index,
                "note_text": a.note_text,
                "highlight_id": a.highlight_id,
                "bookmark_id": a.bookmark_id,
                "position_offset": a.position_offset,
                "tags": a.tags,
                "created_at": a.created_at,
                "updated_at": a.updated_at,
            }
            for a in annotations
        ]
    }


@app.put("/api/annotations/{book_id}/{annotation_id}")
async def update_annotation(book_id: str, annotation_id: str, request: Request):
    """Update an annotation."""
    data = await request.json()
    
    success = user_data_manager.update_annotation(
        book_id=book_id,
        annotation_id=annotation_id,
        note_text=data.get("note_text", ""),
        tags=data.get("tags")
    )
    
    if success:
        return {"status": "updated"}
    raise HTTPException(status_code=404, detail="Annotation not found")


@app.delete("/api/annotations/{book_id}/{annotation_id}")
async def delete_annotation(book_id: str, annotation_id: str):
    """Delete an annotation."""
    if user_data_manager.delete_annotation(book_id, annotation_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Annotation not found")


@app.get("/api/annotations/{book_id}/search")
async def search_annotations(book_id: str, q: str):
    """Search annotations by text or tags."""
    if not q or len(q) < 2:
        return {"results": [], "query": q}
    
    annotations = user_data_manager.search_annotations(book_id, q)
    return {
        "query": q,
        "results": [
            {
                "id": a.id,
                "chapter_index": a.chapter_index,
                "note_text": a.note_text,
                "tags": a.tags,
                "created_at": a.created_at,
            }
            for a in annotations
        ]
    }


@app.get("/api/annotations/{book_id}/export")
async def export_annotations(book_id: str, format: str = "markdown"):
    """Export annotations to Markdown."""
    if format == "markdown":
        content = user_data_manager.export_annotations_markdown(book_id)
        return PlainTextResponse(
            content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": 
                    f"attachment; filename={book_id}_annotations.md"
            }
        )
    else:
        # JSON export
        annotations = user_data_manager.get_annotations(book_id)
        import json
        content = json.dumps(
            {"annotations": [
                {
                    "id": a.id,
                    "chapter_index": a.chapter_index,
                    "note_text": a.note_text,
                    "tags": a.tags,
                    "created_at": a.created_at,
                }
                for a in annotations
            ]},
            indent=2
        )
        return PlainTextResponse(
            content,
            media_type="application/json",
            headers={
                "Content-Disposition":
                    f"attachment; filename={book_id}_annotations.json"
            }
        )


if __name__ == "__main__":
    import uvicorn

    print("Starting server at http://127.0.0.1:8123")
    uvicorn.run(app, host="127.0.0.1", port=8123)
