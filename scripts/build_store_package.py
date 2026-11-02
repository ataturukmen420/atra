"""
Build standalone Windows executable (dist/Atra/Atra.exe) and Microsoft Store MSIX layout
with all required Store visual assets and zero personal data leakage.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build" / "pyinstaller"
APP_OUT_DIR = DIST_DIR / "Atra"
MANIFEST_SRC = ROOT / "packaging" / "AppxManifest.xml"
SOURCE_ICON = ROOT / "assets" / "atra_icon_1024.png"


def generate_store_tiles(assets_out: Path) -> None:
    assets_out.mkdir(parents=True, exist_ok=True)
    with Image.open(SOURCE_ICON) as src_img:
        rgba = src_img.convert("RGBA")
        for filename, size in [
            ("StoreLogo.png", (50, 50)),
            ("Square44x44Logo.png", (44, 44)),
            ("Square150x150Logo.png", (150, 150)),
        ]:
            tile = rgba.resize(size, Image.Resampling.LANCZOS)
            tile.save(assets_out / filename, format="PNG")

        wide = Image.new("RGBA", (310, 150), (0, 0, 0, 0))
        icon_mid = rgba.resize((110, 110), Image.Resampling.LANCZOS)
        wide.paste(icon_mid, ((310 - 110) // 2, (150 - 110) // 2), icon_mid)
        wide.save(assets_out / "Wide310x150Logo.png", format="PNG")


def write_spec_file(spec_path: Path) -> None:
    rthook_path = BUILD_DIR / "rthook_ct2_first.py"
    rthook_path.write_text(
        "import os, sys\n"
        "if hasattr(sys, '_MEIPASS'):\n"
        "    for sub in ('ctranslate2', 'sentencepiece'):\n"
        "        d = os.path.join(sys._MEIPASS, sub)\n"
        "        if os.path.isdir(d):\n"
        "            os.environ['PATH'] = d + os.pathsep + os.environ.get('PATH', '')\n"
        "            if hasattr(os, 'add_dll_directory'):\n"
        "                os.add_dll_directory(d)\n"
        "import ctranslate2\n"
        "import sentencepiece\n",
        encoding="utf-8",
    )
    main_py = repr(str(ROOT / "main.py"))
    rthook_py = repr(str(rthook_path))
    icon_ico = repr(str(ROOT / "assets" / "app_icon.ico"))
    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-
import PyInstaller.building.build_main as _bm

_orig_find_bin = _bm.find_binary_dependencies
def _ordered_find_bin(binaries, collected_packages, *args, **kwargs):
    filtered = [p for p in collected_packages if not p.startswith(('ctranslate2', 'sentencepiece'))]
    return _orig_find_bin(binaries, filtered, *args, **kwargs)
_bm.find_binary_dependencies = _ordered_find_bin

a = Analysis(
    [{main_py}],
    pathex=[{repr(str(ROOT))}],
    binaries=[],
    datas=[],
    hiddenimports=[
        'ctranslate2',
        'sentencepiece',
        'win32crypt',
        'win32gui',
        'win32ui',
        'win32con',
        'pycaw.pycaw',
        'comtypes',
        'edge_tts',
        'winrt.windows.media.ocr',
        'winrt.windows.globalization',
        'winrt.windows.graphics.imaging',
        'winrt.windows.storage.streams',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[{rthook_py}],
    excludes=[
        'ctranslate2.converters',
        'IPython',
        'fastapi',
        'uvicorn',
        'starlette',
        'huggingface_hub',
        'cv2',
        'tkinter',
        'matplotlib',
        'pytest',
    ],
    noarchive=False,
    optimize=0,
)
# Ensure rthook_ct2_first executes BEFORE pyi_rth_pyqt6
rth_entries = [s for s in a.scripts if 'rthook_ct2_first' in s[0]]
other_entries = [s for s in a.scripts if 'rthook_ct2_first' not in s[0]]
a.scripts[:] = rth_entries + other_entries
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Atra',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[{icon_ico}],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Atra',
)
"""
    spec_path.write_text(spec_content, encoding="utf-8")


def build_executable() -> Path:
    if APP_OUT_DIR.exists():
        shutil.rmtree(APP_OUT_DIR)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    spec_path = BUILD_DIR / "Atra.spec"
    write_spec_file(spec_path)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR / "work"),
        str(spec_path),
    ]
    subprocess.run(cmd, check=True)

    # Ensure native ctranslate2 and sentencepiece package folders + DLLs are complete in _internal
    import ctranslate2
    import sentencepiece

    internal = APP_OUT_DIR / "_internal"
    ct2_pkg_dir = Path(ctranslate2.__file__).resolve().parent
    shutil.copytree(ct2_pkg_dir, internal / "ctranslate2", dirs_exist_ok=True)
    spm_pkg_dir = Path(sentencepiece.__file__).resolve().parent
    shutil.copytree(spm_pkg_dir, internal / "sentencepiece", dirs_exist_ok=True)

    # Copy read-only runtime assets to both top-level and _internal so Path(__file__).parents[1] works in all modes
    for base in (APP_OUT_DIR, internal):
        if base.exists():
            shutil.copytree(ROOT / "assets", base / "assets", dirs_exist_ok=True)
            shutil.copy2(ROOT / "glossary.json", base / "glossary.json")

    for doc in ("README.md", "LICENSE", "PRIVACY_DRAFT.md", "THIRD_PARTY_NOTICES.md", "RELEASE_READINESS.md"):
        if (ROOT / doc).is_file():
            shutil.copy2(ROOT / doc, APP_OUT_DIR / doc)

    # Generate Microsoft Store MSIX visual tiles & copy AppxManifest.xml
    generate_store_tiles(APP_OUT_DIR / "Assets")
    shutil.copy2(MANIFEST_SRC, APP_OUT_DIR / "AppxManifest.xml")

    exe_path = APP_OUT_DIR / "Atra.exe"
    if not exe_path.is_file():
        raise FileNotFoundError(f"Expected executable not found: {exe_path}")
    return exe_path


if __name__ == "__main__":
    exe = build_executable()
    print(f"[PASS] Standalone Microsoft Store / Win32 package built at: {exe}")
