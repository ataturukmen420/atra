"""
ATA Game Translator — Multi-Backend Game Translation Engine
Supports:
  1. 100% Offline Local Neural Model (CTranslate2 + SentencePiece Opus-MT-Big EN->TR)
     with Sentence-Boundary Splitting for multi-sentence paragraph accuracy
  2. Fast Cloud Neural GTX Engine
  3. DeepL API (Free & Pro)
  4. Local Ollama LLM
Plus Multi-Word & Sentence-Start Proper Noun protection, Keybind protection,
85-Term Game Glossary, and Thread-Safe SQLite Cache.
"""
from __future__ import annotations

import re
import json
import logging
import hashlib
import os
import shutil
import sqlite3
import threading
from concurrent.futures import CancelledError
from contextlib import closing
from pathlib import Path
from typing import Union

import ctranslate2
import requests
import sentencepiece as spm

from .config import BASE_DIR, CACHE_DB_PATH, LEGACY_CACHE_DB_PATH, USER_DATA_DIR, AppConfig, load_glossary
from .ocr_engine import TextBlock, is_turkish_text, register_known_turkish_translation
from .model_manifest import FILES as MODEL_FILES, REVISION as MODEL_REVISION

_BUNDLED_MODEL_DIR = BASE_DIR / "models" / "opus-mt-en-tr-ct2"
_MANAGED_MODEL_DIR = (Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
                      / "Atra" / "models" / "opus-en-tr" / MODEL_REVISION)
_REQUIRED_MODEL_FILES = ("model.bin", "source.spm", "target.spm", "config.json", "shared_vocabulary.json")
OFFLINE_MODEL_DIR = _BUNDLED_MODEL_DIR if all((_BUNDLED_MODEL_DIR / n).is_file() for n in _REQUIRED_MODEL_FILES) else _MANAGED_MODEL_DIR

_PREFIX_COLON_RE = re.compile(r"^([A-ZÇĞİÖŞÜ][A-Za-z0-9_'\-\s]{1,26}):\s+(.+)$")
_SPEAKER_BRACKET_RE = re.compile(r"^(\[[A-Za-z0-9_'\-\s]{2,24}\])\s+(.+)$")
_KEYBIND_RE = re.compile(r"(\[[A-Z0-9+\-]{1,10}\]|<[A-Z0-9+\-]{1,10}>)")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_UI_COLON_PREFIXES: dict[str, str] = {
    "main quest": "Ana Görev",
    "side quest": "Yan Görev",
    "quest": "Görev",
    "new quest": "Yeni Görev",
    "quest updated": "Görev Güncellendi",
    "quest completed": "Görev Tamamlandı",
    "objective": "Hedef",
    "new objective": "Yeni Hedef",
    "optional": "İsteğe Bağlı",
    "mission": "Görev",
    "chapter": "Bölüm",
    "episode": "Bölüm",
    "location": "Konum",
    "region": "Bölge",
    "tip": "İpucu",
    "hint": "İpucu",
    "tutorial": "Rehber",
    "warning": "Uyarı",
    "note": "Not",
    "error": "Hata",
    "reward": "Ödül",
    "requires": "Gereksinim",
    "prerequisite": "Ön Koşul",
    "effect": "Etki",
    "bonus": "Bonus",
}

# Multi-word and iconic game proper nouns locked regardless of sentence position (even at index 0)
_KNOWN_PROPER_NOUNS = [
    "Night City",
    "Los Santos",
    "San Andreas",
    "Vice City",
    "Liberty City",
    "New Vegas",
    "Baldur's Gate",
    "King's Landing",
    "Kaer Morhen",
    "White Orchard",
    "Arthur Morgan",
    "Johnny Silverhand",
    "John Marston",
    "Blackwater",
    "Silverhand",
    "Geralt",
    "Rivia",
    "Novigrad",
    "Yennefer",
    "Triss",
    "Ciri",
    "Vesemir",
    "Dutch",
    "Pinkertons",
    "Arasaka",
    "Militech",
    "Skyrim",
    "Whiterun",
    "Tamriel",
    "Winterfell",
    "Mordor",
    "Gondor",
]

_KNOWN_PROPER_PATTERNS = [
    (name, re.compile(rf"\b{re.escape(name)}\b")) for name in sorted(_KNOWN_PROPER_NOUNS, key=len, reverse=True)
]

_COMMON_CAP_WORDS = {
    "The", "A", "An", "In", "On", "At", "To", "From", "By", "With", "Of", "For",
    "And", "Or", "But", "If", "When", "Where", "Why", "How", "What", "Who", "Which",
    "This", "That", "These", "Those", "My", "Your", "His", "Her", "Our", "Their",
    "I", "You", "He", "She", "It", "We", "They", "Me", "Him", "Us", "Them",
    "Is", "Are", "Was", "Were", "Be", "Been", "Have", "Has", "Had", "Do", "Does", "Did",
    "Will", "Would", "Shall", "Should", "Can", "Could", "May", "Might", "Must",
    "Press", "Hold", "Click", "Select", "Open", "Close", "Use", "Talk", "Speak",
    "Find", "Go", "Return", "Kill", "Defeat", "Collect", "Search", "Follow",
    "New", "Load", "Save", "Game", "Settings", "Options", "Quit", "Exit", "Back",
    "Start", "Continue", "Main", "Quest", "Side", "Mission", "Objective", "Chapter",
    "Health", "Stamina", "Mana", "Level", "Skill", "Inventory", "Map", "Journal",
    "Yes", "No", "Cancel", "Confirm", "Apply", "Reset", "Audio", "Video", "Graphics",
    "Ancient", "Runed", "Greatsword", "Sword", "Shield", "Armor", "Potion", "Night",
    "Vision", "Dark", "Light", "Silver", "Gold", "Iron", "Steel", "Shadow", "Shadows",
    "Over", "Under", "Behind", "Before", "After", "Whispering", "Woods", "Forest",
    "City", "Town", "Village", "Tavern", "Camp", "Cave", "Waterfall", "Chest",
    "Critical", "Strike", "Damage", "Undead", "Enemy", "Enemies", "Player", "Monster",
    "Security", "Terminal", "Camera", "Cameras", "Control", "Room", "Optical", "Scanner",
    "Heist", "Wake", "Burn", "Samurai", "Tracks", "Nearby", "Midnight", "Nightfall",
    "Sixty", "Seconds", "Percent", "Increases", "Allows", "Reveals", "Disable", "Hold",
    "Watch", "Look", "Listen", "Wait", "Stop", "Run", "Jump", "Crouch", "Attack",
    "Defend", "Heal", "Rest", "Sleep", "Fast", "Travel", "World", "Character",
}


def extract_speaker_or_prefix(text: str) -> tuple[str, str]:
    stripped = text.strip()
    m1 = _PREFIX_COLON_RE.match(stripped)
    if m1:
        raw_prefix = m1.group(1).strip()
        body = m1.group(2).strip()
        ui_tr = _UI_COLON_PREFIXES.get(raw_prefix.lower())
        if ui_tr:
            return ui_tr, body
        return raw_prefix, body

    m2 = _SPEAKER_BRACKET_RE.match(stripped)
    if m2:
        return m2.group(1).strip(), m2.group(2).strip()

    return "", stripped


PlaceholderValue = Union[str, tuple[str, str]]


def protect_entities(text: str, preserve_proper_nouns: bool = True) -> tuple[str, dict[str, PlaceholderValue]]:
    """
    1. Replaces keybinds [E], [SPACE], [F] with single-letter key stand-in 'K'
       so Opus-MT treats them as keyboard keys ("K tuşuna basın").
    2. Locks multi-word & single-word Proper Nouns (Night City, Blackwater, Geralt, Dutch)
       even at index 0, plus dynamic mid-sentence proper nouns.
    """
    placeholders: dict[str, PlaceholderValue] = {}
    counter = 0

    def _sub_token(val: str) -> str:
        nonlocal counter
        token = f"ZXQ{counter}QXZ"
        counter += 1
        placeholders[token] = val
        return token

    kb_counter = 0

    def _sub_keybind(match: re.Match[str]) -> str:
        nonlocal kb_counter
        bracketed = match.group(0)
        standin = ["K", "J", "Z"][kb_counter % 3]
        placeholders[f"__KB_{kb_counter}__"] = (standin, bracketed)
        kb_counter += 1
        return standin

    protected = _KEYBIND_RE.sub(_sub_keybind, text)

    if preserve_proper_nouns:
        # Step A: Lock known multi-word & single-word proper nouns at ANY position (including index 0)
        for name, pat in _KNOWN_PROPER_PATTERNS:
            if pat.search(protected):
                protected = pat.sub(lambda m: _sub_token(m.group(0)), protected)

        # Step B: Dynamic mid-sentence Proper Noun detection & Title-Case normalization
        words = protected.split(" ")
        if len(words) >= 2 and not protected.isupper():
            cap_count = sum(1 for w in words if w and w[0].isupper())
            is_title_case = (cap_count / len(words)) > 0.65
            new_words: list[str] = []
            for i, cur_w in enumerate(words):
                clean_w = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", cur_w)
                if clean_w.startswith("ZXQ") and clean_w.endswith("QXZ"):
                    new_words.append(cur_w)
                    continue
                if i == 0:
                    # Check if first word is an unknown proper noun followed by a comma or verb
                    if (
                        len(clean_w) >= 4
                        and clean_w[0].isupper()
                        and not clean_w.isupper()
                        and clean_w not in _COMMON_CAP_WORDS
                        and cur_w.endswith(",")
                    ):
                        prefix = cur_w[: cur_w.find(clean_w)]
                        suffix = cur_w[cur_w.find(clean_w) + len(clean_w) :]
                        new_words.append(f"{prefix}{_sub_token(clean_w)}{suffix}")
                    else:
                        new_words.append(cur_w)
                    continue

                prev_w = words[i - 1]
                prev_ended_sentence = bool(prev_w and prev_w[-1] in ".!?:\"'")
                if (
                    not prev_ended_sentence
                    and len(clean_w) >= 3
                    and clean_w[0].isupper()
                    and not clean_w.isupper()
                ):
                    if clean_w not in _COMMON_CAP_WORDS:
                        prefix = cur_w[: cur_w.find(clean_w)]
                        suffix = cur_w[cur_w.find(clean_w) + len(clean_w) :]
                        new_words.append(f"{prefix}{_sub_token(clean_w)}{suffix}")
                    elif is_title_case:
                        new_words.append(cur_w.lower())
                    else:
                        new_words.append(cur_w)
                else:
                    new_words.append(cur_w)
            protected = " ".join(new_words)

    return protected, placeholders


def restore_entities(translated: str, placeholders: dict[str, PlaceholderValue]) -> str:
    result = translated
    for token, original in placeholders.items():
        if token.startswith("__KB_") and isinstance(original, tuple):
            standin, bracketed = original
            result = re.sub(
                rf"\b{re.escape(standin)}'yi tutun\b",
                f"{bracketed} tuşuna basılı tutun",
                result,
                flags=re.IGNORECASE,
            )
            result = re.sub(rf"\b{re.escape(standin)}\b", bracketed, result)
        else:
            result = re.sub(re.escape(token), str(original), result, flags=re.IGNORECASE)

    # Polish common RPG tooltip idioms
    result = re.sub(
        r"duvarlardan geçirir",
        "duvarların arkasından ortaya çıkarır",
        result,
        flags=re.IGNORECASE,
    )
    return result


class OfflineCTranslateEngine:
    """
    100% Offline English -> Turkish neural translator powered by CTranslate2 + SentencePiece
    (Helsinki-NLP/opus-mt-tc-big-en-tr) with Sentence-Boundary Splitting.
    """

    def __init__(self, model_dir: Path = OFFLINE_MODEL_DIR) -> None:
        self.model_dir = model_dir
        self._translator = None
        self._sp_src = None
        self._sp_tgt = None
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        return (
            (self.model_dir / "model.bin").exists()
            and (self.model_dir / "source.spm").exists()
            and (self.model_dir / "target.spm").exists()
            and (self.model_dir / "config.json").exists()
            and (self.model_dir / "shared_vocabulary.json").exists()
        )

    def warmup_async(self) -> None:
        if self.is_available():
            try:
                self._ensure_loaded()
            except Exception:
                logging.warning("Çevrimdışı model yüklenemedi; kurulum yeniden denenecek.")

    def _ensure_loaded(self) -> None:
        if self._translator is not None:
            return
        with self._lock:
            if self._translator is not None:
                return

            if self.model_dir == _MANAGED_MODEL_DIR:
                for name, (size, expected_hash) in MODEL_FILES.items():
                    path = self.model_dir / name
                    if not path.is_file() or path.stat().st_size != size:
                        raise RuntimeError("Çevrimdışı model dosyası eksik veya bozuk")
                    digest = hashlib.sha256()
                    with path.open("rb") as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                            digest.update(chunk)
                    if digest.hexdigest() != expected_hash:
                        raise RuntimeError("Çevrimdışı model doğrulanamadı")

            translator = ctranslate2.Translator(
                str(self.model_dir),
                device="cpu",
                compute_type="int8",
                inter_threads=2,
                intra_threads=4,
            )
            sp_src = spm.SentencePieceProcessor(str(self.model_dir / "source.spm"))
            sp_tgt = spm.SentencePieceProcessor(str(self.model_dir / "target.spm"))
            self._translator, self._sp_src, self._sp_tgt = translator, sp_src, sp_tgt

    def translate_batch(self, texts: list[str]) -> list[str]:
        if not texts:
            return []
        self._ensure_loaded()
        assert self._translator is not None and self._sp_src is not None and self._sp_tgt is not None

        flat_sentences: list[str] = []
        block_map: list[list[int]] = []

        for t in texts:
            sents = [s.strip() for s in _SENTENCE_SPLIT_RE.split(t.strip()) if s.strip()]
            if not sents:
                sents = [t.strip()]
            indices: list[int] = []
            for s in sents:
                indices.append(len(flat_sentences))
                flat_sentences.append(s)
            block_map.append(indices)

        with self._lock:
            tokenized = [self._sp_src.encode(s, out_type=str) + ["</s>"] for s in flat_sentences]
            beam = 1 if len(tokenized) > 6 else 2
            results = self._translator.translate_batch(
                tokenized,
                beam_size=beam,
                max_decoding_length=128,
            )
            decoded_sents = [self._sp_tgt.decode(r.hypotheses[0]).strip() for r in results]

        final_outputs: list[str] = []
        for indices in block_map:
            joined = " ".join(decoded_sents[i] for i in indices if i < len(decoded_sents))
            final_outputs.append(joined.strip())
        return final_outputs


_SHARED_OFFLINE_ENGINE = OfflineCTranslateEngine()
_SHARED_OFFLINE_ENGINE.warmup_async()
_SHARED_OFFLINE_LOCK = threading.Lock()


def get_shared_offline_engine() -> OfflineCTranslateEngine:
    global _SHARED_OFFLINE_ENGINE
    if _SHARED_OFFLINE_ENGINE is not None:
        return _SHARED_OFFLINE_ENGINE
    with _SHARED_OFFLINE_LOCK:
        if _SHARED_OFFLINE_ENGINE is None:
            _SHARED_OFFLINE_ENGINE = OfflineCTranslateEngine()
        return _SHARED_OFFLINE_ENGINE


class GameTranslator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.cancel_check = lambda: False
        self.glossary = load_glossary()
        self._glossary_lower = {k.strip().lower(): v for k, v in self.glossary.items()}
        for tr_val in self.glossary.values():
            register_known_turkish_translation(tr_val)
        self._mem_cache: dict[tuple[str, str], str] = {}
        self._lock = threading.Lock()
        self._offline_engine = get_shared_offline_engine()
        self._offline_engine.warmup_async()
        self._init_db()

    def _init_db(self) -> None:
        try:
            db_path = Path(CACHE_DB_PATH)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            is_default_db = db_path == USER_DATA_DIR / "translation_cache.sqlite3"
            if is_default_db and not db_path.exists() and LEGACY_CACHE_DB_PATH.is_file():
                try:
                    shutil.copy2(LEGACY_CACHE_DB_PATH, db_path)
                except OSError:
                    pass
            with closing(sqlite3.connect(db_path)) as conn, conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS translations_v2 (
                        scope TEXT NOT NULL,
                        src_text TEXT NOT NULL,
                        dst_text TEXT NOT NULL,
                        PRIMARY KEY (scope, src_text)
                    )
                    """
                )
                if is_default_db and LEGACY_CACHE_DB_PATH.is_file() and LEGACY_CACHE_DB_PATH != db_path:
                    try:
                        with closing(sqlite3.connect(LEGACY_CACHE_DB_PATH)) as legacy_conn:
                            has_v2 = legacy_conn.execute(
                                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='translations_v2'"
                            ).fetchone()
                            if has_v2:
                                rows = legacy_conn.execute(
                                    "SELECT scope, src_text, dst_text FROM translations_v2"
                                ).fetchall()
                                if rows:
                                    conn.executemany(
                                        "INSERT OR IGNORE INTO translations_v2 (scope, src_text, dst_text) VALUES (?, ?, ?)",
                                        rows,
                                    )
                    except Exception:
                        pass
                cursor = conn.execute("SELECT scope, src_text, dst_text FROM translations_v2 ORDER BY rowid DESC LIMIT 4096")
                for scope, src, dst in cursor.fetchall():
                    if not dst.strip() or src.strip().casefold() == dst.strip().casefold():
                        continue
                    if src.strip().lower() not in self._glossary_lower and is_turkish_text(src):
                        continue
                    self._mem_cache[(scope, src)] = dst
                    register_known_turkish_translation(dst)
        except Exception:
            logging.exception("Unable to load translation cache")

    def clear_cache(self) -> None:
        with self._lock:
            self._mem_cache.clear()
            try:
                db_path = Path(CACHE_DB_PATH)
                if db_path.exists():
                    with closing(sqlite3.connect(db_path)) as conn, conn:
                        conn.execute("DELETE FROM translations_v2")
            except Exception:
                logging.exception("Unable to clear translation cache")

    def _cache_scope(self) -> str:
        cfg = self.config
        return json.dumps([cfg.translation_engine, cfg.source_lang, cfg.target_lang,
                           cfg.preserve_proper_nouns, cfg.ollama_url, cfg.ollama_model],
                          separators=(",", ":"))

    def _check_cancelled(self) -> None:
        if self.cancel_check():
            raise CancelledError("Superseded translation request")

    def _save_to_db(self, pairs: list[tuple[str, str]], engine: str) -> None:
        if not pairs:
            return
        try:
            with closing(sqlite3.connect(CACHE_DB_PATH)) as conn, conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO translations_v2 (src_text, dst_text, scope) VALUES (?, ?, ?)",
                    [(src, dst, engine) for src, dst in pairs],
                )
        except Exception:
            logging.exception("Unable to persist translation cache")

    def _translate_via_google(self, texts: list[str]) -> list[str]:
        self._check_cancelled()
        joined = "\n ||| \n".join(texts)
        resp = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={
                "client": "gtx",
                "sl": self.config.source_lang,
                "tl": self.config.target_lang,
                "dt": "t",
                "q": joined,
            },
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=3.5,
        )
        resp.raise_for_status()
        data = resp.json()
        full_tr = "".join(seg[0] for seg in data[0] if seg and seg[0])
        parts = [p.strip() for p in re.split(r"\s*\|\|\|\s*", full_tr)]
        if len(parts) == len(texts):
            return parts

        out: list[str] = []
        for t in texts:
            self._check_cancelled()
            r = requests.get(
                "https://translate.googleapis.com/translate_a/single",
                params={"client": "gtx", "sl": self.config.source_lang, "tl": self.config.target_lang, "dt": "t", "q": t},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=2.5,
            )
            r.raise_for_status()
            d = r.json()
            out.append("".join(seg[0] for seg in d[0] if seg and seg[0]).strip())
        return out

    def _translate_via_deepl(self, texts: list[str]) -> list[str]:
        self._check_cancelled()
        key = self.config.deepl_api_key.strip()
        if not key:
            raise ValueError("DeepL API anahtarı gerekli")
        host = "https://api-free.deepl.com" if key.endswith(":fx") else "https://api.deepl.com"
        resp = requests.post(
            f"{host}/v2/translate",
            headers={"Authorization": f"DeepL-Auth-Key {key}"},
            json={
                "text": texts,
                "source_lang": self.config.source_lang.upper(),
                "target_lang": self.config.target_lang.upper(),
            },
            timeout=4.0,
        )
        resp.raise_for_status()
        translations = resp.json().get("translations", [])
        return [item.get("text", "").strip() for item in translations]

    def _translate_via_ollama(self, texts: list[str]) -> list[str]:
        out: list[str] = []
        for t in texts:
            self._check_cancelled()
            prompt = (
                "You are a professional video game localization translator. "
                "Translate the following English game text into natural Turkish. "
                "Keep proper nouns and tokens like ZXQ0QXZ unchanged. Output ONLY the Turkish translation:\n"
                f"{t}"
            )
            resp = requests.post(
                self.config.ollama_url,
                json={"model": self.config.ollama_model, "prompt": prompt, "stream": False},
                timeout=6.0,
            )
            resp.raise_for_status()
            out.append(resp.json().get("response", "").strip())
        return out

    def _translate_via_offline_or_google(self, texts: list[str]) -> list[str]:
        self._check_cancelled()
        if not self._offline_engine.is_available():
            raise RuntimeError("Çevrimdışı çeviri modeli bulunamadı")
        return self._offline_engine.translate_batch(texts)

    @staticmethod
    def _format_with_speaker(speaker: str, translated_body: str) -> str:
        if not speaker:
            return translated_body
        if speaker.startswith("[") and speaker.endswith("]"):
            return f"{speaker} {translated_body}"
        return f"{speaker}: {translated_body}"

    def translate_blocks(self, blocks: list[TextBlock]) -> list[TextBlock]:
        if not blocks:
            return []

        with self._lock:
            scope = self._cache_scope()
            pending_indices: list[int] = []
            pending_protected: list[str] = []
            pending_placeholders: list[dict[str, PlaceholderValue]] = []
            pending_raw_bodies: list[str] = []

            for idx, blk in enumerate(blocks):
                direct_hit = self._glossary_lower.get(blk.text.strip().lower())
                if direct_hit:
                    blk.translated = direct_hit
                    register_known_turkish_translation(direct_hit)
                    continue

                if is_turkish_text(blk.text):
                    blk.translated = ""
                    continue

                speaker, body = extract_speaker_or_prefix(blk.text)
                blk.speaker = speaker

                if not body:
                    blk.translated = ""
                    continue

                glossary_hit = self._glossary_lower.get(body.lower())
                if glossary_hit:
                    blk.translated = self._format_with_speaker(speaker, glossary_hit)
                    register_known_turkish_translation(blk.translated)
                    continue

                if is_turkish_text(body):
                    blk.translated = ""
                    continue

                cached = self._mem_cache.get((scope, body))
                if cached:
                    blk.translated = self._format_with_speaker(speaker, cached)
                    register_known_turkish_translation(blk.translated)
                    continue

                prot_text, ph_map = protect_entities(body, self.config.preserve_proper_nouns)
                pending_indices.append(idx)
                pending_protected.append(prot_text)
                pending_placeholders.append(ph_map)
                pending_raw_bodies.append(body)

            if pending_protected:
                engine = self.config.translation_engine
                try:
                    self._check_cancelled()
                    if engine == "offline":
                        translated_list = self._translate_via_offline_or_google(pending_protected)
                    elif engine == "deepl":
                        translated_list = self._translate_via_deepl(pending_protected)
                    elif engine == "ollama":
                        translated_list = self._translate_via_ollama(pending_protected)
                    elif engine == "google":
                        translated_list = self._translate_via_google(pending_protected)
                    else:
                        raise ValueError("Geçersiz çeviri motoru")
                except CancelledError:
                    raise
                except requests.RequestException:
                    logging.warning("Translation request failed for backend %s", engine)
                    raise RuntimeError("Çeviri servisine erişilemedi") from None
                except Exception:
                    # A transport/model failure must remain retryable, never become a cache hit.
                    logging.exception("Translation backend failed: %s", engine)
                    raise

                self._check_cancelled()
                new_db_pairs: list[tuple[str, str]] = []
                for i, blk_idx in enumerate(pending_indices):
                    raw_tr = translated_list[i] if i < len(translated_list) else ""
                    restored = restore_entities(raw_tr, pending_placeholders[i]).strip()
                    orig_body = pending_raw_bodies[i]
                    if not restored or restored.casefold() == orig_body.strip().casefold():
                        blocks[blk_idx].translated = ""
                        continue
                    self._mem_cache[(scope, orig_body)] = restored
                    if len(self._mem_cache) > 4096:
                        self._mem_cache.pop(next(iter(self._mem_cache)))
                    new_db_pairs.append((orig_body, restored))

                    blk = blocks[blk_idx]
                    blk.translated = self._format_with_speaker(blk.speaker, restored)
                    register_known_turkish_translation(restored)
                    register_known_turkish_translation(blk.translated)

                self._save_to_db(new_db_pairs, scope)

        return blocks
