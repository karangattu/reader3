# Changelog

All notable changes to Reader3 will be documented in this file.

## [1.8.1] - 2026-03-30

### Changed

- **PDF toolbar decluttered** — Reorganized the PDF reader toolbar into a clean primary row (Reader Settings, Go to Page, Select Pages) with a collapsible selection strip that expands on demand. Selection tools (Select Range, Select All, Copy Selected, Clear) now live in a secondary row that auto-expands when pages are selected and collapses when cleared. A count badge on the "Select Pages" toggle shows how many pages are currently selected.

### Technical

- Added 3 new toolbar layout tests (`test_copy_badges.py`).
- Tests: `pytest -q` (634 passed).

---

## [1.8.0] - 2026-03-30

### Added

- **Copy badges for PDF and EPUB** — Green checkmark badges now appear on individual PDF pages and EPUB TOC chapters after they have been copied (image, text, or multi-select), giving users clear visual feedback of what has already been copied.
- **Robust multi-page PDF copy** — Per-page error handling with skip-and-continue so a single broken image no longer aborts the entire batch; 15-second timeout on each image load; progress feedback in the copy button ("Loading 3/10…", "Compositing…"); canvas size guard that falls back to individual image downloads when the combined image would exceed browser limits.
- **PDF image download fallback** — Single-page "Copy Image" now falls back to a file download when clipboard image copy is unavailable, instead of silently failing.

### Technical

- New test suite `test_copy_badges.py` (37 tests) covering badge rendering, multi-page robustness logic, EPUB multi-chapter copy API, canvas size guards, and progress tracking.
- Tests: `pytest -q` (631 passed).

---

## [1.7.0] - 2026-03-29

### Added

- **Reader preferences and organization controls** — Added per-book font overrides, persistent reader appearance preferences, richer library sorting/filtering, and improved upload/library UI flows.
- **PDF reading improvements** — Added visible-page detection fixes, page-read tracking during view/copy flows, and a refactored PDF page rendering path with multi-copy improvements.

### Changed

- **Framework dependencies** — Upgraded FastAPI to `0.135.2` and Starlette to `1.0.0`, refreshed the lockfile and pinned requirements, and updated template rendering calls for the current Starlette API.
- **Packaging metadata** — `build_executable.py` now reads the app version from `pyproject.toml` so macOS bundle metadata stays aligned with releases.
- **Project packaging** — Added explicit setuptools build metadata and py-modules configuration for cleaner installs and builds.

### Fixed

- **CI compatibility** — Fixed template rendering under newer Starlette/Jinja combinations that raised `TypeError: unhashable type: 'dict'` in tests and CI.
- **Selection and toolbar polish** — Cleaned up selection toolbar layout and improved PDF copy/selection related behavior.

### Technical

- Tests: `pytest -q` (593 passed).

---

## [1.6.5] - 2026-02-20

### Fixed

- **PDF Select Range from mid-chapter** — Checking a page checkbox then clicking Select Range now correctly anchors the range at that page instead of silently discarding the selection.
- **Viewport page detection** — The heuristic that picks "the page you're looking at" now finds the page whose center is truly closest to the viewport midpoint, instead of the last page within a loose threshold (which overshot by 2-3 pages on tall PDF pages).

### Changed

- **CI release workflows** — Split build matrix for macOS/Windows, added SHA-256 checksum files for release assets.
- **Windows packaging** — PyInstaller build now produces a portable folder zip alongside the single-file exe; added `--console` flag for debugging startup issues.

---

## [1.6.4] - 2026-02-18

### Fixed
- Guarded `search_pdf_text_positions` against loading `pymupdf` when there is no actual PDF source or when the import fails, and cleaned up document handling with a context manager plus the existing plain-text fallback so running the search suite no longer risks a segmentation fault during CI.

### Technical
- Tests: `python -m pytest` (407 passed, starlette `TemplateResponse` deprecation warnings still active).

## [1.6.2] - 2026-02-06

### Fixed
- **PDF Upload Auto-Refresh** — Fixed issue where PDFs wouldn't appear in the reading list after upload without manual page refresh. The frontend now polls the server for background processing completion before redirecting.

### Technical
- Modified upload completion handler in `library.html` to distinguish between synchronous (EPUB) and asynchronous (PDF) processing
- Added `pollUploadStatus()` function that polls `/api/upload/status/{upload_id}` until processing completes
- Shows real-time progress updates during PDF processing with status messages

---

## [1.6.0] - 2026-01-31

### Added - Performance & Usability Improvements 🚀

#### Cached Reading Time Computation
- **LRU-Cached Reading Times** — Reading time estimates are now cached per book, eliminating redundant computation on every request
- **Unified Endpoint** — Removed duplicate `/api/reading-times` endpoint that had conflicting response formats
- **Automatic Cache Invalidation** — Cache clears on book delete, reprocess, or upload

#### Lightweight Metadata Indexing
- **Fast Library Loading** — Library view now uses lightweight `book_meta.json` files instead of loading full pickle files
- **Metadata Cache** — In-memory LRU cache for book metadata reduces disk I/O
- **Automatic Metadata Generation** — Metadata files are auto-generated on book processing and on-demand for existing books
- **Metadata Rebuild Endpoint** — New endpoint to rebuild metadata for all books: `POST /api/metadata/rebuild?force=true`

#### Background PDF Processing
- **Async Upload Processing** — Large PDFs can now be processed in the background with `POST /upload?background=true`
- **Upload Status Tracking** — Poll processing status via `GET /api/upload/status/{upload_id}`
- **Progress Updates** — Status includes progress percentage and stage messages
- **Status Listing** — View all recent upload jobs via `GET /api/upload/status`
- **Automatic Cleanup** — Completed job statuses are cleaned up after 1 hour

#### Consolidated Progress Saving
- **Single Request Progress** — The `/api/progress/{book_id}` endpoint now also saves chapter progress when `progress_percent` is provided
- **Reduced Network Calls** — Frontend no longer needs separate calls to save chapter and overall progress
- **Bandwidth Savings** — Removed unused `text` field from PDF infinite-scroll page payloads

### New API Endpoints
- `POST /api/metadata/rebuild` — Rebuild lightweight metadata files for all books (optional `?force=true`)
- `GET /api/upload/status/{upload_id}` — Get status of background upload processing
- `GET /api/upload/status` — List all recent upload processing jobs

### Changed
- `POST /upload` now accepts `?background=true` parameter for async processing
- `POST /api/progress/{book_id}` now accepts `progress_percent` to update chapter progress in one call
- Removed duplicate `/api/reading-times/{book_id}` endpoint (index-keyed) in favor of href-keyed version
- PDF page payloads no longer include unused `text` field

### Technical
- Added `get_cached_reading_times()` with `@lru_cache(maxsize=200)`
- Added `load_book_metadata()` with `@lru_cache(maxsize=200)`
- Added `write_book_metadata()` helper for consistent metadata writing
- Added thread-safe upload status tracking with `threading.Lock()`
- Book processing now writes `book_meta.json` alongside `book.pkl`
- All caches properly invalidated on book mutations (delete, reprocess, upload)

### Tests
- Added 14 new tests for metadata rebuild, background uploads, consolidated progress, and caching
- Total: 404 tests passing

---

## [1.5.0] - 2025-06-01

### Added - Enhanced EPUB Reading Experience 📚

#### Dictionary & Definitions
- **Double-click Word Lookup** — Double-click any word in EPUB content to instantly get its definition
- **Free Dictionary API Integration** — Fetches definitions, pronunciation, part of speech, and examples
- **Contextual Definitions** — Shows the sentence context where you looked up the word
- **Save to Vocabulary** — One-click save words to your personal vocabulary list

#### Personal Vocabulary List
- **Word Collection** — Build a vocabulary list from words you look up while reading
- **Book Context** — Each saved word includes the book and context where you found it
- **Search Vocabulary** — Full-text search across all saved words and definitions
- **Learning Progress** — Track mastery level for each word (1-5 scale)
- **Export Ready** — Vocabulary integrates with the enhanced export system

#### Enhanced Annotations System
- **Rich Note-Taking** — Add detailed notes and annotations to any text selection
- **Annotation Types** — Support for notes, highlights, bookmarks, and questions
- **Tag System** — Organize annotations with custom tags for easy retrieval
- **Search Annotations** — Full-text search across all your annotations and notes
- **Export to Markdown** — Export all annotations to beautifully formatted Markdown
- **Chapter-based Organization** — View and filter annotations by chapter

#### Reading Session History
- **Session Tracking** — Automatically tracks when and how long you read each book
- **Reading Statistics** — Total reading time, sessions count, average session length
- **Per-book Stats** — See reading patterns for individual books
- **Recent Activity** — View your recent reading sessions with dates and duration

### New API Endpoints
- `POST /api/sessions/start` — Start a new reading session
- `PUT /api/sessions/{session_id}/end` — End a reading session
- `GET /api/sessions` — Get reading session history (filterable by book)
- `GET /api/reading-stats` — Get comprehensive reading statistics
- `GET /api/dictionary/{word}` — Look up word definition
- `GET /api/vocabulary` — Get vocabulary words (filterable by book)
- `POST /api/vocabulary` — Add word to vocabulary
- `DELETE /api/vocabulary/{word_id}` — Delete vocabulary word
- `PUT /api/vocabulary/{word_id}/mastery` — Update word mastery level
- `GET /api/vocabulary/search` — Search vocabulary
- `GET /api/annotations/{book_id}` — Get annotations for a book
- `POST /api/annotations/{book_id}` — Add annotation
- `PUT /api/annotations/{book_id}/{annotation_id}` — Update annotation
- `DELETE /api/annotations/{book_id}/{annotation_id}` — Delete annotation
- `GET /api/annotations/{book_id}/search` — Search annotations
- `GET /api/export/{book_id}/annotations` — Export annotations to Markdown/JSON

### New Data Structures
- `ReadingSession` — Tracks session ID, book info, chapter, start/end times, duration
- `VocabularyWord` — Stores word, definition, example, context, mastery level, review count
- `Annotation` — Stores text, notes, type, position, tags, timestamps

### Frontend Enhancements
- **Dictionary Popup** — Beautiful floating popup with word definitions
- **Vocabulary Panel** — Sidebar panel to browse and search saved words
- **Annotations Panel** — Full-featured panel for viewing/searching annotations
- **Session History Panel** — View reading history and statistics
- **New Sidebar Buttons** — Quick access to Dictionary 📖, Notes 📝, and Stats 📊

### Tests
- Added 28 new tests for reading sessions, vocabulary, and annotations
- Total: 195 tests passing

---

## [1.4.0] - 2025-11-30

### Added - Premium PDF Features 📄

#### Traditional PDF Viewing Experience
- **Page-as-Image Rendering** — PDFs now render each page as a high-quality image, exactly like traditional PDF readers (no more jumbled text!)
- **Copy Page Text Button** — Each PDF page has a "Copy Page Text" button to copy the full extracted text
- **Preserves Visual Layout** — Images, diagrams, and formatting appear exactly as in the original PDF

#### PDF Outline/TOC Extraction
- **Native PDF Bookmarks** — Automatically extract and display the PDF's built-in table of contents/bookmarks for hierarchical navigation
- **Intelligent Fallback** — Falls back to page-based navigation when no native outline exists

#### PDF Page Thumbnails
- **Quick Visual Navigation** — Generate thumbnail previews for all PDF pages
- **Thumbnail API** — New endpoint to list and serve page thumbnails

#### PDF Annotations Support
- **Read Native Annotations** — Extract highlights, underlines, strikeouts, notes, and other annotations from PDFs
- **Annotation Details** — Includes color, author, creation date, and bounding box coordinates
- **Filter by Page** — API supports filtering annotations by specific page

#### PDF Text Layer
- **Word-level Positioning** — Extract text with precise bounding box coordinates for each word
- **Accurate Search** — Full-text search still works on all PDF content
- **Text Block API** — New endpoint to get positioned text data for any page

#### PDF Page Export
- **Export Page Ranges** — Export selected pages from a PDF to a new PDF file
- **Flexible Range Selection** — Choose start and end pages for extraction

#### PDF Statistics
- **Comprehensive Stats** — Total pages, word count, image count, annotation count
- **Reading Time Estimate** — Automatically calculate estimated reading time
- **Content Overview** — Quick stats on pages with images, annotations, etc.

#### PDF Search with Positions
- **Position-aware Search** — Search returns bounding box coordinates for each match
- **Visual Highlighting** — Enable frontend to highlight exact positions of matches
- **Page-filtered Search** — Option to search within specific pages only

### New API Endpoints
- `GET /api/pdf/{book_id}/stats` — Get comprehensive PDF statistics
- `GET /api/pdf/{book_id}/thumbnails` — List all page thumbnails
- `GET /read/{book_id}/thumbnails/{thumb_name}` — Serve thumbnail images
- `GET /api/pdf/{book_id}/annotations` — Get PDF annotations (with optional page filter)
- `GET /api/pdf/{book_id}/search-positions` — Search with position data
- `GET /api/pdf/{book_id}/page/{page_num}` — Get detailed page information
- `GET /api/pdf/{book_id}/outline` — Get hierarchical TOC/outline
- `POST /api/pdf/{book_id}/export` — Export page range to new PDF
- `GET /api/pdf/{book_id}/text-layer/{page_num}` — Get positioned text blocks

### Fixed
- **PDF Text Rendering** — Fixed jumbled/overlapping text issue by rendering pages as images instead of extracting HTML

### New Data Structures
- `PDFAnnotation` — Stores annotation type, content, position, color, author, date
- `PDFTextBlock` — Stores word text with precise x0, y0, x1, y1 coordinates
- `PDFPageData` — Stores page dimensions, rotation, text blocks, annotations, image/word counts

### Technical
- Enhanced `Book` dataclass with PDF-specific fields (`pdf_page_data`, `pdf_total_pages`, `pdf_has_toc`, `pdf_thumbnails_generated`)
- New functions: `extract_pdf_outline()`, `extract_pdf_annotations()`, `extract_pdf_text_blocks()`, `generate_pdf_page_image()`, `generate_pdf_thumbnail()`, `export_pdf_pages()`, `search_pdf_text_positions()`, `get_pdf_page_stats()`

### Tests
- Added 20 new tests for PDF data structures and functions
- Added 28 new tests for PDF API endpoints
- Total: 167 tests passing

## [1.3.0] - 2025-01-17

### Added
- **Keyboard Navigation** — Navigate chapters with ← → arrow keys, toggle sidebar with S, space to scroll down, and more
- **Keyboard Help Tooltip** — Press ? to see all available keyboard shortcuts
- **Chapter Progress Indicators** — Visual progress bars for each chapter in the sidebar TOC
- **Estimated Reading Time** — Display reading time estimates for each chapter (assumes 200 WPM)
- **Empty State Illustrations** — Friendly SVG illustrations for empty bookmarks, highlights, search results, and library
- **Chapter Progress API** — New endpoints for tracking per-chapter reading progress
- **17 New Tests** — Comprehensive test coverage for chapter progress and reading time features

### Fixed
- **Real-time Progress Tracking** — Fixed progress not updating while scrolling (scroll events now properly target #main element)
- **Library Progress Display** — Fixed book progress always showing 0% in library view by calculating from chapter progress

### Technical
- Added `/api/chapter-progress/{book_id}` GET endpoint
- Added `/api/chapter-progress/{book_id}/{chapter_index}` POST endpoint
- Added `/api/reading-times/{book_id}` GET endpoint
- Modified `/api/progress/{book_id}` to return calculated `progress_percent`
- Added `chapter_progress` field to user data with `get_chapter_progress()` and `save_chapter_progress()` methods

## [1.2.0] - 2025-11-28

### Added
- **Highlight Context Menu** — Click on any highlight to access a rich context menu with options to change color, copy text, or delete
- **Change Highlight Color** — Easily change the color of existing highlights without deleting and recreating them
- **Copy Highlight Text** — One-click copy of highlighted text from the context menu
- **Comprehensive Test Coverage** — Added 26 new tests for highlights and export functionality

### Fixed
- **Highlight Color Picker** — Fixed issue where highlight color buttons showed black instead of their actual colors in the selection toolbar
- **Export Functionality** — Fixed JSON and Markdown export returning undefined/errors for highlights

### Improved
- **Delete Highlights UX** — Replaced basic confirm dialog with a polished context menu for better user experience
- **Export Tests** — Added thorough tests for JSON/Markdown export with highlights, bookmarks, color emojis, content types, and edge cases

## [1.1.0] - 2025-11-28

### Added
- **Bookmarks & Highlights** — Save passages with notes, highlight text in 5 colors (yellow, green, blue, pink, purple)
- **Full-text Search** — Search across all books or within a single book (Ctrl/⌘+F)
- **Reading Progress** — Auto-saves scroll position, resume where you left off
- **Export Notes** — Export bookmarks and highlights to JSON or Markdown
- **Global Library Search** — Search across all books from the library view
- **Search History** — Quick access to recent searches
- **Keyboard Shortcuts** — Ctrl/⌘+F (search), Ctrl/⌘+B (bookmarks panel), Escape (close modals)

### Improved
- **Search Performance** — Increased cache size, optimized search algorithm with early-exit for non-matching chapters
- **PDF Reading** — Progress bar, floating page indicator, "Go to Page" feature
- **UI Polish** — Fixed sidebar toggle and "Back to Library" link overlap

### Fixed
- Search API parameter mismatch (`query` → `q`)
- Removed unused imports across all Python files

## [1.0.0] - 2025-11-27

### Added
- Initial release
- EPUB and PDF support with infinite scroll
- Chapter navigation sidebar
- Text selection and batch copy for LLM conversations
- macOS and Windows standalone executables via GitHub Actions
