"""Compatibility shim for the Reader3 package.

The implementation now lives under ``src/reader3``. This file preserves the
historical ``import reader3`` API for scripts, tests, and existing pickles.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ebooklib import epub as epub

_PACKAGE_DIR = Path(__file__).resolve().parent / "src" / "reader3"
__path__ = [str(_PACKAGE_DIR)]
sys.modules.setdefault(__name__ + ".epub", epub)

from reader3.services.library import (  # noqa: E402,F401
    Book,
    BookMetadata,
    ChapterContent,
    DocumentService,
    PDFAnnotation,
    PDFPageData,
    PDFTextBlock,
    TOCEntry,
    clean_html_content,
    collect_toc_spine_indices,
    complete_toc_with_spine,
    export_pdf_pages,
    extract_chapter_title,
    extract_cover_image,
    extract_metadata_robust,
    extract_pdf_annotations,
    extract_pdf_images,
    extract_pdf_outline,
    extract_pdf_text_blocks,
    extract_plain_text,
    find_spine_index_for_href,
    generate_pdf_page_image,
    generate_pdf_thumbnail,
    get_fallback_toc,
    get_pdf_page_stats,
    get_pdf_text_blocks_for_page,
    is_content_document,
    normalize_content_href,
    parse_toc_recursive,
    process_epub,
    process_pdf,
    sanitize_book_text_fields,
    sanitize_text,
    sanitize_toc_entries,
    save_to_pickle,
    search_pdf_text_positions,
    validate_pdf,
)

__all__ = [name for name in globals() if not name.startswith("_")]
