import os
import subprocess
import platform
import plistlib


def build():
    system = platform.system()
    sep = ';' if system == 'Windows' else ':'

    # Hidden imports that PyInstaller may miss
    hidden_imports = [
        'fastapi',
        'fastapi.responses',
        'fastapi.staticfiles',
        'fastapi.templating',
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
        'ebooklib',
        'bs4',
    ]

    # Packages to collect all files from
    collect_all = [
        'fastapi',
        'starlette',
        'uvicorn',
    ]

    # Define the command
    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        f"--add-data=templates{sep}templates",
        "--name=Reader3",
    ]

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

    if system == 'Darwin':
        print("\nTo use: Place your EPUB/PDF files in the same directory "
              "as Reader3.app")
        print("Then double-click Reader3.app to start the server and open "
              "your browser.")


if __name__ == "__main__":
    build()
