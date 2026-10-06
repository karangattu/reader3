"""PDF API routes."""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

from reader3.api.deps import (
    BOOKS_DIR,
    PDF_COPY_IMAGE_DPI,
    _render_pdf_page_image_bytes,
    load_book_cached,
)
from reader3.services.library import (
    export_pdf_pages,
    get_pdf_page_stats,
    get_pdf_text_blocks_for_page,
    search_pdf_text_positions,
)

router = APIRouter()


@router.get("/api/v1/pdf/{book_id}/page-image/{page_num}")
async def render_pdf_page_image(
    book_id: str,
    page_num: int,
    dpi: int = PDF_COPY_IMAGE_DPI,
):
    """Render a PDF page on demand as a PNG for clipboard/export workflows."""
    image_bytes = _render_pdf_page_image_bytes(book_id, page_num, dpi=dpi)
    return Response(content=image_bytes, media_type="image/png")


@router.get("/api/v1/pdf/{book_id}/stats")
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


@router.get("/api/v1/pdf/{book_id}/thumbnails")
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


@router.get("/read/{book_id}/thumbnails/{thumb_name}")
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


@router.get("/api/v1/pdf/{book_id}/annotations")
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


@router.get("/api/v1/pdf/{book_id}/search-positions")
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


@router.get("/api/v1/pdf/{book_id}/page/{page_num}")
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
        "text_block_count": 0  # Text blocks now extracted on-demand
    }


@router.get("/api/v1/pdf/{book_id}/outline")
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


@router.post("/api/v1/pdf/{book_id}/export")
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


@router.get("/api/v1/pdf/{book_id}/text-layer/{page_num}")
async def get_pdf_text_layer(book_id: str, page_num: int):
    """
    Get the text layer (positioned text blocks) for a PDF page.
    Useful for implementing accurate text selection and highlighting.
    
    Text blocks are now extracted on-demand from the source PDF
    to reduce pickle file size and memory usage.
    """
    book = load_book_cached(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not book.is_pdf:
        raise HTTPException(status_code=400, detail="Not a PDF book")

    if page_num < 0 or page_num >= book.pdf_total_pages:
        raise HTTPException(status_code=404, detail="Page not found")

    # Get page dimensions from stored data
    page_data = book.pdf_page_data.get(page_num)
    width = page_data.width if page_data else 0
    height = page_data.height if page_data else 0
    
    # Extract text blocks on-demand from source PDF
    book_dir = os.path.join(BOOKS_DIR, book_id)
    text_blocks = get_pdf_text_blocks_for_page(book, page_num, book_dir)
    
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
        for b in text_blocks
    ]

    return {
        "page": page_num,
        "width": width,
        "height": height,
        "text_blocks": blocks
    }
