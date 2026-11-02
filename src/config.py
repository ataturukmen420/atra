"""
ATA Game Translator (Clean-Room In-Place Game & Subtitle Translator)
Configuration & Professional Game Localization Glossary Manager
"""
from __future__ import annotations

import json
import base64
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent


def get_user_data_dir() -> Path:
    override = os.environ.get("ATRA_DATA_DIR", "").strip()
    if override:
        return Path(override)
    local_appdata = os.environ.get("LOCALAPPDATA")
    root = Path(local_appdata) if local_appdata else (Path.home() / "AppData" / "Local")
    return root / "Atra"


USER_DATA_DIR = get_user_data_dir()
LEGACY_CONFIG_PATH = BASE_DIR / "config.json"
LEGACY_CACHE_DB_PATH = BASE_DIR / "translation_cache.sqlite3"
CONFIG_PATH = USER_DATA_DIR / "config.json"
GLOSSARY_PATH = BASE_DIR / "glossary.json"
CACHE_DB_PATH = USER_DATA_DIR / "translation_cache.sqlite3"
LOG_PATH = USER_DATA_DIR / "translator.log"

_SECRET_PREFIX = "dpapi:v1:"


class CredentialProtectionError(RuntimeError):
    """The stored credential could not be protected or opened for this user."""


def _protect_secret(secret: str) -> str:
    if not secret:
        return ""
    try:
        import win32crypt
        encrypted = win32crypt.CryptProtectData(secret.encode("utf-8"), None, None, None, None, 1)
        return _SECRET_PREFIX + base64.b64encode(encrypted).decode("ascii")
    except Exception as exc:
        raise CredentialProtectionError("DeepL anahtarı Windows ile korunamadı") from exc


def _unprotect_secret(secret: str) -> str:
    if not secret.startswith(_SECRET_PREFIX):
        return secret
    try:
        import win32crypt
        blob = base64.b64decode(secret[len(_SECRET_PREFIX):], validate=True)
        return win32crypt.CryptUnprotectData(blob, None, None, None, 1)[1].decode("utf-8")
    except Exception as exc:
        raise CredentialProtectionError("DeepL anahtarı bu Windows hesabında açılamadı") from exc


DEFAULT_GLOSSARY: dict[str, str] = {
    # Main Menu & System
    "New Game": "Yeni Oyun",
    "Continue": "Devam Et",
    "Load Game": "Oyun Yükle",
    "Save Game": "Oyunu Kaydet",
    "Quick Save": "Hızlı Kayıt",
    "Quick Load": "Hızlı Yükle",
    "Settings": "Ayarlar",
    "Options": "Seçenekler",
    "System": "Sistem",
    "Credits": "Yapımcılar",
    "Extras": "Ekstralar",
    "Accessibility": "Erişilebilirlik",
    "Language": "Dil",
    "Paused": "Oyun Duraklatıldı",
    "Resume": "Devam Et",
    "Restart": "Yeniden Başlat",
    "Return to Main Menu": "Ana Menüye Dön",
    "Quit to Main Menu": "Ana Menüye Çık",
    "Quit to Desktop": "Masaüstüne Dön",
    "Exit Game": "Oyundan Çık",
    " Quit ": " Çıkış ",
    "Back": "Geri",
    "Apply": "Uygula",
    "Confirm": "Onayla",
    "Cancel": "İptal",
    "Reset to Default": "Varsayılana Sıfırla",
    "Defaults": "Varsayılanlar",
    "Press Any Key": "Herhangi Bir Tuşa Basın",
    "Press Any Button": "Herhangi Bir Tuşa Basın",
    "Loading...": "Yükleniyor...",
    "Saving...": "Kaydediliyor...",
    "Autosaving...": "Otomatik Kaydediliyor...",
    # Graphics & Display
    "Graphics": "Grafikler",
    "Display": "Görüntü",
    "Video": "Video",
    "Resolution": "Çözünürlük",
    "Window Mode": "Pencere Modu",
    "Fullscreen": "Tam Ekran",
    "Borderless Windowed": "Kenarlıksız Pencereli",
    "Windowed": "Pencereli",
    "V-Sync": "Dikey Senkronizasyon (V-Sync)",
    "Frame Rate Limit": "Kare Hızı Sınırı",
    "Field of View": "Görüş Açısı (FOV)",
    "Brightness": "Parlaklık",
    "Gamma": "Gama",
    "Shadow Quality": "Gölge Kalitesi",
    "Texture Quality": "Doku Kalitesi",
    "Anti-Aliasing": "Kenar Yumuşatma",
    "Motion Blur": "Hareket Bulanıklığı",
    "Ray Tracing": "Işın İzleme (Ray Tracing)",
    # Audio & Subtitles
    "Audio": "Ses",
    "Sound": "Ses",
    "Master Volume": "Ana Ses Seviyesi",
    "Music Volume": "Müzik Sesi",
    "Voice Volume": "Diyalog Sesi",
    "Effects Volume": "Efekt Sesi",
    "Subtitles": "Altyazılar",
    "Closed Captions": "Açıklamalı Altyazılar",
    "Subtitle Size": "Altyazı Boyutu",
    "Subtitle Background": "Altyazı Arka Planı",
    # Controls
    "Controls": "Kontroller",
    "Keybindings": "Tuş Atamaları",
    "Controller": "Oyun Kumandası",
    "Keyboard & Mouse": "Klavye ve Fare",
    "Mouse Sensitivity": "Fare Hassasiyeti",
    "Invert Y-Axis": "Y Eksenini Ters Çevir",
    "Vibration": "Titreşim",
    # RPG, Quests & Inventory
    "Inventory": "Envanter",
    "Character": "Karakter",
    "Equipment": "Ekipman",
    "Skills": "Yetenekler",
    "Skill Tree": "Yetenek Ağacı",
    "Perks": "Avantajlar",
    "Crafting": "Üretim",
    "Alchemy": "Simya",
    "Journal": "Günlük",
    "Codex": "Kodeks",
    "Map": "Harita",
    "World Map": "Dünya Haritası",
    "Fast Travel": "Hızlı Seyahat",
    "Quests": "Görevler",
    "Main Quest": "Ana Görev",
    "Side Quest": "Yan Görev",
    "Quest Completed": "Görev Tamamlandı",
    "Quest Failed": "Görev Başarısız",
    "New Objective": "Yeni Hedef",
    "Optional": "İsteğe Bağlı",
    "Level Up": "Seviye Atlandı",
    "Experience": "Deneyim (XP)",
    "Health": "Can",
    "Stamina": "Dayanıklılık",
    "Mana": "Mana",
    "Weight": "Ağırlık",
    "Damage": "Hasar",
    "Armor": "Zırh",
    "Critical Chance": "Kritik Şansı",
    "Critical Damage": "Kritik Hasarı",
    "Drop": "Bırak",
    "Equip": "Kuşan",
    "Unequip": "Çıkar",
    "Use": "Kullan",
    "Examine": "İncele",
    "Read": "Oku",
    "Talk": "Konuş",
    "Open": "Aç",
    "Close": "Kapat",
    "Take All": "Tümünü Al",
    "Loot": "Yağmala",
    "Ancient Runed Greatsword": "Kadim Rünlü Büyük Kılıç",
    "Potion of Night Vision": "Gece Görüş İksiri",
    "Cybernetic Optical Scanner": "Sibernetik Optik Tarayıcı",
}


@dataclass
class AppConfig:
    # "inplace" (CeBo-style over original text) or "subtitle" (bottom cinema bar)
    display_mode: str = "inplace"
    # "offline" (local CTranslate2 Opus-MT), "google" (fast GTX neural), "deepl" (DeepL API), "ollama"
    translation_engine: str = "offline"
    deepl_api_key: str = ""
    ollama_url: str = "http://127.0.0.1:11434/api/generate"
    ollama_model: str = "qwen2.5:3b"
    source_lang: str = "en"
    target_lang: str = "tr"

    # Scanning & OCR parameters
    scan_interval_ms: int = 280
    # ROI: [left, top, width, height] or None for full screen (excluding taskbar)
    roi: Optional[list[int]] = None
    frame_diff_threshold: float = 1.2

    # Game-aware NLP features
    preserve_proper_nouns: bool = True
    hide_unchanged_blocks: bool = True

    # TTS & Audio Ducking
    tts_enabled: bool = False
    tts_voice: str = "tr-TR-AhmetNeural"
    audio_ducking_enabled: bool = True
    audio_ducking_volume: float = 0.25

    # Visual styling
    overlay_opacity: float = 0.95
    font_family: str = "Segoe UI Semibold"
    subtitle_font_size: int = 21
    inplace_padding: int = 4

    # Hotkeys (Virtual-Key names)
    hotkey_toggle_live: str = "F8"
    hotkey_scan_once: str = "F9"
    hotkey_select_roi: str = "F10"
    hotkey_toggle_mode: str = "F11"
    hotkey_toggle_tts: str = "F12"

    def save(self) -> None:
        # A process exit must not leave a partially written configuration.
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        protected = asdict(self)
        protected["deepl_api_key"] = _protect_secret(self.deepl_api_key)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=CONFIG_PATH.parent,
                                             prefix=".config-", suffix=".tmp", delete=False) as stream:
                temporary = stream.name
                json.dump(protected, stream, indent=2, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, CONFIG_PATH)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    @classmethod
    def load(cls) -> "AppConfig":
        if (
            CONFIG_PATH == USER_DATA_DIR / "config.json"
            and not CONFIG_PATH.exists()
            and LEGACY_CONFIG_PATH.is_file()
        ):
            try:
                CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(LEGACY_CONFIG_PATH, CONFIG_PATH)
            except OSError:
                pass
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                stored_secret = raw.get("deepl_api_key", "")
                if not isinstance(stored_secret, str):
                    raise CredentialProtectionError("DeepL anahtarı geçersiz")
                raw["deepl_api_key"] = _unprotect_secret(stored_secret)
                valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
                defaults = cls()
                filtered = {}
                for k, v in raw.items():
                    if k not in valid_keys:
                        continue
                    default = getattr(defaults, k)
                    if default is None or (isinstance(v, type(default)) and not (isinstance(v, bool) and not isinstance(default, bool))):
                        filtered[k] = v
                cfg = cls(**filtered)
                if cfg.display_mode not in {"inplace", "subtitle"}:
                    cfg.display_mode = defaults.display_mode
                if cfg.translation_engine not in {"offline", "google", "deepl", "ollama"}:
                    cfg.translation_engine = defaults.translation_engine
                cfg.scan_interval_ms = max(80, min(5000, cfg.scan_interval_ms))
                cfg.subtitle_font_size = max(12, min(40, cfg.subtitle_font_size))
                cfg.inplace_padding = max(0, min(20, cfg.inplace_padding))
                cfg.overlay_opacity = max(.1, min(1., cfg.overlay_opacity))
                cfg.frame_diff_threshold = max(0., min(255., cfg.frame_diff_threshold))
                if cfg.roi is not None and not (isinstance(cfg.roi, list) and len(cfg.roi) == 4
                        and all(type(n) is int for n in cfg.roi) and cfg.roi[2] > 0 and cfg.roi[3] > 0):
                    cfg.roi = None
                if stored_secret and not stored_secret.startswith(_SECRET_PREFIX):
                    try:
                        cfg.save()
                    except Exception as exc:
                        raise CredentialProtectionError("DeepL anahtarı güvenli biçimde taşınamadı") from exc
                return cfg
            except CredentialProtectionError:
                raise
            except Exception:
                pass
        cfg = cls()
        cfg.save()
        return cfg


def load_glossary() -> dict[str, str]:
    if not GLOSSARY_PATH.exists():
        try:
            GLOSSARY_PATH.write_text(
                json.dumps(DEFAULT_GLOSSARY, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass
        return dict(DEFAULT_GLOSSARY)
    try:
        user_glossary = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))
        merged = dict(DEFAULT_GLOSSARY)
        merged.update(user_glossary)
        return merged
    except Exception:
        return dict(DEFAULT_GLOSSARY)
