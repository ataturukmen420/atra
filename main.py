"""
ATA Game Translator — Entrypoint
Usage:
  python main.py             # Opens Control Panel + Transparent Overlay (Real Game Mode)
  python main.py --demo      # Opens Control Panel + Demo RPG Game Scene with Live In-Place Translation
"""
from __future__ import annotations

import os
import sys

# Guard against pythonw.exe where sys.stdout / sys.stderr are None
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
elif hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
elif hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# CRITICAL WINDOWS C++ DLL ORDER: ctranslate2 & sentencepiece MUST load before PyQt6 Qt6Core.dll
import ctranslate2  # noqa: F401
import sentencepiece  # noqa: F401

# Lock Qt to 1:1 physical pixel coordinates so Win32/MSS OCR rects align 100% on 125%/150% DPI displays
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
os.environ.setdefault("QT_SCALE_FACTOR", "1")

from src.app import AtaGameTranslatorApp


def main() -> None:
    auto_demo = "--demo" in sys.argv
    app = AtaGameTranslatorApp(auto_demo=auto_demo)
    app.run()


if __name__ == "__main__":
    main()
