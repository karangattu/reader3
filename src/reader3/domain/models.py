"""Core document models used by Reader3 services."""

from reader3.services.library import (
    Book,
    BookMetadata,
    ChapterContent,
    PDFAnnotation,
    PDFPageData,
    PDFTextBlock,
    TOCEntry,
)

__all__ = [
    "Book",
    "BookMetadata",
    "ChapterContent",
    "PDFAnnotation",
    "PDFPageData",
    "PDFTextBlock",
    "TOCEntry",
]
