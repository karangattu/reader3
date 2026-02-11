# Changelog

All notable changes to Reader3 will be documented in this file.

## [1.6.3] - 2026-02-11

### Added
- Containerization and production readiness: Dockerfile/.dockerignore plus updated render.yaml make releases easier to build, health-checked, and run with sensible defaults.
- ai_service now reuses an `httpx.AsyncClient` with timeouts so Gemini/Ollama calls keep connections pooled.

### Changed
- Server startup now prefers `uvloop`/`httptools`, runs uvicorn via a kwargs dict, and defaults to `ORJSONResponse` for faster serialization, making JSON APIs snappier.
- Background I/O handling grew stronger with structured logging, sani-tized book fields, upload streaming guards, gzip/security/cache middleware, and helper utilities for offloading blocking work, plus the new health endpoint and executor lifecycle hooks.
- PDF imports received thorough validation/sanitization, an atomic temp-dir build-and-swap, placeholder pages for recoverable issues, per-page error handling, richer status messaging, and expanded upload modal controls (cancel/retry/backoff and better error guidance).
- Copy/clipboard flows gained a helper that works in constrained environments, a new info toast style, rename of page copy UI, text-layer fallbacks, inline heading copy buttons, and consistent shortcut/help messaging.

### Technical
- Tests now use a `conftest.py` fixture that isolates book data and clears caches so automation never touches real user files, while `user_data.py` introduces debounced/atomic writes and exposed flush helpers for the new lifecycle hooks.
- The server now tracks active uploads, sanitizes filenames, and adds progress callbacks plus improved cleanup to keep partial uploads from leaking state.
- launcher.py, server.py, and user_data.py gained new helpers for running blocking tasks on a ThreadPoolExecutor, triggering durable saves, and using environment-configurable host/port/workers.

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
