# Reader3

A lightweight, self-hosted EPUB & PDF reader for reading books.

## Features

- **EPUB & PDF Reader**: Clean reading interface with progress persistence and Table of Contents navigation.
- **Chapter & Section Copying**: Single-tap and batch chapter copying from EPUBs with markdown/heading formatting.
- **PDF Image Copying**: Copy single pages or multi-page composites to clipboard and native share sheet.
- **Library Shelf**: Automatic cover art extraction for EPUB and PDF documents.
- **Android App**: Standalone mobile release with offline library ([download `reader3.apk`](reader3.apk)).

## Local setup

Requirements:

- Python 3.12+
- `uv`

Install dependencies:

```bash
uv sync
```

Run locally:

```bash
uv run python launcher.py
```

The app opens in your browser. Upload a book to start reading.

## Tests

```bash
uv run python -m pytest -q
```

## Build

```bash
uv run python build_executable.py
```

## Notes

- Local app data is stored in the book directory.
- `launcher.py` is the simplest way to run the app in development.

## License

MIT
