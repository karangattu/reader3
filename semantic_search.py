"""
Lightweight semantic search indexing and scoring for Reader3.
Uses TF/BM25-style ranking with a persistent per-book index.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

INDEX_VERSION = 1
INDEX_FILENAME = "semantic_index.json"

TOKEN_RE = re.compile(r"[A-Za-z0-9']+")

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "has", "have", "he", "her", "his", "i", "in", "is", "it", "its", "me",
    "my", "not", "of", "on", "or", "our", "she", "that", "the", "their",
    "them", "there", "these", "they", "this", "to", "was", "were", "will",
    "with", "you", "your",
}

_INDEX_CACHE: Dict[str, Dict[str, Any]] = {}


def _normalize_token(token: str) -> str:
    token = token.strip("'").lower()
    if len(token) < 2:
        return ""
    if token.isdigit():
        return ""
    for suffix in ("ing", "edly", "ed", "ly", "es", "s"):
        if token.endswith(suffix) and len(token) > len(suffix) + 2:
            token = token[: -len(suffix)]
            break
    return token


def _tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for match in TOKEN_RE.finditer(text or ""):
        token = _normalize_token(match.group(0))
        if token and token not in STOPWORDS:
            tokens.append(token)
    return tokens


def _index_path(book_dir: str) -> str:
    return os.path.join(book_dir, INDEX_FILENAME)


def _load_index(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    mtime = os.path.getmtime(path)
    cached = _INDEX_CACHE.get(path)
    if cached and cached.get("mtime") == mtime:
        return cached.get("data")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _INDEX_CACHE[path] = {"mtime": mtime, "data": data}
    return data


def _write_index(path: str, data: Dict[str, Any]) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=True)
    os.replace(tmp_path, path)
    _INDEX_CACHE[path] = {"mtime": os.path.getmtime(path), "data": data}


def _should_rebuild(index: Optional[Dict[str, Any]], book: Any) -> bool:
    if not index:
        return True
    if index.get("index_version") != INDEX_VERSION:
        return True
    if index.get("processed_at") != getattr(book, "processed_at", ""):
        return True
    if index.get("chapter_count") != len(getattr(book, "spine", [])):
        return True
    return False


def ensure_book_index(book_id: str, book: Any, book_dir: str) -> Dict[str, Any]:
    """Ensure an up-to-date semantic index exists for a book."""
    index_path = _index_path(book_dir)
    index = _load_index(index_path)
    if not _should_rebuild(index, book):
        return index

    documents = []
    for chapter_index, chapter in enumerate(getattr(book, "spine", [])):
        text = getattr(chapter, "text", "") or ""
        tokens = _tokenize(text)
        if not tokens:
            continue
        term_freq = Counter(tokens)
        documents.append(
            {
                "chapter_index": chapter_index,
                "chapter_title": getattr(chapter, "title", ""),
                "chapter_href": getattr(chapter, "href", ""),
                "length": len(tokens),
                "term_freq": dict(term_freq),
            }
        )

    index = {
        "index_version": INDEX_VERSION,
        "book_id": book_id,
        "book_title": getattr(getattr(book, "metadata", None), "title", ""),
        "processed_at": getattr(book, "processed_at", ""),
        "generated_at": datetime.utcnow().isoformat(),
        "chapter_count": len(getattr(book, "spine", [])),
        "documents": documents,
    }
    _write_index(index_path, index)
    return index


def _build_context(text: str, match_pos: int, match_len: int) -> str:
    if not text:
        return ""
    context_start = max(0, match_pos - 100)
    context_end = min(len(text), match_pos + match_len + 100)
    context = text[context_start:context_end]
    if context_start > 0:
        space_idx = context.find(" ")
        if 0 < space_idx < 30:
            context = context[space_idx + 1 :]
        context = "..." + context
    if context_end < len(text):
        space_idx = context.rfind(" ")
        if space_idx > len(context) - 30:
            context = context[:space_idx]
        context = context + "..."
    return context.strip()


def _find_match(text_lower: str, terms: Iterable[str]) -> Tuple[int, int]:
    best_pos = -1
    best_len = 0
    for term in terms:
        if not term:
            continue
        pos = text_lower.find(term)
        if pos != -1 and (best_pos == -1 or pos < best_pos):
            best_pos = pos
            best_len = len(term)
    return best_pos, best_len


def semantic_search_books(
    query: str,
    book_ids: List[str],
    books_dir: str,
    load_book_fn,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Run a semantic search across the provided book IDs."""
    raw_tokens = [t.lower() for t in TOKEN_RE.findall(query or "")]
    raw_tokens = [t for t in raw_tokens if len(t) > 1 and t not in STOPWORDS]
    query_terms = [_normalize_token(t) for t in raw_tokens]
    query_terms = [t for t in query_terms if t and t not in STOPWORDS]

    if not query_terms:
        return []

    docs: List[Tuple[str, Any, Dict[str, Any]]] = []
    doc_lengths: List[int] = []

    for book_id in book_ids:
        book = load_book_fn(book_id)
        if not book:
            continue
        book_dir = os.path.join(books_dir, book_id)
        index = ensure_book_index(book_id, book, book_dir)
        for doc in index.get("documents", []):
            length = int(doc.get("length", 0))
            if length <= 0:
                continue
            docs.append((book_id, book, doc))
            doc_lengths.append(length)

    if not docs:
        return []

    total_docs = len(docs)
    avg_doc_len = sum(doc_lengths) / total_docs

    df = {term: 0 for term in set(query_terms)}
    for _, _, doc in docs:
        term_freq = doc.get("term_freq", {})
        for term in df:
            if term in term_freq:
                df[term] += 1

    k1 = 1.2
    b = 0.75
    scored: List[Tuple[float, str, Any, Dict[str, Any]]] = []

    for book_id, book, doc in docs:
        term_freq = doc.get("term_freq", {})
        doc_len = float(doc.get("length", 0))
        score = 0.0
        for term, doc_freq in df.items():
            tf = term_freq.get(term, 0)
            if tf <= 0:
                continue
            idf = math.log(1 + (total_docs - doc_freq + 0.5) / (doc_freq + 0.5))
            denom = tf + k1 * (1 - b + b * doc_len / avg_doc_len)
            score += idf * (tf * (k1 + 1) / denom)
        if score > 0:
            scored.append((score, book_id, book, doc))

    scored.sort(key=lambda item: item[0], reverse=True)

    results: List[Dict[str, Any]] = []
    for score, book_id, book, doc in scored[:limit]:
        chapter_index = int(doc.get("chapter_index", 0))
        chapter = None
        if 0 <= chapter_index < len(getattr(book, "spine", [])):
            chapter = book.spine[chapter_index]
        text = getattr(chapter, "text", "") if chapter else ""
        text_lower = text.lower()
        match_pos, match_len = _find_match(text_lower, raw_tokens)
        if match_pos == -1:
            match_pos, match_len = _find_match(text_lower, query_terms)
        if match_pos == -1:
            match_pos, match_len = 0, 0
        context = _build_context(text, match_pos, match_len)

        results.append(
            {
                "book_id": book_id,
                "book_title": getattr(getattr(book, "metadata", None), "title", ""),
                "chapter_index": chapter_index,
                "chapter_href": doc.get("chapter_href", ""),
                "chapter_title": doc.get("chapter_title", ""),
                "context": context,
                "position": match_pos,
                "match_length": match_len,
                "score": round(score, 6),
            }
        )

    return results
