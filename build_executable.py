import argparse
import os
import platform
import plistlib
import shutil
import subprocess
import sys


def build(onefile: bool = False, console: bool = False):
    system = platform.system()
    sep = ';' if system == 'Windows' else ':'

    # Hidden imports that PyInstaller may miss
    hidden_imports = [
        'fastapi',
        'fastapi.responses',
        'fastapi.staticfiles',
        'fastapi.templating',
        'python_multipart',
        'starlette',
        'starlette.routing',
        'starlette.responses',
        'starlette.requests',
        'starlette.middleware',
        'starlette.middleware.cors',
        'starlette.staticfiles',
        'starlette.templating',
        'jinja2',
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        'orjson',
        'fitz',
        'pymupdf',
        'ebooklib',
        'bs4',
    ]

    # Packages to collect all files from
    collect_all = [
        'fastapi',
        'starlette',
        'uvicorn',
        'pymupdf',
    ]

    mode_flag = '--onefile' if onefile else '--onedir'
    templates_src = os.path.join(os.getcwd(), "templates")

    # Define the command
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--specpath",
        "build",
        mode_flag,
        "--console" if console else "--windowed",
        f"--add-data={templates_src}{sep}templates",
        "--name=Reader3",
    ]

    # Avoid UPX-compression-related startup issues on Windows.
    if system == 'Windows':
        cmd.append("--noupx")

    # Add hidden imports
    for imp in hidden_imports:
        cmd.append(f"--hidden-import={imp}")

    # Add collect-all for packages
    for pkg in collect_all:
        cmd.append(f"--collect-all={pkg}")

    cmd.append("launcher.py")

    print(f"Building for {system}...")
    print("Command:", " ".join(cmd))

    # Run PyInstaller
    subprocess.check_call(cmd)

    # Post-processing for macOS: Fix Info.plist for proper app behavior
    if system == 'Darwin':
        print("\nConfiguring macOS app bundle...")
        plist_path = os.path.join(
            os.getcwd(), "dist", "Reader3.app", "Contents", "Info.plist"
        )

        if os.path.exists(plist_path):
            with open(plist_path, 'rb') as f:
                plist = plistlib.load(f)

            # LSUIElement makes the app a "background" app
            # (no dock icon, no menu bar)
            # This is appropriate for a server that just opens a browser
            plist['LSUIElement'] = True

            # Add a proper bundle identifier
            plist['CFBundleIdentifier'] = 'com.reader3.app'

            # Set version
            plist['CFBundleShortVersionString'] = '1.0.0'
            plist['CFBundleVersion'] = '1'

            # Allow the app to access network
            plist['NSAppTransportSecurity'] = {'NSAllowsArbitraryLoads': True}

            with open(plist_path, 'wb') as f:
                plistlib.dump(plist, f)

            print("Info.plist updated successfully")

    print("\nBuild complete!")
    dist_dir = os.path.join(os.getcwd(), "dist")
    print(f"Executable should be in: {dist_dir}")

    if system == 'Windows':
        exe_path = (
            os.path.join(dist_dir, "Reader3.exe")
            if onefile
            else os.path.join(dist_dir, "Reader3", "Reader3.exe")
        )
        print(f"Windows executable: {exe_path}")

        # Create a portable zip for easy distribution (folder mode only).
        if not onefile and os.path.exists(os.path.join(dist_dir, "Reader3")):
            archive_base = os.path.join(dist_dir, "Reader3-windows-portable")
            if os.path.exists(f"{archive_base}.zip"):
                os.remove(f"{archive_base}.zip")
            shutil.make_archive(archive_base, "zip", dist_dir, "Reader3")
            print(f"Portable bundle: {archive_base}.zip")
            print("Share this zip and keep all files together when unzipped.")

    if system == 'Darwin':
        print("\nTo use: Place your EPUB/PDF files in the same directory "
              "as Reader3.app")
        print("Then double-click Reader3.app to start the server and open "
              "your browser.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build Reader3 executable via PyInstaller")
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Build a single-file executable instead of a directory bundle",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="Show console window (useful for debugging startup issues)",
    )
    args = parser.parse_args()
    build(onefile=args.onefile, console=args.console)
