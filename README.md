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

## Copilot Summaries

Reader3 can now summarize:

- the current chapter
- selected text
- PDF page images
- inline EPUB images

The reader keeps working if Copilot is unavailable. You can also turn Copilot assistance off or on from Reader Settings; when it is off, Reader3 skips Copilot status checks and hides summary controls.

Setup notes:

- Run `uv sync` so the Python Copilot SDK is installed.
- The default Copilot model is `gpt-4.1`. Override it with `READER3_COPILOT_MODEL` if you want a different model.
- Image summaries require a vision-capable model.
- The current integration is single-user, local, and non-streaming.

## Keyboard Shortcuts

| Shortcut | Action |
| -------- | ------ |
| `Ctrl/⌘+F` | Search |
| `Ctrl/⌘+B` | Bookmarks panel |
| `Escape` | Close modals |

## Building Executable

```bash
uv run python build_executable.py
```

Creates:

- macOS: `dist/Reader3.app`
- macOS installer: `dist/Reader3-macOS.dmg` (drag `Reader3.app` into `Applications`)
- Windows (default): `dist/Reader3/Reader3.exe` and `dist/Reader3-windows-portable.zip`

Windows notes:

- Keep the entire `Reader3` folder together (do not move only the `.exe`).
- For debugging startup issues on Windows, build with console logs:

```bash
uv run python build_executable.py --console
```

## CI Releases (on tags)

Pushing a version tag triggers GitHub Actions to build and publish platform artifacts automatically.

```bash
git tag v1.7.0 && git push origin v1.7.0
```

Release assets include:

- `Reader3-windows-portable.zip`
- `Reader3.exe`
- `Reader3-macOS.zip`
- `Reader3-macOS.dmg`
- SHA256 checksum files for each artifact

## License

MIT
