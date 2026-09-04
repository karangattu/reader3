"""Thin search API routes."""

from __future__ import annotations

from fastapi import APIRouter

from reader3.api.deps import (
    get_all_book_ids,
    get_search_service,
    _run_sync,
    user_data_manager,
    SearchQuery,
)

router = APIRouter()

@router.get("/api/v1/search")
async def search_books(q: str, book_id: str | None = None, mode: str = "exact"):
    if not q or len(q) < 2:
        return {"results": [], "query": q, "total": 0, "mode": mode}

    book_ids = [book_id] if book_id else get_all_book_ids()
    max_total_results = 500

    def _do_search():
        return get_search_service().search(
            q,
            book_ids,
            mode=mode,
            limit=max_total_results,
        )

    results = await _run_sync(_do_search)
    user_data_manager.add_search(
        SearchQuery(query=q, book_id=book_id, results_count=len(results))
    )
    return {"query": q, "results": results, "total": len(results), "mode": mode}


@router.get("/api/v1/search/history")
async def get_search_history(limit: int = 20):
    history = user_data_manager.get_search_history(limit)
    return {
        "history": [
            {
                "query": item.query,
                "book_id": item.book_id,
                "timestamp": item.timestamp,
                "results_count": item.results_count,
            }
            for item in history
        ]
    }


@router.delete("/api/v1/search/history")
async def clear_search_history():
    user_data_manager.clear_search_history()
    return {"status": "cleared"}
