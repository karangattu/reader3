# Changelog

All notable changes to Reader3 will be documented in this file.

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
