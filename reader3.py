"""
Parses an EPUB file into a structured object that can be used to serve the book via a web interface.
"""

import os
import pickle
import shutil
import json
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


def sanitize_text(value: Optional[str]) -> Optional[str]:
    """Replace invalid UTF-16 surrogate code points with the replacement char."""
    if value is None or not isinstance(value, str):
        return value
    has_surrogates = False
    for ch in value:
        code = ord(ch)
        if 0xD800 <= code <= 0xDFFF:
            has_surrogates = True
            break
    if not has_surrogates:
        return value
    return ''.join(
        '\uFFFD' if 0xD800 <= ord(ch) <= 0xDFFF else ch
        for ch in value
    )


def sanitize_toc_entries(entries: List[TOCEntry]) -> None:
    """Sanitize TOC entry titles in-place to avoid invalid Unicode."""
    for entry in entries:
        entry.title = sanitize_text(entry.title) or entry.title
        entry.href = sanitize_text(entry.href) or entry.href
        entry.file_href = sanitize_text(entry.file_href) or entry.file_href
        entry.anchor = sanitize_text(entry.anchor) or entry.anchor
        if entry.children:
            sanitize_toc_entries(entry.children)


def sanitize_book_text_fields(book: 'Book') -> None:
    """Sanitize text fields in a Book to avoid invalid Unicode at render time."""
    if getattr(book, 'metadata', None):
        book.metadata.title = sanitize_text(book.metadata.title) or book.metadata.title
        book.metadata.language = sanitize_text(book.metadata.language) or book.metadata.language
        book.metadata.description = sanitize_text(book.metadata.description)
        book.metadata.publisher = sanitize_text(book.metadata.publisher)
        book.metadata.date = sanitize_text(book.metadata.date)
        book.metadata.authors = [sanitize_text(a) or a for a in book.metadata.authors]
        book.metadata.identifiers = [sanitize_text(i) or i for i in book.metadata.identifiers]
        book.metadata.subjects = [sanitize_text(s) or s for s in book.metadata.subjects]

    book.source_file = sanitize_text(getattr(book, 'source_file', None)) or getattr(book, 'source_file', None)
    book.cover_image = sanitize_text(getattr(book, 'cover_image', None)) or getattr(book, 'cover_image', None)

    if getattr(book, 'toc', None):
        sanitize_toc_entries(book.toc)

    if getattr(book, 'spine', None):
        for ch in book.spine:
            ch.id = sanitize_text(ch.id) or ch.id
            ch.href = sanitize_text(ch.href) or ch.href
            ch.title = sanitize_text(ch.title) or ch.title
            ch.content = sanitize_text(ch.content) or ch.content
            ch.text = sanitize_text(ch.text) or ch.text

    if getattr(book, 'images', None):
        sanitized_images = {}
        for k, v in book.images.items():
            sk = sanitize_text(k) or k
            sv = sanitize_text(v) or v
            sanitized_images[sk] = sv
        book.images = sanitized_images


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


def validate_pdf(pdf_path: str) -> dict:
    """
    Validate that a file is a readable PDF before starting heavy processing.
    Returns dict with 'valid' bool, 'error' str (if invalid), and 'info' dict.
    """
    import fitz  # PyMuPDF

    result = {"valid": False, "error": None, "info": {}}

    # Check magic bytes (%PDF-)
    try:
        with open(pdf_path, "rb") as f:
            header = f.read(8)
        if not header.startswith(b"%PDF"):
            result["error"] = "File is not a valid PDF (bad header magic bytes)."
            return result
    except OSError as e:
        result["error"] = f"Cannot read file: {e}"
        return result

    # Try opening with PyMuPDF
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        result["error"] = f"Cannot open PDF: {e}"
        return result

    try:
        if doc.needs_pass:
            doc.close()
            result["error"] = "PDF is password-protected. Please remove the password and re-upload."
            return result

        if doc.is_encrypted:
            doc.close()
            result["error"] = "PDF is encrypted. Please decrypt the file and re-upload."
            return result

        total_pages = len(doc)
        if total_pages == 0:
            doc.close()
            result["error"] = "PDF has no pages."
            return result

        # Quick sanity check: try to access the first page
        try:
            _ = doc[0].rect
        except Exception as e:
            doc.close()
            result["error"] = f"PDF appears corrupted (cannot read first page): {e}"
            return result

        result["valid"] = True
        result["info"] = {
            "pages": total_pages,
            "title": doc.metadata.get("title", ""),
            "author": doc.metadata.get("author", ""),
        }
        doc.close()
    except Exception as e:
        try:
            doc.close()
        except Exception:
            pass
        result["error"] = f"Error inspecting PDF: {e}"

    return result


def process_pdf(pdf_path: str, output_dir: str,
                generate_thumbnails: bool = True,
                progress_callback=None,
                source_filename: Optional[str] = None) -> Book:
    """
    Process a PDF file into a structured Book object.
    Renders each page as an image (like a traditional PDF reader)
    while extracting text separately for search and copy functionality.

    Args:
        pdf_path: Path to source PDF.
        output_dir: Final destination directory for the processed book.
        generate_thumbnails: Whether to render page thumbnails.
        progress_callback: Optional ``fn(percent, message)`` called during processing.
    """
    import fitz  # PyMuPDF

    def _progress(pct: int, msg: str):
        if progress_callback:
            try:
                progress_callback(pct, msg)
            except Exception:
                pass

    # --- 1. Validate -----------------------------------------------------------
    _progress(5, "Validating PDF…")
    validation = validate_pdf(pdf_path)
    if not validation["valid"]:
        raise ValueError(validation["error"])

    # --- 2. Open ---------------------------------------------------------------
    _progress(8, "Opening PDF…")
    print(f"Loading {pdf_path}...")
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        raise ValueError(f"Failed to open PDF: {e}")

    total_pages = len(doc)

    # Extract Metadata (defensively)
    raw_meta = doc.metadata or {}
    display_name = source_filename or os.path.basename(pdf_path)
    display_title = os.path.splitext(display_name)[0] or display_name
    metadata = BookMetadata(
        title=raw_meta.get('title') or display_title,
        language=raw_meta.get('language') or "en",
        authors=(
            [raw_meta.get('author')]
            if raw_meta.get('author') else []
        ),
        publisher=raw_meta.get('producer'),
        date=raw_meta.get('creationDate'),
        subjects=(
            [raw_meta.get('subject')]
            if raw_meta.get('subject') else []
        )
    )

    # --- 3. Build into a *temp* directory, then swap atomically ----------------
    # This prevents destroying an existing good copy if processing fails.
    import tempfile
    parent_dir = os.path.dirname(os.path.abspath(output_dir))
    os.makedirs(parent_dir, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix=".reader3_pdf_", dir=parent_dir)

    try:
        images_dir = os.path.join(tmp_dir, 'images')
        thumbs_dir = os.path.join(tmp_dir, 'thumbnails')
        os.makedirs(images_dir, exist_ok=True)
        if generate_thumbnails:
            os.makedirs(thumbs_dir, exist_ok=True)

        # Copy original PDF to _data folder for on-demand text extraction
        pdf_copy_name = 'source.pdf'
        pdf_copy_path = os.path.join(tmp_dir, pdf_copy_name)
        shutil.copy2(pdf_path, pdf_copy_path)

        spine_chapters = []
        image_map = {}
        pdf_page_data = {}
        failed_pages = []

        # Extract native outline/TOC
        _progress(12, "Extracting PDF outline…")
        print("Extracting PDF outline...")
        try:
            toc_structure = extract_pdf_outline(doc)
        except Exception as e:
            print(f"Warning: Failed to extract TOC: {e}")
            toc_structure = []
        has_native_toc = len(toc_structure) > 0

        if not toc_structure:
            print("No native TOC found, will create page-based navigation.")

        _progress(15, f"Processing {total_pages} pages…")
        print(f"Processing {total_pages} PDF pages...")

        for i in range(total_pages):
            # Real progress: 15 ‥ 90 proportional to page count
            page_pct = 15 + int(75 * (i / max(total_pages, 1)))
            _progress(page_pct, f"Processing page {i+1}/{total_pages}…")

            try:
                page = doc[i]
            except Exception as e:
                print(f"Warning: Could not load page {i+1}: {e}")
                failed_pages.append(i)
                # Insert placeholder so page numbering stays consistent
                _insert_placeholder_page(
                    i, spine_chapters, image_map, pdf_page_data,
                    toc_structure, has_native_toc, error_msg=str(e)
                )
                continue

            try:
                rect = page.rect
                height = rect.height
                width = rect.width

                # Extract plain text for search/copy (full page, no clipping)
                try:
                    page_text = page.get_text("text")
                except Exception as e:
                    print(f"Warning: Text extraction failed for page {i+1}: {e}")
                    page_text = ""

                # Render page as image for display
                try:
                    page_image_path = generate_pdf_page_image(page, i, images_dir)
                except Exception as e:
                    print(f"Warning: Image render failed for page {i+1}: {e}")
                    failed_pages.append(i)
                    _insert_placeholder_page(
                        i, spine_chapters, image_map, pdf_page_data,
                        toc_structure, has_native_toc,
                        error_msg=f"Render failed: {e}"
                    )
                    continue

                image_map[f"page_{i+1}"] = page_image_path

                # Extract annotations (non-critical; skip on error)
                try:
                    annotations = extract_pdf_annotations(page)
                except Exception as e:
                    print(f"Warning: Annotation extraction failed for page {i+1}: {e}")
                    annotations = []

                # Generate thumbnail if requested (non-critical)
                if generate_thumbnails:
                    try:
                        generate_pdf_thumbnail(page, i, thumbs_dir)
                    except Exception as e:
                        print(f"Warning: Thumbnail generation failed for page {i+1}: {e}")

                # Store page-specific data
                pdf_page_data[i] = PDFPageData(
                    page_num=i,
                    width=width,
                    height=height,
                    rotation=page.rotation,
                    annotations=annotations,
                    has_images=True,
                    word_count=len(page_text.split()) if page_text else 0
                )

                # Create chapter content
                chapter_id = f"page_{i+1}"
                chapter_title = f"Page {i+1}"

                content_html = f'''<div class="pdf-page-image-container">
<img src="{page_image_path}" alt="Page {i+1}" class="pdf-page-image" />
</div>'''

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
                    text=page_text,
                    order=i
                )
                spine_chapters.append(chapter)

            except Exception as e:
                print(f"Warning: Unexpected error processing page {i+1}: {e}")
                failed_pages.append(i)
                _insert_placeholder_page(
                    i, spine_chapters, image_map, pdf_page_data,
                    toc_structure, has_native_toc, error_msg=str(e)
                )

        doc.close()

        # If *every* page failed, that's still an error
        if len(failed_pages) == total_pages:
            raise ValueError(
                f"All {total_pages} pages failed to process. "
                "The PDF may be severely corrupted."
            )

        if failed_pages:
            print(f"Warning: {len(failed_pages)} of {total_pages} page(s) had errors "
                  f"and were replaced with placeholders: {failed_pages}")

        _progress(92, "Saving book data…")

        final_book = Book(
            metadata=metadata,
            spine=spine_chapters,
            toc=toc_structure,
            images=image_map,
            source_file=display_name,
            processed_at=datetime.now().isoformat(),
            added_at=datetime.now().isoformat(),
            is_pdf=True,
            pdf_page_data=pdf_page_data,
            pdf_total_pages=total_pages,
            pdf_has_toc=has_native_toc,
            pdf_thumbnails_generated=generate_thumbnails,
            pdf_source_path=pdf_copy_name
        )

        sanitize_book_text_fields(final_book)

        # --- 4. Atomic swap: tmp_dir -> output_dir ----------------------------
        _progress(95, "Finalising…")
        if os.path.exists(output_dir):
            backup_dir = output_dir + ".__old"
            # Remove stale backup if present
            if os.path.exists(backup_dir):
                shutil.rmtree(backup_dir, ignore_errors=True)
            os.rename(output_dir, backup_dir)
            try:
                os.rename(tmp_dir, output_dir)
            except Exception:
                # Restore the old directory on rename failure
                os.rename(backup_dir, output_dir)
                raise
            shutil.rmtree(backup_dir, ignore_errors=True)
        else:
            os.rename(tmp_dir, output_dir)

        tmp_dir = None  # Prevent cleanup in finally
        _progress(100, "Done!")
        return final_book

    finally:
        # Clean up temp dir on any failure
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
        try:
            doc.close()
        except Exception:
            pass


def _insert_placeholder_page(
    page_idx: int,
    spine_chapters: list,
    image_map: dict,
    pdf_page_data: dict,
    toc_structure: list,
    has_native_toc: bool,
    error_msg: str = "Page could not be rendered",
):
    """Insert a placeholder entry for a page that failed to process."""
    chapter_id = f"page_{page_idx + 1}"
    chapter_title = f"Page {page_idx + 1}"
    content_html = (
        f'<div class="pdf-page-image-container" style="padding:40px; text-align:center; '
        f'color:#999; background:#f9f9f9; border:1px dashed #ccc; border-radius:8px;">'
        f'<p style="font-size:1.2em;">⚠ Page {page_idx + 1} could not be rendered</p>'
        f'<p style="font-size:0.85em;">{error_msg}</p></div>'
    )
    if not has_native_toc:
        toc_structure.append(TOCEntry(
            title=chapter_title, href=chapter_id,
            file_href=chapter_id, anchor=""
        ))
    pdf_page_data[page_idx] = PDFPageData(
        page_num=page_idx, width=0, height=0, rotation=0,
        has_images=False, word_count=0
    )
    spine_chapters.append(ChapterContent(
        id=chapter_id, href=chapter_id, title=chapter_title,
        content=content_html, text="", order=page_idx
    ))


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
        import fitz
    except Exception as e:
        print(f"Error importing fitz for PDF search: {e}")
        return _search_pdf_text_fallback(book, query, pages_to_search)

    try:
        with fitz.open(pdf_path) as doc:
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

    # 3. Build into a temp dir, then swap atomically
    import tempfile

    parent_dir = os.path.dirname(os.path.abspath(output_dir))
    os.makedirs(parent_dir, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix=".reader3_epub_", dir=parent_dir)

    try:
        images_dir = os.path.join(tmp_dir, 'images')
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
                    if not src:
                        continue

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

        sanitize_book_text_fields(final_book)

        # 8. Atomic swap: tmp_dir -> output_dir
        if os.path.exists(output_dir):
            backup_dir = output_dir + ".__old"
            if os.path.exists(backup_dir):
                shutil.rmtree(backup_dir, ignore_errors=True)
            os.rename(output_dir, backup_dir)
            try:
                os.rename(tmp_dir, output_dir)
            except Exception:
                os.rename(backup_dir, output_dir)
                raise
            shutil.rmtree(backup_dir, ignore_errors=True)
        else:
            os.rename(tmp_dir, output_dir)

        tmp_dir = None
        return final_book
    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


def save_to_pickle(book: Book, output_dir: str):
    p_path = os.path.join(output_dir, 'book.pkl')
    with open(p_path, 'wb') as f:
        pickle.dump(book, f)
    print(f"Saved structured data to {p_path}")

    meta_path = os.path.join(output_dir, 'book_meta.json')
    metadata = {
        "title": book.metadata.title,
        "authors": book.metadata.authors,
        "chapters": len(book.spine),
        "added_at": book.added_at or book.processed_at,
        "processed_at": book.processed_at,
        "cover_image": book.cover_image,
        "is_pdf": book.is_pdf,
        "language": book.metadata.language,
        "source_file": book.source_file,
    }
    try:
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False)
        print(f"Saved metadata to {meta_path}")
    except Exception as e:
        print(f"Error saving metadata to {meta_path}: {e}")


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
