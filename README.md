# Reader3

A lightweight, self-hosted EPUB & PDF reader for reading books.

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
