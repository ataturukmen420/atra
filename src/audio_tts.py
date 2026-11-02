"""
ATA Game Translator — Turkish Neural TTS (Sesli Okuma) &
WASAPI Game Audio Ducking (Konuşurken Oyun Sesini Otomatik Kısma)
With Offline Windows SAPI Fallback when internet is disconnected.
"""
from __future__ import annotations

import asyncio
import ctypes
import os
import queue
import tempfile
import threading
import time
from pathlib import Path

import ctranslate2  # noqa: F401
import sentencepiece  # noqa: F401

# pycaw imports comtypes: import it once on the main thread, before workers exist.
try:
    from pycaw.pycaw import AudioUtilities as _AudioUtilities
except ImportError:
    _AudioUtilities = None

from .config import AppConfig

winmm = ctypes.windll.winmm


def _play_mp3_blocking(mp3_path: str, stop_event=None) -> None:
    alias = f"atatts_{int(time.time() * 1000) % 100000}"
    buf = ctypes.create_unicode_buffer(256)
    cmd_open = f'open "{mp3_path}" type mpegvideo alias {alias}'
    if winmm.mciSendStringW(cmd_open, buf, 255, 0) != 0:
        return
    try:
        winmm.mciSendStringW(f"play {alias}", buf, 255, 0)
        while stop_event is None or not stop_event.is_set():
            winmm.mciSendStringW(f"status {alias} mode", buf, 255, 0)
            if buf.value != "playing":
                break
            time.sleep(.05)
    finally:
        winmm.mciSendStringW(f"close {alias}", buf, 255, 0)


def _speak_offline_sapi_blocking(text: str, stop_event=None) -> None:
    """Offline fallback using Windows SAPI SpVoice when no internet connection is available."""
    try:
        import win32com.client

        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Rate = 1
        speaker.Speak(text, 1)
        while not speaker.WaitUntilDone(50):
            if stop_event is not None and stop_event.is_set():
                speaker.Speak("", 3)
                break
    except Exception:
        pass


class AudioDuckingController:
    """
    Lowers background game audio sessions via Windows Core Audio (WASAPI / pycaw)
    while Turkish TTS is speaking, and restores original volumes afterwards.
    """

    def __init__(self) -> None:
        self._saved_volumes: list[tuple[object, float]] = []
        self._lock = threading.Lock()

    def duck(self, duck_ratio: float = 0.25) -> None:
        with self._lock:
            try:
                my_pid = os.getpid()
                sessions = _AudioUtilities.GetAllSessions() if _AudioUtilities else []
                for session in sessions:
                    if not session.Process or session.Process.pid == my_pid:
                        continue
                    vol = session.SimpleAudioVolume
                    if vol is None:
                        continue
                    pid = session.Process.pid
                    orig = float(vol.GetMasterVolume())
                    if orig > 0.05:
                        # Multiple sessions from one PID can have different volumes.
                        self._saved_volumes.append((vol, orig))
                        vol.SetMasterVolume(min(orig, max(0.05, min(1.0, duck_ratio))), None)
            except Exception:
                pass

    def restore(self) -> None:
        with self._lock:
            if not self._saved_volumes:
                return
            try:
                for volume, original in self._saved_volumes:
                    try:
                        volume.SetMasterVolume(original, None)
                    except Exception:
                        continue
            except Exception:
                pass
            finally:
                self._saved_volumes.clear()


class TurkishTTSWorker:
    """
    Background worker that speaks newly translated dialogue subtitles in Turkish
    using Microsoft Edge Neural TTS (or Offline Windows SAPI fallback)
    with automatic WASAPI game audio ducking.
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._queue: queue.Queue[str] = queue.Queue(maxsize=3)
        self._last_spoken: str = ""
        self._ducker = AudioDuckingController()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def enqueue(self, text: str) -> None:
        if not self.config.tts_enabled:
            return
        cleaned = text.strip()
        if not cleaned or len(cleaned) < 3 or cleaned == self._last_spoken:
            return
        self._last_spoken = cleaned
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        try:
            self._queue.put_nowait(cleaned)
        except queue.Full:
            pass

    async def _synthesize_edge_tts(self, text: str, out_path: str) -> bool:
        try:
            import edge_tts

            communicate = edge_tts.Communicate(text, self.config.tts_voice, rate="+8%")
            await asyncio.wait_for(communicate.save(out_path), timeout=10.0)
            return os.path.exists(out_path) and os.path.getsize(out_path) > 256
        except Exception:
            return False

    def _run_loop(self) -> None:
        com_initialized = False
        try:
            result = ctypes.windll.ole32.CoInitialize(None)
            com_initialized = result in (0, 1)
        except Exception:
            pass

        tmp_dir = Path(tempfile.mkdtemp(prefix=f"ata_tts_{os.getpid()}_"))
        counter = 0

        try:
            while not self._stop_event.is_set():
                try:
                    text = self._queue.get(timeout=0.3)
                except queue.Empty:
                    continue

                if not self.config.tts_enabled:
                    continue

                counter += 1
                mp3_file = str(tmp_dir / f"speech_{counter % 6}.mp3")
                ok = asyncio.run(self._synthesize_edge_tts(text, mp3_file))
                if self._stop_event.is_set() or not self.config.tts_enabled:
                    Path(mp3_file).unlink(missing_ok=True)
                    continue

                try:
                    if self.config.audio_ducking_enabled:
                        self._ducker.duck(self.config.audio_ducking_volume)
                    if ok:
                        _play_mp3_blocking(mp3_file, self._stop_event)
                    else:
                        _speak_offline_sapi_blocking(text, self._stop_event)
                finally:
                    self._ducker.restore()
                    try:
                        Path(mp3_file).unlink(missing_ok=True)
                    except OSError:
                        pass
        finally:
            self._ducker.restore()
            for partial in tmp_dir.glob("speech_*.mp3"):
                try:
                    partial.unlink()
                except OSError:
                    pass
            try:
                tmp_dir.rmdir()
            except OSError:
                pass
            if com_initialized:
                try:
                    ctypes.windll.ole32.CoUninitialize()
                except Exception:
                    pass

    def shutdown(self) -> None:
        self._stop_event.set()
