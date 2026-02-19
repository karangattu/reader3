# Reader3

A lightweight, self-hosted EPUB & PDF reader for reading books alongside LLMs.

![reader3](reader3.png)

## Quick Start

```bash
# Install dependencies
uv sync

# Run the app
uv run python launcher.py
```

The browser opens automatically. Upload a book and start reading!

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl/⌘+F` | Search |
| `Ctrl/⌘+B` | Bookmarks panel |
| `Escape` | Close modals |

## Building Executable

```bash
uv run python build_executable.py
```

Creates:
- macOS: `dist/Reader3.app`
- Windows (default): `dist/Reader3/Reader3.exe` and `dist/Reader3-windows-portable.zip`

Windows notes:
- Keep the entire `Reader3` folder together (do not move only the `.exe`).
- For debugging startup issues on Windows, build with console logs:

```bash
uv run python build_executable.py --console
```

## License

MIT
