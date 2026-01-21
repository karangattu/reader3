"""
Parses an EPUB file into a structured object that can be used to serve the book via a web interface.
"""

import os
import pickle
import shutil
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
from urllib.parse import unquote

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup, Comment

# --- Data structures ---

@dataclass
class ChapterContent:
    """
    Represents a physical file in the EPUB (Spine Item).
    A single file might contain multiple logical chapters (TOC entries).
    """
    id: str           # Internal ID (e.g., 'item_1')
    href: str         # Filename (e.g., 'part01.html')
    title: str        # Best guess title from file
    content: str      # Cleaned HTML with rewritten image paths
    text: str         # Plain text for search/LLM context
    order: int        # Linear reading order


@dataclass
class TOCEntry:
    """Represents a logical entry in the navigation sidebar."""
    title: str
    href: str         # original href (e.g., 'part01.html#chapter1')
    file_href: str    # just the filename (e.g., 'part01.html')
    anchor: str       # just the anchor (e.g., 'chapter1'), empty if none
    children: List['TOCEntry'] = field(default_factory=list)


@dataclass
class BookMetadata:
    """Metadata"""
    title: str
    language: str
    authors: List[str] = field(default_factory=list)
    description: Optional[str] = None
    publisher: Optional[str] = None
    date: Optional[str] = None
    identifiers: List[str] = field(default_factory=list)
    subjects: List[str] = field(default_factory=list)


@dataclass
class PDFAnnotation:
    """Represents an annotation from a PDF."""
    page: int
    type: str           # highlight, underline, strikeout, note, etc.
    content: str        # Annotation content/text
    rect: List[float]   # [x0, y0, x1, y1] position
    color: Optional[str] = None
    author: Optional[str] = None
    created: Optional[str] = None


@dataclass
class PDFTextBlock:
    """Represents a positioned text block in a PDF page for accurate highlighting."""
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    block_no: int
    line_no: int
    word_no: int


@dataclass
class PDFPageData:
    """Extended data for a PDF page."""
    page_num: int
    width: float
    height: float
    rotation: int
    # Note: text_blocks removed - now generated on-demand from source PDF to reduce pickle size
    annotations: List[PDFAnnotation] = field(default_factory=list)
    has_images: bool = False
    word_count: int = 0


@dataclass
class Book:
    """The Master Object to be pickled."""
    metadata: BookMetadata
    spine: List[ChapterContent]  # The actual content (linear files)
    toc: List[TOCEntry]          # The navigation tree
    images: Dict[str, str]       # Map: original_path -> local_path

    # Meta info
    source_file: str
    processed_at: str
    added_at: str = ""  # Timestamp when book was added to library
    version: str = "3.0"
    is_pdf: bool = False  # Flag to indicate if this is a PDF book
    # Path to cover image (relative), e.g., 'images/cover.jpg'
    cover_image: Optional[str] = None
    
    # PDF-specific data
    pdf_page_data: Dict[int, PDFPageData] = field(default_factory=dict)
    pdf_total_pages: int = 0
    pdf_has_toc: bool = False  # True if PDF has native outline/bookmarks
    pdf_thumbnails_generated: bool = False
    pdf_source_path: Optional[str] = None  # Path to stored PDF for on-demand text extraction


# --- Utilities ---

def clean_html_content(soup: BeautifulSoup) -> BeautifulSoup:

    # Remove dangerous/useless tags
    for tag in soup(['script', 'style', 'iframe', 'video', 'nav', 'form', 'button']):
        tag.decompose()

    # Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Remove input tags
    for tag in soup.find_all('input'):
        tag.decompose()

    return soup


def extract_plain_text(soup: BeautifulSoup) -> str:
    """Extract clean text for LLM/Search usage."""
    text = soup.get_text(separator=' ')
    # Collapse whitespace
    return ' '.join(text.split())


def parse_toc_recursive(toc_list, depth=0) -> List[TOCEntry]:
    """
    Recursively parses the TOC structure from ebooklib.
    """
    result = []

    for item in toc_list:
        # ebooklib TOC items are either `Link` objects or tuples (Section, [Children])
        if isinstance(item, tuple):
            section, children = item
            entry = TOCEntry(
                title=section.title,
                href=section.href,
                file_href=section.href.split('#')[0],
                anchor=section.href.split('#')[1] if '#' in section.href else "",
                children=parse_toc_recursive(children, depth + 1)
            )
            result.append(entry)
        elif isinstance(item, epub.Link):
            entry = TOCEntry(
                title=item.title,
                href=item.href,
                file_href=item.href.split('#')[0],
                anchor=item.href.split('#')[1] if '#' in item.href else ""
            )
            result.append(entry)
        # Note: ebooklib sometimes returns direct Section objects without children
        elif isinstance(item, epub.Section):
             entry = TOCEntry(
                title=item.title,
                href=item.href,
                file_href=item.href.split('#')[0],
                anchor=item.href.split('#')[1] if '#' in item.href else ""
            )
             result.append(entry)

    return result


def is_content_document(item) -> bool:
    """
    Check if an item is a content document (HTML/XHTML).
    Extends ebooklib's ITEM_DOCUMENT detection to also check media type and file extension.
    This ensures TOC entries map to real chapters and produces a complete spine.
    """
    # First check ebooklib's native detection
    if item.get_type() == ebooklib.ITEM_DOCUMENT:
        return True
    
    # Check media type for HTML content
    media_type = getattr(item, 'media_type', '') or ''
    if media_type in ('text/html', 'application/xhtml+xml'):
        return True
    
    # Check file extension as fallback
    name = item.get_name() or ''
    name_lower = name.lower()
    if name_lower.endswith(('.html', '.xhtml', '.htm')):
        return True
    
    return False


def get_fallback_toc(book_obj) -> List[TOCEntry]:
    """
    If TOC is missing, build a flat one from the Spine.
    """
    toc = []
    for item in book_obj.get_items():
        if is_content_document(item):
            name = item.get_name()
            # Try to guess a title from the content or ID
            title = item.get_name().replace('.html', '').replace('.xhtml', '').replace('_', ' ').title()
            toc.append(TOCEntry(title=title, href=name, file_href=name, anchor=""))
    return toc


def extract_metadata_robust(book_obj) -> BookMetadata:
    """
    Extracts metadata handling both single and list values.
    """
    def get_list(key):
        data = book_obj.get_metadata('DC', key)
        return [x[0] for x in data] if data else []

    def get_one(key):
        data = book_obj.get_metadata('DC', key)
        return data[0][0] if data else None

    return BookMetadata(
        title=get_one('title') or "Untitled",
        language=get_one('language') or "en",
        authors=get_list('creator'),
        description=get_one('description'),
        publisher=get_one('publisher'),
        date=get_one('date'),
        identifiers=get_list('identifier'),
        subjects=get_list('subject')
    )


# --- Main Conversion Logic ---

def extract_pdf_outline(doc) -> List[TOCEntry]:
    """
    Extract the PDF's native outline/bookmarks as a hierarchical TOC.
    Returns empty list if PDF has no outline.
    """
    toc = doc.get_toc()  # Returns list of [level, title, page, dest]
    if not toc:
        return []

    result = []
    stack = [(0, result)]  # (current_level, current_list)

    for item in toc:
        level, title, page = item[0], item[1], item[2]
        page_idx = max(0, page - 1)  # Convert to 0-based index

        entry = TOCEntry(
            title=title or f"Section (Page {page})",
            href=f"page_{page_idx + 1}",
            file_href=f"page_{page_idx + 1}",
            anchor="",
            children=[]
        )

        # Find the right parent level
        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            stack[-1][1].append(entry)
        else:
            result.append(entry)

        stack.append((level, entry.children))

    return result


def extract_pdf_annotations(page) -> List[PDFAnnotation]:
    """Extract annotations from a PDF page."""
    annotations = []

    for annot in page.annots() or []:
        annot_type = annot.type[1] if annot.type else "unknown"

        # Get annotation info
        info = annot.info
        content = info.get("content", "") or ""
        author = info.get("title", "")  # 'title' often contains author
        created = info.get("creationDate", "")

        # Get color if available
        color = None
        if annot.colors and annot.colors.get("stroke"):
            rgb = annot.colors["stroke"]
            color = "#{:02x}{:02x}{:02x}".format(
                int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255)
            )

        rect = list(annot.rect)

        # For highlight/underline, try to get the highlighted text
        text_content = content
        if annot_type in ("Highlight", "Underline", "StrikeOut", "Squiggly"):
            try:
                # Get quads and extract text from them
                quads = annot.vertices
                if quads:
                    quad_rect = page.rect
                    text_content = page.get_text("text", clip=annot.rect).strip()
            except Exception:
                pass

        annotations.append(PDFAnnotation(
            page=page.number,
            type=annot_type.lower(),
            content=text_content or content,
            rect=rect,
            color=color,
            author=author,
            created=created
        ))

    return annotations


def extract_pdf_text_blocks(page, clip_rect=None) -> List[PDFTextBlock]:
    """
    Extract positioned text blocks from a PDF page for accurate search highlighting.
    """
    blocks = []

    # Get word-level data with positions
    words = page.get_text("words", clip=clip_rect)  # (x0, y0, x1, y1, word, ...)

    for idx, word_data in enumerate(words):
        x0, y0, x1, y1, word, block_no, line_no, word_no = word_data[:8]

        blocks.append(PDFTextBlock(
            text=word,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            block_no=block_no,
            line_no=line_no,
            word_no=word_no
        ))

    return blocks


def extract_pdf_images(page, page_num: int, images_dir: str) -> Dict[str, str]:
    """
    Extract images from a PDF page and save them.
    Returns a map of image references to file paths.
    """
    import fitz
    image_map = {}
    image_list = page.get_images(full=True)

    for img_idx, img in enumerate(image_list):
        xref = img[0]
        try:
            base_image = page.parent.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]

            # Save image
            img_filename = f"page_{page_num + 1}_img_{img_idx + 1}.{image_ext}"
            img_path = os.path.join(images_dir, img_filename)

            with open(img_path, "wb") as f:
                f.write(image_bytes)

            image_map[f"xref_{xref}"] = f"images/{img_filename}"
        except Exception as e:
            print(f"Warning: Could not extract image {xref}: {e}")

    return image_map


def generate_pdf_thumbnail(page, page_num: int, thumbs_dir: str,
                           size: int = 150) -> str:
    """
    Generate a thumbnail for a PDF page.
    Returns the relative path to the thumbnail.
    """
    import fitz
    # Calculate scale to fit within size x size
    rect = page.rect
    scale = min(size / rect.width, size / rect.height)
    matrix = fitz.Matrix(scale, scale)

    # Render page to pixmap
    pix = page.get_pixmap(matrix=matrix, alpha=False)

    # Save as PNG
    thumb_filename = f"thumb_{page_num + 1}.png"
    thumb_path = os.path.join(thumbs_dir, thumb_filename)
    pix.save(thumb_path)

    return f"thumbnails/{thumb_filename}"


def generate_pdf_page_image(page, page_num: int, images_dir: str,
                            dpi: int = 150) -> str:
    """
    Render a PDF page as a high-quality image for display.
    Returns the relative path to the image.
    """
    import fitz
    # Calculate zoom for desired DPI (72 is default PDF resolution)
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    # Render page to pixmap
    pix = page.get_pixmap(matrix=matrix, alpha=False)

    # Save as PNG
    img_filename = f"page_{page_num + 1}.png"
    img_path = os.path.join(images_dir, img_filename)
    pix.save(img_path)

    return f"images/{img_filename}"


def process_pdf(pdf_path: str, output_dir: str,
                generate_thumbnails: bool = True) -> Book:
    """
    Process a PDF file into a structured Book object.
    Renders each page as an image (like a traditional PDF reader)
    while extracting text separately for search and copy functionality.
    """
    import fitz  # PyMuPDF

    print(f"Loading {pdf_path}...")
    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    # Extract Metadata
    metadata = BookMetadata(
        title=doc.metadata.get('title') or os.path.basename(pdf_path),
        language=doc.metadata.get('language') or "en",
        authors=(
            [doc.metadata.get('author')]
            if doc.metadata.get('author') else []
        ),
        publisher=doc.metadata.get('producer'),
        date=doc.metadata.get('creationDate'),
        subjects=(
            [doc.metadata.get('subject')]
            if doc.metadata.get('subject') else []
        )
    )

    # Prepare Output Directories
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    images_dir = os.path.join(output_dir, 'images')
    thumbs_dir = os.path.join(output_dir, 'thumbnails')
    os.makedirs(images_dir, exist_ok=True)
    if generate_thumbnails:
        os.makedirs(thumbs_dir, exist_ok=True)
    
    # Copy original PDF to _data folder for on-demand text extraction
    pdf_copy_name = 'source.pdf'
    pdf_copy_path = os.path.join(output_dir, pdf_copy_name)
    shutil.copy2(pdf_path, pdf_copy_path)

    spine_chapters = []
    image_map = {}
    pdf_page_data = {}

    # Extract native outline/TOC
    print("Extracting PDF outline...")
    toc_structure = extract_pdf_outline(doc)
    has_native_toc = len(toc_structure) > 0

    if not toc_structure:
        print("No native TOC found, will create page-based navigation.")

    print(f"Processing {total_pages} PDF pages...")

    for i, page in enumerate(doc):
        rect = page.rect
        height = rect.height
        width = rect.width

        # Extract plain text for search/copy (full page, no clipping)
        page_text = page.get_text("text")

        # Render page as image for display
        page_image_path = generate_pdf_page_image(page, i, images_dir)
        image_map[f"page_{i+1}"] = page_image_path

        # Note: text_blocks no longer stored - extracted on-demand from source.pdf

        # Extract annotations
        annotations = extract_pdf_annotations(page)

        # Generate thumbnail if requested
        if generate_thumbnails:
            generate_pdf_thumbnail(page, i, thumbs_dir)

        # Store page-specific data (without text_blocks to reduce pickle size)
        pdf_page_data[i] = PDFPageData(
            page_num=i,
            width=width,
            height=height,
            rotation=page.rotation,
            annotations=annotations,
            has_images=True,  # We render the whole page as image
            word_count=len(page_text.split())
        )

        # Create chapter content - use image tag instead of messy HTML
        chapter_id = f"page_{i+1}"
        chapter_title = f"Page {i+1}"

        # HTML content shows the rendered page image
        # Text is stored separately for copy functionality
        content_html = f'''<div class="pdf-page-image-container">
<img src="{page_image_path}" alt="Page {i+1}" class="pdf-page-image" />
</div>'''

        # If no native TOC, add each page to the TOC
        if not has_native_toc:
            toc_structure.append(TOCEntry(
                title=chapter_title,
                href=chapter_id,
                file_href=chapter_id,
                anchor=""
            ))

        chapter = ChapterContent(
            id=chapter_id,
            href=chapter_id,
            title=chapter_title,
            content=content_html,
            text=page_text,  # Full text for search/copy
            order=i
        )
        spine_chapters.append(chapter)

    doc.close()

    final_book = Book(
        metadata=metadata,
        spine=spine_chapters,
        toc=toc_structure,
        images=image_map,
        source_file=os.path.basename(pdf_path),
        processed_at=datetime.now().isoformat(),
        added_at=datetime.now().isoformat(),
        is_pdf=True,
        pdf_page_data=pdf_page_data,
        pdf_total_pages=total_pages,
        pdf_has_toc=has_native_toc,
        pdf_thumbnails_generated=generate_thumbnails,
        pdf_source_path=pdf_copy_name  # Relative path to source.pdf
    )

    return final_book


def export_pdf_pages(book: Book, output_path: str, start_page: int,
                     end_page: int, original_pdf_path: str) -> bool:
    """
    Export a range of pages from a PDF to a new PDF file.
    Requires the original PDF file path since we only store text in Book.
    """
    import fitz

    if not book.is_pdf:
        raise ValueError("This function only works with PDF books")

    try:
        doc = fitz.open(original_pdf_path)
        new_doc = fitz.open()

        # Validate page range
        start_page = max(0, start_page)
        end_page = min(end_page, len(doc) - 1)

        # Copy pages
        new_doc.insert_pdf(doc, from_page=start_page, to_page=end_page)

        # Save
        new_doc.save(output_path)
        new_doc.close()
        doc.close()

        return True
    except Exception as e:
        print(f"Error exporting PDF pages: {e}")
        return False


def get_pdf_text_blocks_for_page(book: Book, page_num: int,
                                  book_dir: str) -> List[PDFTextBlock]:
    """
    Extract text blocks from a PDF page on-demand.
    This avoids storing large text_blocks data in the pickle.
    
    Args:
        book: The Book object
        page_num: Page number (0-indexed)
        book_dir: Directory where the book data is stored (contains source.pdf)
    
    Returns:
        List of PDFTextBlock objects for the page
    """
    import fitz
    
    if not book.is_pdf or not book.pdf_source_path:
        return []
    
    pdf_path = os.path.join(book_dir, book.pdf_source_path)
    if not os.path.exists(pdf_path):
        print(f"Warning: Source PDF not found at {pdf_path}")
        return []
    
    try:
        doc = fitz.open(pdf_path)
        if page_num < 0 or page_num >= len(doc):
            doc.close()
            return []
        
        page = doc[page_num]
        blocks = extract_pdf_text_blocks(page)
        doc.close()
        return blocks
    except Exception as e:
        print(f"Error extracting text blocks from page {page_num}: {e}")
        return []


def search_pdf_text_positions(book: Book, query: str,
                              page_num: int = None,
                              book_dir: str = None) -> List[dict]:
    """
    Search for text in PDF and return positions for highlighting.
    Returns list of matches with page number and bounding box coordinates.
    
    Note: This now extracts text blocks on-demand from the source PDF.
    """
    import fitz
    
    if not book.is_pdf:
        return []

    results = []
    query_lower = query.lower()
    query_words = query_lower.split()

    pages_to_search = (
        [page_num] if page_num is not None
        else range(book.pdf_total_pages)
    )
    
    # Open PDF once for all page searches
    pdf_path = None
    if book.pdf_source_path and book_dir:
        pdf_path = os.path.join(book_dir, book.pdf_source_path)
    
    if not pdf_path or not os.path.exists(pdf_path):
        # Fallback: search using stored plain text (less accurate positioning)
        return _search_pdf_text_fallback(book, query, pages_to_search)
    
    try:
        doc = fitz.open(pdf_path)
        
        for page_idx in pages_to_search:
            if page_idx < 0 or page_idx >= len(doc):
                continue

            page = doc[page_idx]
            text_blocks = extract_pdf_text_blocks(page)

            # Simple word-by-word matching
            for block in text_blocks:
                if query_lower in block.text.lower():
                    results.append({
                        "page": page_idx,
                        "text": block.text,
                        "rect": [block.x0, block.y0, block.x1, block.y1],
                        "match_type": "exact"
                    })
                elif any(w in block.text.lower() for w in query_words):
                    results.append({
                        "page": page_idx,
                        "text": block.text,
                        "rect": [block.x0, block.y0, block.x1, block.y1],
                        "match_type": "partial"
                    })
        
        doc.close()
    except Exception as e:
        print(f"Error searching PDF: {e}")

    return results


def _search_pdf_text_fallback(book: Book, query: str,
                               pages_to_search) -> List[dict]:
    """
    Fallback text search using stored plain text when source PDF unavailable.
    Returns matches without precise positioning.
    """
    results = []
    query_lower = query.lower()
    
    for page_idx in pages_to_search:
        if page_idx >= len(book.spine):
            continue
        
        page_text = book.spine[page_idx].text.lower()
        if query_lower in page_text:
            results.append({
                "page": page_idx,
                "text": query,
                "rect": [0, 0, 0, 0],  # No positioning available
                "match_type": "text_only"
            })
    
    return results


def get_pdf_page_stats(book: Book) -> dict:
    """
    Get statistics about the PDF pages.
    """
    if not book.is_pdf:
        return {}

    total_words = 0
    total_images = 0
    total_annotations = 0
    pages_with_images = 0
    pages_with_annotations = 0

    for page_data in book.pdf_page_data.values():
        total_words += page_data.word_count
        if page_data.has_images:
            pages_with_images += 1
            total_images += 1  # Simplified count
        if page_data.annotations:
            pages_with_annotations += 1
            total_annotations += len(page_data.annotations)

    # Estimate reading time (225 words per minute)
    reading_time_minutes = total_words / 225

    return {
        "total_pages": book.pdf_total_pages,
        "total_words": total_words,
        "total_images": total_images,
        "total_annotations": total_annotations,
        "pages_with_images": pages_with_images,
        "pages_with_annotations": pages_with_annotations,
        "has_native_toc": book.pdf_has_toc,
        "has_thumbnails": book.pdf_thumbnails_generated,
        "estimated_reading_time_minutes": round(reading_time_minutes, 1)
    }


def extract_cover_image(
    epub_book,
    images_dir: str,
    image_map: Dict[str, str]
) -> Optional[str]:
    """
    Extract cover image from EPUB.
    Returns relative path to cover image (e.g., 'images/cover.jpg') or None.
    """
    try:
        # Try to get cover using ebooklib's cover attribute
        cover_item = epub_book.get_cover()
        if cover_item:
            original_fname = os.path.basename(cover_item.get_name())
            # Sanitize filename for OS
            safe_fname = "".join(
                [c for c in original_fname
                 if c.isalpha() or c.isdigit() or c in '._-']
            ).strip()
            if not safe_fname:
                safe_fname = "cover.jpg"

            # Save to disk
            local_path = os.path.join(images_dir, safe_fname)
            with open(local_path, 'wb') as f:
                f.write(cover_item.get_content())

            cover_rel_path = f"images/{safe_fname}"
            print(f"Extracted cover image: {cover_rel_path}")
            return cover_rel_path
    except Exception as e:
        print(f"Could not extract cover using get_cover(): {e}")

    # Fallback: Check EPUB manifest/spine for common cover patterns
    try:
        for item in epub_book.get_items():
            if item.get_type() == ebooklib.ITEM_IMAGE:
                item_name_lower = item.get_name().lower()
                # Look for common cover file patterns
                if any(pattern in item_name_lower
                       for pattern in ['cover', 'front']):
                    original_fname = os.path.basename(item.get_name())
                    # Sanitize filename for OS
                    safe_fname = "".join(
                        [c for c in original_fname
                         if c.isalpha() or c.isdigit() or c in '._-']
                    ).strip()

                    # Save to disk
                    local_path = os.path.join(images_dir, safe_fname)
                    with open(local_path, 'wb') as f:
                        f.write(item.get_content())

                    cover_rel_path = f"images/{safe_fname}"
                    print(f"Found cover by pattern: {cover_rel_path}")
                    return cover_rel_path
    except Exception as e:
        print(f"Fallback cover extraction failed: {e}")

    # Final fallback: use the first image as cover
    try:
        for item in epub_book.get_items():
            if item.get_type() == ebooklib.ITEM_IMAGE:
                original_fname = os.path.basename(item.get_name())
                # Sanitize filename for OS
                safe_fname = "".join(
                    [c for c in original_fname
                     if c.isalpha() or c.isdigit() or c in '._-']
                ).strip()

                # Save to disk
                local_path = os.path.join(images_dir, safe_fname)
                with open(local_path, 'wb') as f:
                    f.write(item.get_content())

                cover_rel_path = f"images/{safe_fname}"
                print(f"Using first image as cover: {cover_rel_path}")
                return cover_rel_path
    except Exception as e:
        print(f"Could not use first image as cover: {e}")

    print("Warning: No cover image found")
    return None


def process_epub(epub_path: str, output_dir: str) -> Book:

    # 1. Load Book
    print(f"Loading {epub_path}...")
    book = epub.read_epub(epub_path)

    # 2. Extract Metadata
    metadata = extract_metadata_robust(book)

    # 3. Prepare Output Directories
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    images_dir = os.path.join(output_dir, 'images')
    os.makedirs(images_dir, exist_ok=True)

    # 4. Extract Images & Build Map
    print("Extracting images...")
    image_map = {}  # Key: internal_path, Value: local_relative_path

    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_IMAGE:
            # Normalize filename
            original_fname = os.path.basename(item.get_name())
            # Sanitize filename for OS
            safe_fname = "".join(
                [c for c in original_fname
                 if c.isalpha() or c.isdigit() or c in '._-']
            ).strip()

            # Save to disk
            local_path = os.path.join(images_dir, safe_fname)
            with open(local_path, 'wb') as f:
                f.write(item.get_content())

            # Map keys: We try both the full internal path
            # and just the basename to be robust against
            # messy HTML src attributes
            rel_path = f"images/{safe_fname}"
            image_map[item.get_name()] = rel_path
            image_map[original_fname] = rel_path

    # 4.5 Extract Cover Image
    print("Extracting cover image...")
    cover_image = extract_cover_image(book, images_dir, image_map)

    # 5. Process TOC
    print("Parsing Table of Contents...")
    toc_structure = parse_toc_recursive(book.toc)
    if not toc_structure:
        print("Warning: Empty TOC, building fallback from Spine...")
        toc_structure = get_fallback_toc(book)

    # 6. Process Content (Spine-based to preserve HTML validity)
    print("Processing chapters...")
    spine_chapters = []

    # We iterate over the spine (linear reading order)
    for i, spine_item in enumerate(book.spine):
        item_id, linear = spine_item
        item = book.get_item_with_id(item_id)

        if not item:
            continue

        if is_content_document(item):
            # Raw content
            raw_content = item.get_content().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(raw_content, 'html.parser')

            # A. Fix Images
            for img in soup.find_all('img'):
                src = img.get('src', '')
                if not src: continue

                # Decode URL (part01/image%201.jpg -> part01/image 1.jpg)
                src_decoded = unquote(src)
                filename = os.path.basename(src_decoded)

                # Try to find in map
                if src_decoded in image_map:
                    img['src'] = image_map[src_decoded]
                elif filename in image_map:
                    img['src'] = image_map[filename]

            # B. Clean HTML
            soup = clean_html_content(soup)

            # C. Extract Body Content only
            body = soup.find('body')
            if body:
                # Extract inner HTML of body
                final_html = "".join([str(x) for x in body.contents])
            else:
                final_html = str(soup)

            # D. Create Object
            chapter = ChapterContent(
                id=item_id,
                href=item.get_name(), # Important: This links TOC to Content
                title=f"Section {i+1}", # Fallback, real titles come from TOC
                content=final_html,
                text=extract_plain_text(soup),
                order=i
            )
            spine_chapters.append(chapter)

    # 7. Final Assembly
    final_book = Book(
        metadata=metadata,
        spine=spine_chapters,
        toc=toc_structure,
        images=image_map,
        source_file=os.path.basename(epub_path),
        processed_at=datetime.now().isoformat(),
        added_at=datetime.now().isoformat(),
        cover_image=cover_image
    )

    return final_book


def save_to_pickle(book: Book, output_dir: str):
    p_path = os.path.join(output_dir, 'book.pkl')
    with open(p_path, 'wb') as f:
        pickle.dump(book, f)
    print(f"Saved structured data to {p_path}")


# --- CLI ---

if __name__ == "__main__":

    import sys
    if len(sys.argv) < 2:
        print("Usage: python reader3.py <file.epub>")
        sys.exit(1)

    epub_file = sys.argv[1]
    assert os.path.exists(epub_file), "File not found."
    out_dir = os.path.splitext(epub_file)[0] + "_data"

    book_obj = process_epub(epub_file, out_dir)
    save_to_pickle(book_obj, out_dir)
    print("\n--- Summary ---")
    print(f"Title: {book_obj.metadata.title}")
    print(f"Authors: {', '.join(book_obj.metadata.authors)}")
    print(f"Physical Files (Spine): {len(book_obj.spine)}")
    print(f"TOC Root Items: {len(book_obj.toc)}")
    print(f"Images extracted: {len(book_obj.images)}")
