"""
ATA Game Translator — Zero-Fail Win32 PrintWindow (PW_RENDERFULLCONTENT) & MSS
Hybrid Capture Engine, Frame-Diff Gating, HUD Noise Filtering,
Two-Pass Spatial Clustering & Adaptive Color Sampling
"""
from __future__ import annotations

import asyncio
import ctypes
from ctypes import wintypes
import math
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import mss
import numpy as np
from PIL import Image
import winocr

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

# ctypes defaults truncate HWNDs to 32 bits on 64-bit Windows.
for _name, _args, _result in (
    ("GetForegroundWindow", [], wintypes.HWND),
    ("GetWindowThreadProcessId", [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
    ("GetWindowRect", [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
    ("GetClientRect", [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
    ("ClientToScreen", [wintypes.HWND, ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
    ("IsWindow", [wintypes.HWND], wintypes.BOOL),
    ("IsWindowVisible", [wintypes.HWND], wintypes.BOOL),
    ("IsIconic", [wintypes.HWND], wintypes.BOOL),
    ("GetWindowTextLengthW", [wintypes.HWND], ctypes.c_int),
    ("GetClassNameW", [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
    ("GetWindowLongW", [wintypes.HWND, ctypes.c_int], wintypes.LONG),
    ("SetWindowLongW", [wintypes.HWND, ctypes.c_int, wintypes.LONG], wintypes.LONG),
    ("SetWindowPos", [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.BOOL),
    ("SetWindowDisplayAffinity", [wintypes.HWND, wintypes.DWORD], wintypes.BOOL),
):
    _fn = getattr(user32, _name)
    _fn.argtypes, _fn.restype = _args, _result

user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.GetWindowDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.BitBlt.argtypes = [
    wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD,
]
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.GetDIBits.argtypes = [
    wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
    ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT,
]
gdi32.GetDIBits.restype = ctypes.c_int
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.PrintWindow.restype = wintypes.BOOL


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


@dataclass
class TextBlock:
    text: str
    x: int          # Screen absolute X
    y: int          # Screen absolute Y
    w: int          # Width in pixels
    h: int          # Height in pixels
    line_count: int
    avg_line_h: float
    bg_hex: str     # Sampled background color (#RRGGBB)
    fg_hex: str     # Sampled text foreground color (#RRGGBB)
    translated: str = ""
    speaker: str = ""


_VOWEL_RE = re.compile(r"[aeiouyAEIOUY]")
_FPS_METRIC_RE = re.compile(
    r"^\s*[+\-]?\d+(\.\d+)?\s*(fps|ms|hz|mb|gb|kb|°c|%|m|km|ft|xp|hp|mp|lv|lvl|g|kg)\s*$",
    re.IGNORECASE,
)
_REPEATED_CHAR_RE = re.compile(r"^([A-Za-z])\1{1,}$")
_COMPASS_SET = {"N", "S", "E", "W", "NW", "NE", "SW", "SE"}
_SHORT_VALID_WORDS = {"no", "go", "up", "on", "ok"}

# ── MULTI-LAYER TURKISH & SELF-TRANSLATION REJECTION ENGINE ──
_TR_DIACRITIC_RE = re.compile(r"[çğıİöşüÇĞÖŞÜâîûÂÎÛ]")
_TR_CHAR_MAP = str.maketrans("çğıİöşüÇĞÖŞÜâîûÂÎÛ", "cgiiosuCGOSUaiuAIU")

# Unmistakable Turkish words in ASCII-stripped form (excluding any short words shared with English)
_TR_ASCII_WORDS: set[str] = {
    # Core Turkish function words & stopwords
    "icin", "olarak", "ancak", "fakat", "lakin", "cunku", "oyle", "boyle", "soyle",
    "kadar", "sonra", "once", "uzerinde", "uzerine", "altinda", "arkasinda", "arkasindaki",
    "arkasindan", "icinde", "icindeki", "disinda", "karsi", "dogru", "gore", "degil",
    "evet", "hayir", "tamam", "lutfen", "simdi", "henuz", "hala", "artik", "sadece",
    "yalniz", "butun", "herkes", "hicbir", "bazi", "biraz", "cok", "daha", "veya",
    "yahut", "ile", "ise", "ama", "hem", "nasil", "neden", "niye", "nerede", "nereden",
    "nereye", "hangi", "kimin", "kendi", "onlar", "bunlar", "sunlar",
    # Game / UI / Desktop / Translator Turkish vocabulary (ASCII-normalized)
    "gorev", "gorevi", "gorevler", "bolum", "sahne", "sonraki", "onceki", "canli",
    "oyun", "oyunu", "simulator", "simulatoru", "ceviri", "ceviriyi", "cevir",
    "baslat", "duraklat", "durdur", "kapat", "acmak", "temizle", "katman", "katmani",
    "alan", "sifirla", "ayarlar", "envanter", "yukle", "kaydet", "devam", "masaustu",
    "masaustune", "cikis", "iptal", "onayla", "uygula", "sistem", "sorunlu", "turkce",
    "turkceye", "turkceleri", "turkceleride", "cevirmeye", "calisiyor", "profesyonel",
    "gelistir", "arayuz", "tasarim", "tasarimlari", "dosya", "klasor", "pencere",
    "ekran", "bolge", "bolgesi", "hedef", "aktif", "beklemede", "hazir", "yama",
    "blok", "bellek", "akis", "akisi", "gorunum", "modu", "yerinde", "sinematik",
    "altyazi", "motoru", "mimarisi", "ozel", "isimleri", "konusmaci", "etiketlerini",
    "koru", "dublaj", "sesi", "kisma", "tusuna", "basili", "tutun", "basin",
    # Translated RPG scene words (ASCII-normalized)
    "golgeler", "selalenin", "gizli", "girisi", "bulun", "kadim", "runlu", "buyuk",
    "kilic", "kilicini", "vurus", "hasarini", "olmayan", "dusmanlara", "yuzde",
    "artirir", "aksam", "olmadan", "kampa", "geri", "donmeliyiz", "eski", "sandigi",
    "fisildayan", "orman", "gece", "yarisindan", "meyhanede", "konusun", "gorus",
    "iksiri", "oyuncunun", "karanlik", "magaralarda", "altmis", "saniye", "boyunca",
    "sekilde", "gormesini", "saglar", "izleri", "dikkatlice", "takip", "edin",
    "canavar", "yakinlarda", "saklaniyor", "gumus", "cekmek", "soygun", "odasindaki",
    "guvenlik", "kameralarini", "devre", "disi", "birak", "sibernetik", "optik",
    "tarayici", "dusman", "zayifliklarini", "aglarini", "duvarlarin", "ortaya",
    "cikarir", "uyan", "samuray", "yakacak", "sehrimiz", "bizi", "kampta", "bekliyor",
    "yeni", "eklenen", "yetenekleri", "incelendi", "rapor", "durum", "analiz", "analizi",
}

# Unmistakable Turkish agglutinative suffixes on words >= 6 chars
_TR_SUFFIX_RE = re.compile(
    r"^[a-z]{3,}(?:iyor|uyor|iyorsun|iyoruz|iyorlar|meliyiz|maliyiz|melisin|malisin|"
    r"sindan|sinden|larindan|lerinden|ndaki|ndeki|odaki|odeki|larina|lerine|"
    r"lardan|lerden|masina|mesine|dikca|dikce|yacak|yecek|acagi|ecegi)$"
)

# Exact short Turkish UI phrases (ASCII lowercase)
_TR_EXACT_PHRASES: set[str] = {
    "devam et",
    "oyun yukle",
    "masaustune don",
    "sonraki sahne",
    "onceki sahne",
    "anlik cevir",
    "katmani temizle",
    "simulatoru kapat",
    "demo sahnesi ac",
    "alan sec / sifirla",
    "canli ceviriyi baslat",
    "canli ceviriyi duraklat",
    "canli oyun simulatoru",
    "aktif yama",
    "tarama bekliyor",
}

_KNOWN_TR_TRANSLATIONS_ASCII: set[str] = set(_TR_EXACT_PHRASES)


def normalize_ascii_tr(text: str) -> str:
    s = text.translate(_TR_CHAR_MAP).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def register_known_turkish_translation(tr_text: str) -> None:
    norm = normalize_ascii_tr(tr_text)
    if len(norm) >= 3:
        # Bound long-running session memory while keeping the seed UI vocabulary.
        if len(_KNOWN_TR_TRANSLATIONS_ASCII) >= 16384:
            _KNOWN_TR_TRANSLATIONS_ASCII.clear()
            _KNOWN_TR_TRANSLATIONS_ASCII.update(_TR_EXACT_PHRASES)
        _KNOWN_TR_TRANSLATIONS_ASCII.add(norm)


def is_turkish_text(text: str) -> bool:
    """
    Returns True if `text` is already Turkish (either containing Turkish diacritics,
    matching a previously produced Turkish translation, or containing unmistakable
    ASCII-stripped Turkish vocabulary/morphology read by an English OCR engine).
    """
    cleaned = text.strip()
    if not cleaned:
        return False

    # 1. Any Turkish-specific diacritic character -> 100% Turkish
    if _TR_DIACRITIC_RE.search(cleaned):
        return True

    norm = normalize_ascii_tr(cleaned)
    if not norm:
        return False

    # 2. Exact match with known Turkish translations or UI phrases
    if norm in _KNOWN_TR_TRANSLATIONS_ASCII:
        return True

    words = [w for w in norm.split(" ") if len(w) >= 2]
    if not words:
        return False

    # 3. Check word hits against Turkish ASCII vocabulary & Turkish agglutinative suffixes
    tr_hits = 0
    for w in words:
        if w in _TR_ASCII_WORDS or _TR_SUFFIX_RE.match(w):
            tr_hits += 1

    if len(words) == 1:
        return tr_hits >= 1
    if len(words) <= 3:
        return tr_hits >= 1
    # For longer sentences (4+ words), 2+ Turkish words OR >= 30% Turkish word density -> Turkish
    if tr_hits >= 2 or (tr_hits / len(words)) >= 0.30:
        return True

    return False


def is_valid_game_text(text: str) -> bool:
    cleaned = text.strip()
    if not cleaned:
        return False
    if cleaned.upper() in _COMPASS_SET:
        return False
    if _FPS_METRIC_RE.match(cleaned):
        return False

    # Reject text that is already in Turkish so we NEVER translate Turkish -> Turkish
    if is_turkish_text(cleaned):
        return False

    alpha_chars = [c for c in cleaned if c.isalpha()]
    alpha_count = len(alpha_chars)
    if alpha_count < 2:
        return False
    if alpha_count == 2 and cleaned.lower() not in _SHORT_VALID_WORDS:
        return False

    non_space_len = max(1, len(re.sub(r"\s+", "", cleaned)))
    if (alpha_count / non_space_len) < 0.42:
        return False

    alpha_str = "".join(alpha_chars)
    if _REPEATED_CHAR_RE.match(alpha_str):
        return False
    if not _VOWEL_RE.search(alpha_str):
        return False

    return True


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{max(0, min(255, int(r))):02x}{max(0, min(255, int(g))):02x}{max(0, min(255, int(b))):02x}"


def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    if len(h) != 6:
        return (240, 240, 245)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _color_distance(hex1: str, hex2: str) -> float:
    r1, g1, b1 = _hex_to_rgb(hex1)
    r2, g2, b2 = _hex_to_rgb(hex2)
    return math.sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)


def _luminance(r: float, g: float, b: float) -> float:
    return 0.299 * r + 0.587 * g + 0.114 * b


def sample_block_colors(rgb_arr: np.ndarray, x: int, y: int, w: int, h: int) -> tuple[str, str]:
    img_h, img_w, _ = rgb_arr.shape
    x0 = max(0, min(img_w - 1, x))
    y0 = max(0, min(img_h - 1, y))
    x1 = max(x0 + 1, min(img_w, x + w))
    y1 = max(y0 + 1, min(img_h, y + h))

    bx0 = max(0, x0 - 4)
    by0 = max(0, y0 - 4)
    bx1 = min(img_w, x1 + 4)
    by1 = min(img_h, y1 + 4)

    patch = rgb_arr[y0:y1, x0:x1]
    if patch.size == 0:
        return "#10141e", "#f4f6fb"

    border_pixels = []
    if by0 < y0:
        border_pixels.append(rgb_arr[by0:y0, bx0:bx1].reshape(-1, 3))
    if y1 < by1:
        border_pixels.append(rgb_arr[y1:by1, bx0:bx1].reshape(-1, 3))
    if bx0 < x0:
        border_pixels.append(rgb_arr[y0:y1, bx0:x0].reshape(-1, 3))
    if x1 < bx1:
        border_pixels.append(rgb_arr[y0:y1, x1:bx1].reshape(-1, 3))

    if border_pixels:
        border_all = np.vstack(border_pixels).astype(np.float32)
        bg_rgb = np.median(border_all, axis=0)
        border_std = float(np.mean(np.std(border_all, axis=0)))
    else:
        flat_init = patch.reshape(-1, 3).astype(np.float32)
        bg_rgb = np.median(flat_init, axis=0)
        border_std = float(np.mean(np.std(flat_init, axis=0)))

    bg_r, bg_g, bg_b = float(bg_rgb[0]), float(bg_rgb[1]), float(bg_rgb[2])
    bg_lum = _luminance(bg_r, bg_g, bg_b)

    is_floating_3d = border_std > 28.0 or bg_lum > 155.0
    if is_floating_3d:
        bg_r, bg_g, bg_b = 14.0, 18.0, 27.0
        bg_lum = _luminance(bg_r, bg_g, bg_b)
    elif 75.0 < bg_lum <= 155.0:
        bg_r, bg_g, bg_b = bg_r * 0.42, bg_g * 0.42, bg_b * 0.45
        bg_lum = _luminance(bg_r, bg_g, bg_b)

    flat_patch = patch.reshape(-1, 3).astype(np.float32)
    patch_lum = 0.299 * flat_patch[:, 0] + 0.587 * flat_patch[:, 1] + 0.114 * flat_patch[:, 2]
    lum_diff = np.abs(patch_lum - bg_lum)
    threshold = np.percentile(lum_diff, 88)
    glyph_pixels = flat_patch[lum_diff >= threshold]

    if len(glyph_pixels) > 0:
        fg_rgb = np.median(glyph_pixels, axis=0)
        fg_r, fg_g, fg_b = float(fg_rgb[0]), float(fg_rgb[1]), float(fg_rgb[2])
    else:
        fg_r, fg_g, fg_b = (245.0, 247.0, 250.0)

    fg_lum = _luminance(fg_r, fg_g, fg_b)
    if abs(fg_lum - bg_lum) < 95.0:
        fg_r, fg_g, fg_b = (248.0, 250.0, 252.0) if bg_lum < 135.0 else (18.0, 20.0, 26.0)

    return _rgb_to_hex(int(bg_r), int(bg_g), int(bg_b)), _rgb_to_hex(int(fg_r), int(fg_g), int(fg_b))


@dataclass
class _RawLine:
    text: str
    x: float
    y: float
    w: float
    h: float
    bg_hex: str
    fg_hex: str


def _cluster_lines_into_blocks(
    raw_lines: list[_RawLine],
    rgb_arr: np.ndarray,
    offset_x: int,
    offset_y: int,
) -> list[TextBlock]:
    if not raw_lines:
        return []

    by_row = sorted(raw_lines, key=lambda ln: (ln.y + ln.h * 0.5, ln.x))
    stitched_lines: list[_RawLine] = []

    for ln in by_row:
        if not stitched_lines:
            stitched_lines.append(ln)
            continue
        prev = stitched_lines[-1]
        max_h = max(ln.h, prev.h)
        same_row = abs((ln.y + ln.h * 0.5) - (prev.y + prev.h * 0.5)) <= max_h * 0.42
        h_gap = ln.x - (prev.x + prev.w)
        same_color = _color_distance(ln.fg_hex, prev.fg_hex) <= 65.0

        if same_row and (-4.0 <= h_gap <= max_h * 1.65) and same_color:
            new_x0 = min(prev.x, ln.x)
            new_y0 = min(prev.y, ln.y)
            new_x1 = max(prev.x + prev.w, ln.x + ln.w)
            new_y1 = max(prev.y + prev.h, ln.y + ln.h)
            prev.text = f"{prev.text.strip()} {ln.text.strip()}"
            prev.x = new_x0
            prev.y = new_y0
            prev.w = new_x1 - new_x0
            prev.h = new_y1 - new_y0
        else:
            stitched_lines.append(ln)

    sorted_lines = sorted(stitched_lines, key=lambda ln: (ln.y, ln.x))
    clusters: list[list[_RawLine]] = []

    for ln in sorted_lines:
        placed = False
        for cluster in clusters:
            last = cluster[-1]
            height_ratio = ln.h / max(1.0, last.h)
            if not (0.65 <= height_ratio <= 1.55):
                continue

            v_gap = ln.y - (last.y + last.h)
            max_gap = max(ln.h, last.h) * 0.55
            if not (-max(ln.h, last.h) * 0.15 <= v_gap <= max_gap):
                continue

            if _color_distance(ln.fg_hex, last.fg_hex) > 62.0:
                continue

            c_x0 = min(item.x for item in cluster)
            c_x1 = max(item.x + item.w for item in cluster)
            ln_x0, ln_x1 = ln.x, ln.x + ln.w

            overlap = max(0.0, min(c_x1, ln_x1) - max(c_x0, ln_x0))
            min_w = max(1.0, min(c_x1 - c_x0, ln.w))
            left_diff = abs(c_x0 - ln_x0)
            center_diff = abs(((c_x0 + c_x1) / 2.0) - ((ln_x0 + ln_x1) / 2.0))

            if overlap / min_w >= 0.20 and (
                left_diff <= max(ln.h, last.h) * 2.2 or center_diff <= max(ln.h, last.h) * 2.8
            ):
                cluster.append(ln)
                placed = True
                break

        if not placed:
            clusters.append([ln])

    blocks: list[TextBlock] = []
    for cluster in clusters:
        full_text = " ".join(item.text.strip() for item in cluster if item.text.strip())
        full_text = re.sub(r"\s+", " ", full_text).strip()
        if not is_valid_game_text(full_text):
            continue

        x0 = int(min(item.x for item in cluster))
        y0 = int(min(item.y for item in cluster))
        x1 = int(max(item.x + item.w for item in cluster))
        y1 = int(max(item.y + item.h for item in cluster))
        w = max(16, x1 - x0)
        h = max(14, y1 - y0)
        avg_h = float(sum(item.h for item in cluster)) / len(cluster)

        bg_hex, fg_hex = sample_block_colors(rgb_arr, x0, y0, w, h)
        blocks.append(
            TextBlock(
                text=full_text,
                x=x0 + offset_x,
                y=y0 + offset_y,
                w=w,
                h=h,
                line_count=len(cluster),
                avg_line_h=avg_h,
                bg_hex=bg_hex,
                fg_hex=fg_hex,
            )
        )

    return blocks


def find_target_game_hwnd() -> Optional[int]:
    """
    Finds the active foreground window, or if our own Control Panel is focused,
    finds the highest Z-order visible application/game window underneath it.
    """
    my_pid = os.getpid()
    fg_hwnd = user32.GetForegroundWindow()
    if fg_hwnd:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(pid))
        if pid.value != my_pid and user32.IsWindowVisible(fg_hwnd) and not user32.IsIconic(fg_hwnd):
            return int(fg_hwnd)

    found_hwnd: Optional[int] = None
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _enum_cb(hwnd: int, _lparam: int) -> bool:
        nonlocal found_hwnd
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == my_pid:
            return True

        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w < 240 or h < 160:
            return True

        cls_buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls_buf, 63)
        if cls_buf.value in {"Progman", "WorkerW", "Shell_TrayWnd", "Windows.UI.Core.CoreWindow"}:
            return True

        title_len = user32.GetWindowTextLengthW(hwnd)
        if title_len <= 0:
            return True

        found_hwnd = int(hwnd)
        return False

    user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
    return found_hwnd


def capture_window_client_rgb(
    hwnd: int,
    crop_roi: Optional[list[int]] = None,
) -> Optional[tuple[np.ndarray, tuple[int, int, int, int]]]:
    """
    Capture a client area using PrintWindow, with BitBlt fallback and paired GDI cleanup.
    Unsupported windows return None so the caller can try desktop capture.
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return None

    win_rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(win_rect)):
        return None
    w = win_rect.right - win_rect.left
    h = win_rect.bottom - win_rect.top
    if w <= 32 or h <= 32:
        return None

    cli_rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(cli_rect))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))

    hdc_win = user32.GetWindowDC(hwnd)
    if not hdc_win:
        return None

    memdc = hbmp = old = None
    try:
        memdc = gdi32.CreateCompatibleDC(hdc_win)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
        if not memdc or not hbmp:
            return None
        old = gdi32.SelectObject(memdc, hbmp)

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            if not gdi32.BitBlt(memdc, 0, 0, w, h, hdc_win, 0, 0, 0x00CC0020):
                return None
        else:
            ok = user32.PrintWindow(hwnd, memdc, 2)
            if not ok:
                if not gdi32.BitBlt(memdc, 0, 0, w, h, hdc_win, 0, 0, 0x00CC0020):
                    return None

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        buf = ctypes.create_string_buffer(w * h * 4)
        # GetDIBits requires the bitmap not to be selected into a DC.
        gdi32.SelectObject(memdc, old)
        old = None
        if gdi32.GetDIBits(memdc, hbmp, 0, h, buf, ctypes.byref(bmi), 0) != h:
            return None
    finally:
        if old and memdc:
            gdi32.SelectObject(memdc, old)
        if hbmp:
            gdi32.DeleteObject(hbmp)
        if memdc:
            gdi32.DeleteDC(memdc)
        user32.ReleaseDC(hwnd, hdc_win)

    full_bgra = np.frombuffer(buf, dtype=np.uint8).reshape((h, w, 4))
    full_rgb = full_bgra[:, :, [2, 1, 0]]

    # Crop to Client Area (excludes title bar and invisible window borders)
    cx0 = max(0, pt.x - win_rect.left)
    cy0 = max(0, pt.y - win_rect.top)
    cw = min(w - cx0, cli_rect.right - cli_rect.left)
    ch = min(h - cy0, cli_rect.bottom - cli_rect.top)
    if cw <= 20 or ch <= 20:
        client_rgb = full_rgb.copy()
        screen_x, screen_y, screen_w, screen_h = win_rect.left, win_rect.top, w, h
    else:
        client_rgb = full_rgb[cy0 : cy0 + ch, cx0 : cx0 + cw].copy()
        screen_x, screen_y, screen_w, screen_h = pt.x, pt.y, cw, ch

    # If a specific screen ROI is active, intersect it with the captured client rect
    if crop_roi and len(crop_roi) == 4 and crop_roi[2] > 30 and crop_roi[3] > 20:
        rx, ry, rw, rh = int(crop_roi[0]), int(crop_roi[1]), int(crop_roi[2]), int(crop_roi[3])
        ix0 = max(screen_x, rx)
        iy0 = max(screen_y, ry)
        ix1 = min(screen_x + screen_w, rx + rw)
        iy1 = min(screen_y + screen_h, ry + rh)
        if ix1 - ix0 > 0 and iy1 - iy0 > 0:
            sub_x0 = ix0 - screen_x
            sub_y0 = iy0 - screen_y
            sub_w = ix1 - ix0
            sub_h = iy1 - iy0
            return client_rgb[sub_y0 : sub_y0 + sub_h, sub_x0 : sub_x0 + sub_w].copy(), (
                ix0,
                iy0,
                sub_w,
                sub_h,
            )
        return None

    return client_rgb, (screen_x, screen_y, screen_w, screen_h)


class ScreenOcrEngine:
    """
    Captures game windows via Win32 PrintWindow(PW_RENDERFULLCONTENT=2) with MSS fallback,
    gates unchanged frames via downsampled perceptual diffing, upscales compact ROIs,
    and runs Windows Native WinRT OCR.
    """

    def __init__(self, lang: str = "en") -> None:
        self.lang = lang
        self._prev_thumb: Optional[np.ndarray] = None
        self._last_roi: Optional[tuple[int, int, int, int]] = None
        self._tls = threading.local()
        self._diff_lock = threading.Lock()
        self._last_gate_time = 0.0

    def _get_sct(self) -> mss.base.MSSBase:
        sct = getattr(self._tls, "sct", None)
        if sct is None:
            sct = mss.mss()
            self._tls.sct = sct
        return sct

    def reset_diff_gate(self) -> None:
        with self._diff_lock:
            self._prev_thumb = None

    def close(self) -> None:
        """Release the capture handle on the persistent worker that owns it."""
        sct = getattr(self._tls, "sct", None)
        if sct is not None:
            sct.close()
            self._tls.sct = None

    def capture_rgb(
        self,
        roi: Optional[list[int]] = None,
        target_hwnd: Optional[int] = None,
    ) -> tuple[np.ndarray, tuple[int, int, int, int]]:
        # 1. Try explicit target_hwnd (e.g., DemoGameWindow) via PrintWindow
        if target_hwnd:
            res = capture_window_client_rgb(target_hwnd, crop_roi=roi)
            if res is not None:
                return res

        # Desktop capture stays on the worker: QScreen/QPixmap are GUI-thread APIs.
        sct = self._get_sct()
        desktop = sct.monitors[0]
        mon = sct.monitors[1]
        if roi is not None:
            if len(roi) != 4 or roi[2] <= 0 or roi[3] <= 0:
                raise ValueError("Capture ROI must have positive width and height")
            left = max(desktop["left"], int(roi[0]))
            top = max(desktop["top"], int(roi[1]))
            right = min(desktop["left"] + desktop["width"], int(roi[0] + roi[2]))
            bottom = min(desktop["top"] + desktop["height"], int(roi[1] + roi[3]))
            if right <= left or bottom <= top:
                raise ValueError("Capture ROI does not intersect the virtual desktop")
            width, height = right-left, bottom-top
        else:
            left, top, width, height = mon["left"], mon["top"], mon["width"], mon["height"]
        try:
            shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
            bgra = np.frombuffer(shot.bgra, dtype=np.uint8).reshape((shot.height, shot.width, 4))
            return bgra[:, :, [2, 1, 0]].copy(), (left, top, width, height)
        except Exception:
            auto_hwnd = find_target_game_hwnd()
            if auto_hwnd:
                result = capture_window_client_rgb(auto_hwnd, crop_roi=roi)
                if result is not None:
                    return result
            raise

    def has_frame_changed(self, rgb: np.ndarray, rect: tuple[int, int, int, int], threshold: float = 1.2) -> bool:
        # Area resampling sees small text changes that sparse pixel sampling missed.
        small = cv2.resize(rgb, (320, 180), interpolation=cv2.INTER_AREA)
        thumb = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY).astype(np.float32)
        now = time.monotonic()
        with self._diff_lock:
            changed = self._prev_thumb is None or self._last_roi != rect
            if not changed:
                delta = np.abs(thumb-self._prev_thumb)
                tile_peak = float(delta.reshape(20, 9, 20, 16).mean(axis=(1, 3)).max())
                changed = (float(delta.mean()) >= threshold
                           or float(np.mean(delta >= 12)) >= .002
                           or tile_peak >= max(3.6, threshold*3)
                           or now-self._last_gate_time >= 2.0)
            if changed:
                self._prev_thumb, self._last_roi = thumb, rect
                self._last_gate_time = now
            return changed

    async def recognize_rgb_async(
        self, rgb: np.ndarray, offset_x: int = 0, offset_y: int = 0,
    ) -> list[TextBlock]:
        result = ctypes.windll.ole32.CoInitializeEx(None, 0)
        try:
            return await self._recognize_rgb_initialized(rgb, offset_x, offset_y)
        finally:
            if result in (0, 1):
                ctypes.windll.ole32.CoUninitialize()

    async def _recognize_rgb_initialized(
        self, rgb: np.ndarray, offset_x: int, offset_y: int,
    ) -> list[TextBlock]:
        h, w, _ = rgb.shape
        scale = 1.5 if (h < 280 or w < 640) else 1.0
        if scale > 1.0:
            ocr_rgb = cv2.resize(rgb, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
        else:
            ocr_rgb = rgb

        pil_img = Image.fromarray(ocr_rgb)
        ocr_result = None
        for lang_tag in (self.lang, "en-US", "en-GB", "en"):
            try:
                ocr_result = await winocr.recognize_pil(pil_img, lang_tag)
                if ocr_result is not None:
                    break
            except Exception:
                continue
        if ocr_result is None:
            ocr_result = await winocr.recognize_pil(pil_img)

        raw_lines: list[_RawLine] = []
        inv_scale = 1.0 / scale
        for line in ocr_result.lines:
            words = list(line.words)
            if not words:
                continue
            x0 = min(float(w_obj.bounding_rect.x) for w_obj in words) * inv_scale
            y0 = min(float(w_obj.bounding_rect.y) for w_obj in words) * inv_scale
            x1 = max(float(w_obj.bounding_rect.x + w_obj.bounding_rect.width) for w_obj in words) * inv_scale
            y1 = max(float(w_obj.bounding_rect.y + w_obj.bounding_rect.height) for w_obj in words) * inv_scale
            lw = max(4.0, x1 - x0)
            lh = max(4.0, y1 - y0)
            bg_hex, fg_hex = sample_block_colors(rgb, int(x0), int(y0), int(lw), int(lh))
            raw_lines.append(
                _RawLine(
                    text=line.text,
                    x=x0,
                    y=y0,
                    w=lw,
                    h=lh,
                    bg_hex=bg_hex,
                    fg_hex=fg_hex,
                )
            )

        return _cluster_lines_into_blocks(raw_lines, rgb, offset_x, offset_y)

    def scan_screen(
        self,
        roi: Optional[list[int]] = None,
        force: bool = False,
        diff_threshold: float = 1.2,
        target_hwnd: Optional[int] = None,
    ) -> Optional[list[TextBlock]]:
        rgb, rect = self.capture_rgb(roi=roi, target_hwnd=target_hwnd)
        changed = self.has_frame_changed(rgb, rect, threshold=diff_threshold)
        if not force and not changed:
            return None

        left, top, _, _ = rect
        return asyncio.run(self.recognize_rgb_async(rgb, offset_x=left, offset_y=top))
