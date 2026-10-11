"""Repeatable Windows build; no publish step."""
import os
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
if sys.platform != "win32":
    raise SystemExit("Build on Windows x64.")
os.chdir(root)
os.environ.setdefault("SOURCE_DATE_EPOCH","1767225600")  # Neutral 2026-01-01 PE timestamp.
subprocess.run([sys.executable,"-m","PyInstaller","--clean","--noconfirm","--onefile","--windowed",
                "--name","BloxBinds","--version-file","scripts/windows-version.txt",
                "--add-data","third_party;third_party","main.py"],check=True)
