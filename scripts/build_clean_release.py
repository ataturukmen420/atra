"""Build a clean, allowlisted release staging directory with zero personal data or dev artifacts."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING_DIR = ROOT / "dist" / "Atra-Release-Staging"

ALLOWED_FILES = [
    "main.py",
    "requirements.txt",
    "README.md",
    "LICENSE",
    "PRIVACY_DRAFT.md",
    "RELEASE_READINESS.md",
    "THIRD_PARTY_NOTICES.md",
    "packaging/AppxManifest.xml",
    "scripts/build_clean_release.py",
    "scripts/build_store_package.py",
    "glossary.json",
    "src/__init__.py",
    "src/app.py",
    "src/audio_tts.py",
    "src/brand.py",
    "src/config.py",
    "src/demo_scene.py",
    "src/model_manifest.py",
    "src/model_setup.py",
    "src/ocr_engine.py",
    "src/overlay.py",
    "src/studio_ui.py",
    "src/svg_medallions.py",
    "src/translator.py",
    "assets/app_icon.ico",
    "assets/app_logo.png",
    "assets/atra_icon.svg",
    "assets/atra_icon_1024.png",
    "assets/atra_mark.svg",
]

FORBIDDEN_PATTERNS = (
    "config.json",
    "*.sqlite3",
    "*.db",
    "*.log",
    ".env",
    "CODEX_PROMPT.md",
    "__pycache__",
)


def build_staging(target: Path = STAGING_DIR) -> Path:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    for rel in ALLOWED_FILES:
        src = ROOT / rel
        if not src.is_file():
            raise FileNotFoundError(f"Missing required release file: {rel}")
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    for pattern in FORBIDDEN_PATTERNS:
        leaked = [
            p for p in target.rglob(pattern)
            if p.name != "config.json" or p.parent != target / "models" / "opus-mt-en-tr-ct2"
        ]
        if leaked:
            raise RuntimeError(f"Forbidden artifact leaked into staging bundle: {leaked}")

    return target


if __name__ == "__main__":
    out = build_staging()
    print(f"[PASS] Clean release bundle staged at: {out} ({len(ALLOWED_FILES)} allowlisted files, 0 personal files)")
    sys.exit(0)
