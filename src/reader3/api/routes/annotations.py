"""Annotations API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
import json

from reader3.api.deps import (
    get_reader_service,
    user_data_manager,
    Annotation,
    generate_id,
    VocabularyWord,
)

router = APIRouter()


# ============================================================================
# Bookmarks API
# ============================================================================


@router.get("/api/v1/bookmarks/{book_id}")
async def get_bookmarks(book_id: str):
    """Get all bookmarks for a book."""
    reader_service = get_reader_service()
    bookmarks = user_data_manager.get_bookmarks(book_id)
    return {
        "book_id": book_id,
        "bookmarks": [
            reader_service.serialize_bookmark(bookmark)
            for bookmark in bookmarks
        ],
    }


@router.post("/api/v1/bookmarks/{book_id}")
async def add_bookmark(book_id: str, request: Request):
    """Add a bookmark."""
    data = await request.json()
    bookmark = get_reader_service().add_bookmark(book_id, data)
    return {"id": bookmark.id, "status": "created"}


@router.delete("/api/v1/bookmarks/{book_id}/{bookmark_id}")
async def delete_bookmark(book_id: str, bookmark_id: str):
    """Delete a bookmark."""
    if user_data_manager.delete_bookmark(book_id, bookmark_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Bookmark not found")


@router.put("/api/v1/bookmarks/{book_id}/{bookmark_id}")
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


@router.get("/api/v1/highlights/{book_id}")
async def get_highlights(book_id: str, chapter: int = None):
    """Get highlights for a book, optionally filtered by chapter."""
    reader_service = get_reader_service()
    highlights = user_data_manager.get_highlights(book_id, chapter)
    return {
        "book_id": book_id,
        "highlights": [
            reader_service.serialize_highlight(highlight)
            for highlight in highlights
        ],
    }


@router.post("/api/v1/highlights/{book_id}")
async def add_highlight(book_id: str, request: Request):
    """Add a highlight."""
    data = await request.json()
    highlight = get_reader_service().add_highlight(book_id, data)
    return {"id": highlight.id, "status": "created"}


@router.delete("/api/v1/highlights/{book_id}/{highlight_id}")
async def delete_highlight(book_id: str, highlight_id: str):
    """Delete a highlight."""
    if user_data_manager.delete_highlight(book_id, highlight_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Highlight not found")


@router.put("/api/v1/highlights/{book_id}/{highlight_id}")
async def update_highlight(book_id: str, highlight_id: str, request: Request):
    """Update a highlight's note."""
    data = await request.json()
    note = data.get("note", "")

    if user_data_manager.update_highlight_note(book_id, highlight_id, note):
        return {"status": "updated"}
    raise HTTPException(status_code=404, detail="Highlight not found")


@router.put("/api/v1/highlights/{book_id}/{highlight_id}/color")
async def update_highlight_color(book_id: str, highlight_id: str, request: Request):
    """Update a highlight's color."""
    data = await request.json()
    color = data.get("color", "yellow")

    if user_data_manager.update_highlight_color(book_id, highlight_id, color):
        return {"status": "updated"}
    raise HTTPException(status_code=404, detail="Highlight not found")


# ============================================================================
# Vocabulary/Dictionary API
# ============================================================================


@router.get("/api/v1/vocabulary/search")
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


@router.post("/api/v1/vocabulary/{book_id}")
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


@router.get("/api/v1/vocabulary/{book_id}")
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


@router.get("/api/v1/vocabulary")
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


@router.delete("/api/v1/vocabulary/{book_id}/{word_id}")
async def delete_vocabulary_word(book_id: str, word_id: str):
    """Delete a vocabulary word."""
    if user_data_manager.delete_vocabulary_word(book_id, word_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Word not found")


# ============================================================================
# Annotations API
# ============================================================================


@router.post("/api/v1/annotations/{book_id}")
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


@router.get("/api/v1/annotations/{book_id}")
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


@router.put("/api/v1/annotations/{book_id}/{annotation_id}")
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


@router.delete("/api/v1/annotations/{book_id}/{annotation_id}")
async def delete_annotation(book_id: str, annotation_id: str):
    """Delete an annotation."""
    if user_data_manager.delete_annotation(book_id, annotation_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Annotation not found")


@router.get("/api/v1/annotations/{book_id}/search")
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


@router.get("/api/v1/annotations/{book_id}/export")
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


# ========== Collections API ==========

@router.get("/api/v1/collections")
async def get_collections():
    """Get all collections."""
    collections = user_data_manager.get_collections()
    return {
        "collections": [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "icon": c.icon,
                "color": c.color,
                "book_count": len(c.book_ids),
                "book_ids": c.book_ids,
                "created_at": c.created_at,
                "updated_at": c.updated_at,
            }
            for c in collections
        ]
    }


@router.put("/api/v1/collections/reorder")
async def reorder_collections(request: Request):
    """Reorder collections."""
    data = await request.json()
    collection_ids = data.get("collection_ids", [])
    
    user_data_manager.reorder_collections(collection_ids)
    return {"status": "reordered"}


@router.post("/api/v1/collections")
async def create_collection(request: Request):
    """Create a new collection."""
    data = await request.json()
    name = data.get("name", "").strip()
    
    if not name:
        raise HTTPException(status_code=400, detail="Collection name is required")
    
    description = data.get("description", "")
    icon = data.get("icon", "folder")
    color = data.get("color", "#3498db")
    
    collection = user_data_manager.create_collection(
        name=name,
        description=description,
        icon=icon,
        color=color
    )
    
    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "icon": collection.icon,
        "color": collection.color,
        "book_count": 0,
        "book_ids": [],
        "created_at": collection.created_at,
    }


@router.get("/api/v1/collections/{collection_id}")
async def get_collection(collection_id: str):
    """Get a single collection."""
    collection = user_data_manager.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "icon": collection.icon,
        "color": collection.color,
        "book_count": len(collection.book_ids),
        "book_ids": collection.book_ids,
        "created_at": collection.created_at,
        "updated_at": collection.updated_at,
    }


@router.put("/api/v1/collections/{collection_id}")
async def update_collection(collection_id: str, request: Request):
    """Update a collection."""
    data = await request.json()
    
    success = user_data_manager.update_collection(
        collection_id=collection_id,
        name=data.get("name"),
        description=data.get("description"),
        icon=data.get("icon"),
        color=data.get("color")
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    # Return updated collection
    collection = user_data_manager.get_collection(collection_id)
    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "icon": collection.icon,
        "color": collection.color,
        "book_count": len(collection.book_ids),
        "book_ids": collection.book_ids,
        "updated_at": collection.updated_at,
    }


@router.delete("/api/v1/collections/{collection_id}")
async def delete_collection(collection_id: str):
    """Delete a collection."""
    if user_data_manager.delete_collection(collection_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Collection not found")


@router.post("/api/v1/collections/{collection_id}/books/{book_id}")
async def add_book_to_collection(collection_id: str, book_id: str):
    """Add a book to a collection."""
    if user_data_manager.add_book_to_collection(collection_id, book_id):
        return {"status": "added", "collection_id": collection_id, "book_id": book_id}
    raise HTTPException(status_code=404, detail="Collection not found")


@router.delete("/api/v1/collections/{collection_id}/books/{book_id}")
async def remove_book_from_collection(collection_id: str, book_id: str):
    """Remove a book from a collection."""
    if user_data_manager.remove_book_from_collection(collection_id, book_id):
        return {"status": "removed", "collection_id": collection_id, "book_id": book_id}
    raise HTTPException(status_code=404, detail="Collection not found")


@router.get("/api/v1/books/{book_id}/collections")
async def get_book_collections(book_id: str):
    """Get all collections that contain a specific book."""
    collections = user_data_manager.get_book_collections(book_id)
    return {
        "book_id": book_id,
        "collections": [
            {
                "id": c.id,
                "name": c.name,
                "icon": c.icon,
                "color": c.color,
            }
            for c in collections
        ]
    }


@router.put("/api/v1/books/{book_id}/collections")
async def set_book_collections(book_id: str, request: Request):
    """Set which collections a book belongs to."""
    data = await request.json()
    collection_ids = data.get("collection_ids", [])
    
    user_data_manager.set_book_collections(book_id, collection_ids)
    
    # Return updated list
    collections = user_data_manager.get_book_collections(book_id)
    return {
        "book_id": book_id,
        "collections": [
            {
                "id": c.id,
                "name": c.name,
                "icon": c.icon,
                "color": c.color,
            }
            for c in collections
        ]
    }
