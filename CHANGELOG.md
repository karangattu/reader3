# Changelog

All notable changes to Reader3 will be documented in this file.

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
