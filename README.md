# reader 3

![reader3](reader3.png)

A lightweight, self-hosted EPUB reader that lets you read through EPUB books one chapter at a time. This makes it very easy to copy paste the contents of a chapter to an LLM, to read along. Basically - get epub books (e.g. [Project Gutenberg](https://www.gutenberg.org/) has many), open them up in this reader, copy paste text around to your favorite LLM, and read together and along.

This project was 90% vibe coded just to illustrate how one can very easily [read books together with LLMs](https://x.com/karpathy/status/1990577951671509438). I'm not going to support it in any way, it's provided here as is for other people's inspiration and I don't intend to improve it. Code is ephemeral now and libraries are over, ask your LLM to change it in whatever way you like.

## Usage

## Usage

1. **Run the App**:
   - If you built the executable, just double-click `Reader3` (or `Reader3.app`).
   - Or run from source: `uv run python launcher.py`

2. **Add Books**:
   - The browser will open automatically.
   - Click "Upload EPUB" to select a book from your computer.
   - The book will be processed and added to your library.

3. **Read**:
   - Click "Read Book" to start reading.
   - Copy-paste text to your LLM as needed.

## License

MIT

## Building Executable

To build a standalone executable for your platform (Windows or macOS):

1. Ensure dependencies are installed:
   ```bash
   uv sync
   ```

2. Run the build script:
   ```bash
   uv run python build_executable.py
   ```

The executable will be created in the `dist` directory.
- On macOS, it will be `dist/Reader3.app`
- On Windows, it will be `dist/Reader3.exe`