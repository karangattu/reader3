import os
import sys
import subprocess
import platform

def build():
    system = platform.system()
    sep = ';' if system == 'Windows' else ':'
    
    # Define the command
    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        f"--add-data=templates{sep}templates",
        "--name=Reader3",
        "launcher.py"
    ]
    
    print(f"Building for {system}...")
    print("Command:", " ".join(cmd))
    
    # Run PyInstaller
    subprocess.check_call(cmd)
    
    print("\nBuild complete!")
    dist_dir = os.path.join(os.getcwd(), "dist")
    print(f"Executable should be in: {dist_dir}")

if __name__ == "__main__":
    build()
