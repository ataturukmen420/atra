"""Atra desktop application: Studio presentation and preserved asynchronous runtime."""
from __future__ import annotations

import asyncio
import ctypes
import math
import logging
import os
import queue
import random
import sys
import threading
import time
from collections import deque
from concurrent.futures import CancelledError, ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Callable, Optional

# CRITICAL WINDOWS C++ DLL ORDER: Load ctranslate2 & sentencepiece before PyQt6 Qt6Core.dll
import ctranslate2  # noqa: F401
import sentencepiece  # noqa: F401

# Construct/load the single native engine before Qt loads any DLLs.
from src.translator import GameTranslator

from PyQt6.QtCore import (
    QPoint,
    QPointF,
    QRect,
    QRectF,
    Qt,
    QTimer,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QCursor,
    QFont,
    QIcon,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.audio_tts import TurkishTTSWorker
from src.config import AppConfig, LOG_PATH
from src.demo_scene import DemoGameWindow
from src.ocr_engine import ScreenOcrEngine, TextBlock, is_turkish_text
from src.overlay import GameOverlayWindow, RoiSelectorModal
from src.svg_medallions import (
    CryptographicScrambler,
    GlassMedallionWidget,
    SpringAnimator,
    draw_glass_medallion,
    render_duotone_svg,
)

user32 = ctypes.windll.user32
WDA_EXCLUDEFROMCAPTURE = 0x00000011

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"
LOGO_PNG_PATH = ASSETS_DIR / "app_logo.png"
ICON_ICO_PATH = ASSETS_DIR / "app_icon.ico"

VK_MAP = {
    "F8": 0x77,
    "F9": 0x78,
    "F10": 0x79,
    "F11": 0x7A,
    "F12": 0x7B,
}


from src.studio_ui import (
    StudioButton, StudioSegmentedBar, StudioToggleSwitch, StudioHeaderBanner,
    GlassCard, BentoTelemetryCockpit, StudioControlPanelWindow, _lerp_qcolor,
)
from src import brand
from src.model_setup import ModelProvisioner


class AtaGameTranslatorApp:
    FULL_W = 640
    FULL_H = 970
    MINI_H = 270

    def __init__(self, auto_demo: bool = False) -> None:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ATA.GameTranslator.Pro.v4")
        except Exception:
            pass

        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=str(LOG_PATH), level=logging.WARNING,
                            format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
        self._closing = False

        self.qapp = QApplication.instance() or QApplication(sys.argv)
        self.config = AppConfig.load()

        # Bind Commercial Application Icon to QApplication & Windows Taskbar
        self.app_icon = QIcon()
        if ICON_ICO_PATH.exists():
            self.app_icon.addFile(str(ICON_ICO_PATH))
        if LOGO_PNG_PATH.exists():
            self.app_icon.addFile(str(LOGO_PNG_PATH))
        if not self.app_icon.isNull():
            self.qapp.setWindowIcon(self.app_icon)

        self.win = StudioControlPanelWindow()
        self.win.on_close = self.shutdown
        if not self.app_icon.isNull():
            self.win.setWindowIcon(self.app_icon)
        self.win.setFixedSize(self.FULL_W, self.FULL_H)
        available = self.qapp.primaryScreen().availableGeometry()
        self.win.move(max(available.left(), available.right() - self.FULL_W - 24), available.top() + 24)

        self.ocr_engine = ScreenOcrEngine(lang=self.config.source_lang)
        self.translator = GameTranslator(replace(self.config))
        self.tts_worker = TurkishTTSWorker(self.config)
        self.overlay = GameOverlayWindow(self.win, self.config)

        self.live_active = False
        self._is_mini = False
        self._beam_angle = 0.0

        self._scan_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ata-scan")
        self._scan_busy = False
        self._scan_epoch = 0
        self._pending_forced_scan = False
        self._last_blocks: list[TextBlock] = []

        self._ui_queue: queue.Queue = queue.Queue(maxsize=1)
        self._error_queue: queue.Queue = queue.Queue(maxsize=1)
        self._empty_scan_count = 0
        self._empty_epoch = -1
        self._key_down_state: dict[str, bool] = {k: False for k in VK_MAP}
        self._demo_win: Optional[DemoGameWindow] = None
        self._demo_hwnd: Optional[int] = None
        self._demo_roi: Optional[list[int]] = None
        self._roi_modal: Optional[RoiSelectorModal] = None
        self._setup_active = False
        self._setup_token = -1
        self._model_setup = ModelProvisioner(self.win)

        self._build_ui()
        self._model_setup.progress.connect(self._on_setup_progress)
        self._model_setup.ready.connect(self._on_setup_ready)
        self._model_setup.failed.connect(self._on_setup_failed)
        self.win.show()

        self.hwnd = int(self.win.winId())
        user32.SetWindowDisplayAffinity(self.hwnd, WDA_EXCLUDEFROMCAPTURE)

        self.root = self.win

        self._hdr_timer = QTimer(self.win)
        self._hdr_timer.timeout.connect(self._tick_visual_shaders)
        self._hdr_timer.start(250)

        self._hk_timer = QTimer(self.win)
        self._hk_timer.timeout.connect(self._poll_hotkeys)
        self._hk_timer.start(40)

        self._queue_timer = QTimer(self.win)
        self._queue_timer.timeout.connect(self._process_ui_queue)
        self._queue_timer.start(25)

        self._live_timer = QTimer(self.win)
        self._live_timer.timeout.connect(self._live_loop_tick)
        self._live_timer.start(max(240, int(self.config.scan_interval_ms)))

        # Watch source files for live hot-reload if code is updated while app is open
        self._watched_files = list((ROOT_DIR / "src").glob("*.py"))
        self._file_mtimes = {p: p.stat().st_mtime for p in self._watched_files if p.exists()}
        self._reload_timer = QTimer(self.win)
        self._reload_timer.timeout.connect(self._check_hot_reload)
        # Hot reload is explicitly opt-in; replacing the process loses live state.
        if os.environ.get("ATA_DEV_RELOAD") == "1":
            self._reload_timer.start(1500)
        self.qapp.aboutToQuit.connect(self.shutdown)

        if auto_demo:
            QTimer.singleShot(120, self.open_demo_scene)
        QTimer.singleShot(0, self._setup_initial_engine)

    def _check_hot_reload(self) -> None:
        try:
            for p, old_mt in self._file_mtimes.items():
                if p.exists() and p.stat().st_mtime > old_mt + 0.5:
                    os.execl(sys.executable, sys.executable, *sys.argv)
        except Exception:
            pass

    def _tick_visual_shaders(self) -> None:
        # Static surfaces are repainted only on input or new telemetry.
        if self.header.live_active != self.live_active:
            self.header.tick_animation(self.live_active)


    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self.win)
        main_layout.setContentsMargins(20, 12, 20, 20)
        main_layout.setSpacing(12)
        self.header = StudioHeaderBanner(self.win, self.toggle_mini_hud, self.shutdown,
                                         on_sim=self.toggle_demo_scene)
        main_layout.addWidget(self.header)

        def label(value, size=12, color="#ACADB7", bold=False):
            widget = QLabel(value)
            widget.setStyleSheet(f"color:{color}; font-family:'Segoe UI Variable Text'; font-size:{size}px; font-weight:{600 if bold else 400}; background:transparent; border:none;")
            return widget

        self.card1 = GlassCard(self.win, is_hero=True)
        commands = QVBoxLayout(self.card1)
        commands.setContentsMargins(18, 15, 18, 17)
        commands.setSpacing(10)
        self.telemetry_cockpit = BentoTelemetryCockpit(self.card1)
        commands.addWidget(self.telemetry_cockpit)
        self.status_lbl = QLabel("Hazır"); self.status_lbl.hide()
        self.perf_lbl = QLabel("OFFLINE"); self.perf_lbl.hide()
        self.block_badge = QLabel("0 BLOK"); self.block_badge.hide()
        self.btn_live = StudioButton("Çeviriyi başlat", self.toggle_live,
            subtitle="", kbd_tag="F8", icon="play",
            is_hero=True, accent_hex="#FFFFFF", top_idle="#2867DC", bot_idle="#2056C5",
            border_idle="#407CEB", top_hover="#2C6CDD", bot_hover="#245FCE",
            border_hover="#6897F0", height=58, font_px=16, radius=12)
        commands.addWidget(self.btn_live)
        grid = QGridLayout(); grid.setSpacing(10)
        self.btn_once = StudioButton("Anlık çeviri", lambda: self.trigger_single_scan(force=True),
            subtitle="", kbd_tag="F9", icon="bolt", height=52)
        self.btn_roi = StudioButton("Çeviri alanı", self.open_roi_selector,
            subtitle="", kbd_tag="F10", icon="reticle", height=52)
        self.btn_demo = StudioButton("Simülatör", self.toggle_demo_scene,
            subtitle="", kbd_tag="SIM", icon="gamepad", height=52)
        self.btn_clear = StudioButton("Temizle", self.clear_overlay,
            subtitle="", kbd_tag="CLR", icon="sweep", height=52)
        for index, button in enumerate((self.btn_once,self.btn_roi,self.btn_demo,self.btn_clear)):
            grid.addWidget(button,index//2,index%2)
        commands.addLayout(grid)
        main_layout.addWidget(self.card1)

        self.body_widget = QWidget(self.win)
        body = QVBoxLayout(self.body_widget)
        body.setContentsMargins(0,0,0,0); body.setSpacing(12)
        self.card2 = GlassCard(self.body_widget)
        settings = QVBoxLayout(self.card2)
        settings.setContentsMargins(18,14,18,14); settings.setSpacing(8)
        mode_title = QHBoxLayout()
        mode_title.addWidget(label("Çeviri görünümü",12,bold=True))
        mode_title.addStretch(); mode_title.addWidget(label("F11",10,"#9396A3"))
        settings.addLayout(mode_title)
        self.mode_seg = StudioSegmentedBar([
            ("inplace","Yerinde çeviri","pin"), ("subtitle","Sinematik altyazı","cinema")],
            self.config.display_mode,self._on_mode_selected,height=40)
        settings.addWidget(self.mode_seg)
        settings.addSpacing(3)
        settings.addWidget(label("Çeviri motoru",12,bold=True))
        self.engine_seg = StudioSegmentedBar([
            ("offline","Çevrimdışı","cpu"),("google","Google","bolt"),
            ("deepl","DeepL","diamond"),("ollama","Ollama","terminal")],
            self.config.translation_engine,self._on_engine_selected,height=40)
        settings.addWidget(self.engine_seg)
        setup_row = QHBoxLayout()
        self.setup_lbl = label("",11,"#B5C9F2")
        self.setup_lbl.setWordWrap(True)
        self.setup_lbl.hide()
        setup_row.addWidget(self.setup_lbl,1)
        self.setup_retry = QPushButton("Yeniden dene")
        self.setup_retry.setStyleSheet("QPushButton {color:#DCE8FF; background:#34363D; border:1px solid #50535D; border-radius:6px; padding:4px 9px; font-size:11px;} QPushButton:hover {background:#424650;}")
        self.setup_retry.clicked.connect(lambda: self._begin_model_setup(self.config.translation_engine))
        self.setup_retry.hide()
        setup_row.addWidget(self.setup_retry)
        settings.addLayout(setup_row)
        privacy_notice = label("Google, DeepL ve seslendirme metni internete gönderir.", 11, "#B5B8C4")
        privacy_notice.setWordWrap(True)
        settings.addWidget(privacy_notice)
        self.deepl_panel = QWidget()
        deepl_row = QHBoxLayout(self.deepl_panel); deepl_row.setContentsMargins(0,2,0,2)
        deepl_row.addWidget(label("DeepL anahtarı",12))
        self.deepl_input = QLineEdit(self.config.deepl_api_key)
        self.deepl_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.deepl_input.setAccessibleName("DeepL API anahtarı")
        self.deepl_input.setPlaceholderText("API anahtarınızı girin")
        self.deepl_input.setStyleSheet("QLineEdit { background:#18191D; color:#F5F5F7; border:1px solid #41434B; border-radius:8px; padding:7px 10px; font-family:'Segoe UI Variable Text'; font-size:12px; } QLineEdit:focus {border-color:#7BA8FF;}")
        self.deepl_input.editingFinished.connect(self._save_settings)
        deepl_row.addWidget(self.deepl_input,1)
        settings.addWidget(self.deepl_panel)
        self.deepl_panel.setVisible(self.config.translation_engine=="deepl")
        settings.addSpacing(3)
        def toggle_row(icon, title, switch, shortcut=""):
            row = QWidget(); layout = QHBoxLayout(row)
            layout.setContentsMargins(0,3,0,3); layout.setSpacing(10)
            row.setMinimumHeight(38)
            layout.addWidget(GlassMedallionWidget(icon,accent_hex="#BCC1CF",size=26))
            layout.addWidget(label(title,13,"#E7E8EE"),1)
            if shortcut: layout.addWidget(label(shortcut,10,"#9396A3"))
            layout.addWidget(switch)
            settings.addWidget(row)
        self.sw_proper = StudioToggleSwitch(self.config.preserve_proper_nouns,self._on_proper_toggled)
        self.sw_proper.setAccessibleName("Karakter ve yer adlarını koru")
        toggle_row("shield","Karakter ve yer adlarını koru",self.sw_proper)
        self.sw_tts = StudioToggleSwitch(self.config.tts_enabled,self._on_tts_toggled)
        self.sw_tts.setAccessibleName("Türkçe seslendirme")
        toggle_row("wave","Türkçe seslendirme",self.sw_tts,"F12")
        self.roi_lbl = label(self._format_roi_text(),11,"#9396A3")
        self.roi_lbl.setMinimumHeight(25)
        settings.addWidget(self.roi_lbl)
        body.addWidget(self.card2)

        self.card3 = GlassCard(self.body_widget)
        history = QVBoxLayout(self.card3)
        history.setContentsMargins(18,14,18,13); history.setSpacing(10)
        history_title=QHBoxLayout()
        history_title.addWidget(label("Son çeviriler",12,bold=True)); history_title.addStretch()
        self.btn_purge_cache = QPushButton("Önbelleği sıfırla")
        self.btn_purge_cache.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_purge_cache.setFixedHeight(22)
        self.btn_purge_cache.setStyleSheet("QPushButton {color:#9396A3; background:transparent; border:1px solid #3A3D46; border-radius:5px; padding:0 8px; font-family:'Segoe UI Variable Text'; font-size:10px;} QPushButton:hover {color:#F5F5F7; background:#34363D; border-color:#50535D;} QPushButton:focus {border-color:#7BA8FF;}")
        self.btn_purge_cache.clicked.connect(self.clear_user_history)
        history_title.addWidget(self.btn_purge_cache)
        history_title.addSpacing(6)
        history_title.addWidget(label("EN  →  TR",10,"#9396A3"))
        history.addLayout(history_title)
        self.feed_box = QTextEdit()
        self.feed_box.setReadOnly(True)
        self.feed_box.setAccessibleName("Son İngilizce ve Türkçe çeviriler")
        self.feed_box.setPlaceholderText("Çevrilen oyun metinleri burada görünecek.")
        self.feed_box.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.feed_box.setStyleSheet("QTextEdit { background:transparent; color:#F5F5F7; border:none; padding:0; font-family:'Segoe UI Variable Text'; font-size:13px; } QScrollBar:vertical {background:transparent; width:5px; margin:0;} QScrollBar::handle:vertical {background:#555861; border-radius:2px; min-height:28px;} QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;} QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical {background:transparent;}")
        history.addWidget(self.feed_box,1)
        body.addWidget(self.card3,1)
        main_layout.addWidget(self.body_widget,1)


    def clear_user_history(self) -> None:
        self.translator.clear_cache()
        self.clear_overlay()
        self.feed_box.clear()
        try:
            if LOG_PATH.exists():
                LOG_PATH.write_text("", encoding="utf-8")
        except OSError:
            pass
        self.telemetry_cockpit.set_status("Önbellek ve geçmiş temizlendi", self.live_active)

    def clear_overlay(self) -> None:
        with self._scan_lock:
            self._scan_epoch += 1
            self._pending_forced_scan = False
        self._last_blocks = []
        self.overlay.clear()
        if self._is_demo_active() and self._demo_win is not None:
            self._demo_win.clear_translations()
        self.block_badge.setText("0 BLOK")
        self.telemetry_cockpit.push_telemetry(self.telemetry_cockpit.last_ms, self.config.translation_engine, 0)

    def _render_demo_instant(self) -> None:
        """Compatibility entrypoint: schedule the scene on the scan worker."""
        self.trigger_single_scan(force=True)


    def toggle_mini_hud(self) -> None:
        self._is_mini = not self._is_mini
        self.body_widget.setVisible(not self._is_mini)
        self.telemetry_cockpit.setVisible(not self._is_mini)
        for button in (self.btn_once,self.btn_roi,self.btn_demo,self.btn_clear):
            button.setVisible(not self._is_mini)
        if self._is_mini:
            self.card1.setFixedHeight(104)
            self.win.setFixedSize(self.FULL_W,self.MINI_H)
            self.header.mini_btn.text_str="Tam"
            self.header.mini_btn.setAccessibleName("Tam görünüm")
            self.header.mini_btn.setToolTip("Tam görünüme geç")
        else:
            self.card1.setMinimumHeight(0); self.card1.setMaximumHeight(16777215)
            self.win.setFixedSize(self.FULL_W,self.FULL_H)
            self.header.mini_btn.text_str="Kompakt"
            self.header.mini_btn.setAccessibleName("Kompakt görünüm")
            self.header.mini_btn.setToolTip("Kompakt görünüme geç")
        self.header.mini_btn.update()


    def _format_roi_text(self) -> str:
        if self._is_demo_active() and self._demo_roi:
            _,_,w,h=self._demo_roi
            return f"Yakalama alanı: Simülatör · {w} × {h}"
        if self.config.roi and len(self.config.roi)==4:
            _,_,w,h=self.config.roi
            return f"Yakalama alanı: Seçili bölge · {w} × {h}"
        return "Yakalama alanı: Ekranın tamamı · F10 ile bölge seçin"


    def _on_mode_selected(self, mode_key: str) -> None:
        self.config.display_mode = mode_key
        if self._last_blocks:
            if self._is_demo_active() and self._demo_win is not None:
                self._demo_win.set_translated_blocks(self._last_blocks, display_mode=mode_key)
                self.overlay.clear()
            else:
                self.overlay.render_blocks(self._last_blocks, active_roi=self._get_effective_roi())
        self._save_settings()

    def _on_engine_selected(self, eng_key: str) -> None:
        self.config.translation_engine = eng_key
        self.deepl_panel.setVisible(eng_key == "deepl")
        self.telemetry_cockpit.engine_name = eng_key.upper()
        self.telemetry_cockpit.update()
        self._begin_model_setup(eng_key)
        self._save_settings()

    def _setup_initial_engine(self) -> None:
        if not self._closing:
            self._begin_model_setup(self.config.translation_engine)

    def _begin_model_setup(self, engine: str) -> None:
        self._model_setup.cancel()
        self._setup_token = -1  # Ignore already-queued signals from a superseded setup.
        self._setup_active = False
        self.setup_retry.hide()
        if engine not in ('offline','ollama'):
            self.setup_lbl.hide()
            return
        if engine == 'offline' and self.translator._offline_engine._translator is not None:
            self.setup_lbl.hide()
            return
        with self._scan_lock:
            self._scan_epoch += 1
            self._pending_forced_scan = False
        self._setup_active = True
        self.setup_lbl.setText('Model kontrol ediliyor…')
        self.setup_lbl.show()
        self._setup_token = self._model_setup.start(engine,self.translator._offline_engine,
                                                    self.config.ollama_url,self.config.ollama_model)

    def _on_setup_progress(self, token: int, message: str) -> None:
        if token == self._setup_token and not self._closing:
            self.setup_lbl.setText(message)
            self.setup_lbl.show()

    def _on_setup_ready(self, token: int, engine: str, model: str) -> None:
        if token != self._setup_token or self._closing or self.config.translation_engine != engine:
            return
        self._setup_active = False
        if engine == 'ollama':
            self.config.ollama_model = model
        self.setup_lbl.setText(f'Yerel model hazır · {model}' if model else 'Çevrimdışı model hazır')
        self.setup_retry.hide()
        self._save_settings()

    def _on_setup_failed(self, token: int, message: str) -> None:
        if token != self._setup_token or self._closing:
            return
        # Keep live scans paused until retry succeeds or another engine is selected.
        self._setup_active = True
        self.setup_lbl.setText(message)
        self.setup_lbl.show()
        self.setup_retry.show()

    def _on_proper_toggled(self, val: bool) -> None:
        self.config.preserve_proper_nouns = val
        self._save_settings()

    def _on_tts_toggled(self, val: bool) -> None:
        self.config.tts_enabled = val
        self._save_settings()

    def _save_settings(self) -> None:
        self.config.deepl_api_key = self.deepl_input.text().strip()
        self.config.save()
        self.ocr_engine.reset_diff_gate()
        if self.live_active and not self._setup_active:
            self.trigger_single_scan(force=True)

    def _set_live_ui_state(self, active: bool) -> None:
        self.live_active=active
        self.header.tick_animation(active)
        self.status_lbl.setText("Canlı çeviri aktif" if active else "Duraklatıldı")
        self.telemetry_cockpit.set_status("Canlı çeviri" if active else "Duraklatıldı",active)
        if active:
            self.btn_live.set_palette(text="Çeviriyi duraklat",icon="pause",
                subtitle="",kbd_tag="F8",accent_hex="#FFFFFF",
                top_idle="#2867DC",bot_idle="#2056C5",border_idle="#407CEB",
                top_hover="#2C6CDD",bot_hover="#245FCE",border_hover="#6897F0")
        else:
            self.btn_live.set_palette(text="Çeviriyi başlat",icon="play",
                subtitle="",kbd_tag="F8",accent_hex="#FFFFFF",
                top_idle="#2867DC",bot_idle="#2056C5",border_idle="#407CEB",
                top_hover="#2C6CDD",bot_hover="#245FCE",border_hover="#6897F0")


    def toggle_live(self) -> None:
        self._set_live_ui_state(not self.live_active)
        if self.live_active:
            self.ocr_engine.reset_diff_gate()
            self.trigger_single_scan(force=True)
        else:
            with self._scan_lock:
                self._scan_epoch += 1
                self._pending_forced_scan = False
            self._last_blocks = []
            self.overlay.clear()
            if self._is_demo_active() and self._demo_win is not None:
                self._demo_win.clear_translations()

    def toggle_mode(self) -> None:
        new_mode = "subtitle" if self.config.display_mode == "inplace" else "inplace"
        self.config.display_mode = new_mode
        self.mode_seg.set_key(new_mode, animate=True)
        if self._last_blocks:
            if self._is_demo_active() and self._demo_win is not None:
                self._demo_win.set_translated_blocks(self._last_blocks, display_mode=new_mode)
                self.overlay.clear()
            else:
                self.overlay.render_blocks(self._last_blocks, active_roi=self._get_effective_roi())
        self._save_settings()

    def toggle_tts(self) -> None:
        new_val = not self.config.tts_enabled
        self.config.tts_enabled = new_val
        self.sw_tts.setChecked(new_val, animate=True)
        self._save_settings()

    def open_roi_selector(self) -> None:
        if self._is_demo_active() and self._demo_win is not None:
            self._demo_win.close()

        was_live = self.live_active
        self.live_active = False
        self._last_blocks = []
        with self._scan_lock:
            self._scan_epoch += 1
        self.overlay.clear()

        def _after_roi(roi: Optional[list[int]]) -> None:
            self._demo_roi = None
            self.config.roi = roi
            self.config.save()
            self.roi_lbl.setText(self._format_roi_text())
            self.ocr_engine.reset_diff_gate()
            self.overlay.draw_roi_indicator(active_roi=self._get_effective_roi())
            if was_live or roi is not None:
                if not self.live_active:
                    self.toggle_live()
                else:
                    self.trigger_single_scan(force=True)

        self._roi_modal = RoiSelectorModal(self.win, _after_roi)

    def _sync_demo_roi(self) -> None:
        if not self._is_demo_active() or self._demo_win is None:
            self._demo_roi = None
            self._demo_hwnd = None
            self.roi_lbl.setText(self._format_roi_text())
            return

        self._demo_hwnd = self._demo_win.hwnd
        new_roi = self._demo_win.get_canvas_screen_rect()
        if new_roi != self._demo_roi:
            self._demo_roi = new_roi
            self.roi_lbl.setText(self._format_roi_text())
            self.ocr_engine.reset_diff_gate()

    def toggle_demo_scene(self) -> None:
        if self._is_demo_active() and self._demo_win is not None:
            self._demo_win.close()
        else:
            self.open_demo_scene()

    def open_demo_scene(self) -> None:
        def _on_scene_switched() -> None:
            with self._scan_lock:
                self._scan_epoch += 1
            self._last_blocks = []
            self._sync_demo_roi()
            self.ocr_engine.reset_diff_gate()
            if not self.live_active:
                self._set_live_ui_state(True)
            self.trigger_single_scan(force=True)

        def _on_demo_closed() -> None:
            with self._scan_lock:
                self._scan_epoch += 1
            self._last_blocks = []
            self._demo_win = None
            self._demo_hwnd = None
            self._demo_roi = None
            self.btn_demo.set_palette(
                text="Simülatör",
                subtitle="",
                kbd_tag="SIM",
                accent_hex="#BCC1CF",
                icon="gamepad",
            )
            self.roi_lbl.setText(self._format_roi_text())
            self.overlay.clear()
            self.ocr_engine.reset_diff_gate()
            if self.live_active and not self.config.roi:
                self.toggle_live()
            elif self.live_active:
                self.trigger_single_scan(force=True)

        if self._is_demo_active() and self._demo_win is not None:
            self._demo_win.raise_()
        else:
            self._demo_win = DemoGameWindow(
                self.win,
                on_scene_change=_on_scene_switched,
                on_closed=_on_demo_closed,
            )
            if not self.app_icon.isNull():
                self._demo_win.setWindowIcon(self.app_icon)
            self.btn_demo.set_palette(
                text="Simülatörü kapat",
                subtitle="",
                kbd_tag="SIM",
                accent_hex="#BCC1CF",
                icon="gamepad",
                top_idle="#34363D",
                bot_idle="#2B2D33",
                top_hover="#3D4048",
                bot_hover="#33363D",
            )

        self._sync_demo_roi()
        self.overlay.clear()
        if not self.live_active:
            self._set_live_ui_state(True)
        self.trigger_single_scan(force=True)

    def _is_demo_active(self) -> bool:
        return bool(self._demo_win is not None and self._demo_win.isVisible())

    def _get_effective_roi(self) -> Optional[list[int]]:
        if self._is_demo_active():
            self._sync_demo_roi()
            return self._demo_roi
        return self.config.roi

    def _poll_hotkeys(self) -> None:
        try:
            for key_name, vk in VK_MAP.items():
                is_down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
                was_down = self._key_down_state[key_name]
                self._key_down_state[key_name] = is_down
                if is_down and not was_down:
                    if key_name == "F8":
                        self.toggle_live()
                    elif key_name == "F9":
                        self.trigger_single_scan(force=True)
                    elif key_name == "F10":
                        self.open_roi_selector()
                    elif key_name == "F11":
                        self.toggle_mode()
                    elif key_name == "F12":
                        self.toggle_tts()
        except Exception:
            pass

    def _live_loop_tick(self) -> None:
        if self.live_active and not self._scan_busy:
            self.trigger_single_scan(force=False)

    def trigger_single_scan(self, force: bool = False) -> None:
        if self._closing or self._setup_active:
            return

        with self._scan_lock:
            if force:
                self._scan_epoch += 1
            if self._scan_busy:
                if force:
                    self._pending_forced_scan = True
                return
            self._scan_busy = True
            self._pending_forced_scan = False
            scan_epoch = self._scan_epoch

        demo_snapshot: Optional[tuple[object, tuple[int, int, int, int]]] = None
        demo_fallback_blocks: Optional[list[TextBlock]] = None
        if self._is_demo_active() and self._demo_win is not None:
            self._sync_demo_roi()
            demo_snapshot = self._demo_win.capture_canvas_rgb()
            demo_fallback_blocks = self._demo_win.get_scene_blocks()

        fg_geo = self.win.frameGeometry()
        panel_rect = (fg_geo.x(), fg_geo.y(), fg_geo.width(), fg_geo.height())
        prev_blocks = list(self._last_blocks)

        effective_roi = self._get_effective_roi()
        snapshot = replace(self.config, roi=list(effective_roi) if effective_roi else None)
        self._executor.submit(self._worker_scan, scan_epoch, effective_roi, force,
                              demo_snapshot, demo_fallback_blocks, panel_rect, prev_blocks, snapshot)

    def _worker_scan(
        self,
        scan_epoch: int,
        roi: Optional[list[int]],
        force: bool,
        demo_snapshot: Optional[tuple[object, tuple[int, int, int, int]]],
        demo_fallback_blocks: Optional[list[TextBlock]],
        panel_rect: tuple[int, int, int, int],
        prev_blocks: list[TextBlock],
        scan_config: Optional[AppConfig] = None,
    ) -> None:
        t0 = time.perf_counter()
        cfg = scan_config or replace(self.config)
        com_result = ctypes.windll.ole32.CoInitializeEx(None, 0)
        try:
            with self._scan_lock:
                if scan_epoch != self._scan_epoch or self._closing:
                    return
            self.translator.config = cfg
            self.translator.cancel_check = lambda: self._closing or scan_epoch != self._scan_epoch
            if demo_snapshot is not None:
                rgb_arr, rect = demo_snapshot  # type: ignore[misc]
                if not force and not self.ocr_engine.has_frame_changed(
                    rgb_arr, rect, threshold=cfg.frame_diff_threshold  # type: ignore[arg-type]
                ):
                    return
                lx, ty, _, _ = rect
                try:
                    blocks = asyncio.run(self.ocr_engine.recognize_rgb_async(rgb_arr, offset_x=lx, offset_y=ty))  # type: ignore[arg-type]
                except Exception:
                    blocks = []
                # Use exact simulator HUD bounding boxes & exact background colors for 100% seamless rendering
                if demo_fallback_blocks:
                    blocks = list(demo_fallback_blocks)
            else:
                blocks = self.ocr_engine.scan_screen(
                    roi=roi,
                    force=force,
                    diff_threshold=cfg.frame_diff_threshold,
                    target_hwnd=None,
                )
                if blocks is None:
                    return

                px, py, pw, ph = panel_rect
                filtered: list[TextBlock] = []
                for b in blocks:
                    bcx = b.x + b.w * 0.5
                    bcy = b.y + b.h * 0.5
                    # 1. Exclude our own Control Panel window
                    if (px - 8) <= bcx <= (px + pw + 8) and (py - 8) <= bcy <= (py + ph + 8):
                        continue
                    # 2. If Turkish text is detected (including any Turkish overlay or Turkish UI), reject it
                    if is_turkish_text(b.text):
                        continue
                    filtered.append(b)
                blocks = filtered

            with self._scan_lock:
                if scan_epoch != self._scan_epoch:
                    return

            if blocks:
                self.translator.translate_blocks(blocks)
                blocks = [b for b in blocks if b.translated and not is_turkish_text(b.text)]

            # Hold through one transient empty OCR result, then clear disappeared text.
            # Unchanged frames return None above and retain the existing patch indefinitely.
            if self._empty_epoch != scan_epoch:
                self._empty_scan_count = 0
                self._empty_epoch = scan_epoch
            self._empty_scan_count = 0 if blocks else self._empty_scan_count + 1
            if demo_snapshot is None and not blocks and not force and self._empty_scan_count < 2:
                self.ocr_engine.reset_diff_gate()
                return

            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            with self._scan_lock:
                if scan_epoch == self._scan_epoch:
                    if self._ui_queue.full():
                        self._ui_queue.get_nowait()
                    self._ui_queue.put_nowait((scan_epoch, blocks, elapsed_ms, cfg.translation_engine))
        except CancelledError:
            pass
        except Exception as exc:
            logging.exception("Scan failed (epoch %s)", scan_epoch)
            self.ocr_engine.reset_diff_gate()
            safe_messages = {"Çevrimdışı çeviri modeli bulunamadı", "DeepL API anahtarı gerekli", "Çeviri servisine erişilemedi"}
            message = str(exc) if str(exc) in safe_messages else "Tarama başarısız · F9 ile yeniden dene"
            if self._error_queue.empty():
                self._error_queue.put_nowait((scan_epoch, message))
        finally:
            if com_result in (0, 1):
                ctypes.windll.ole32.CoUninitialize()
            with self._scan_lock:
                self._scan_busy = False

    def _process_ui_queue(self) -> None:
        if self._closing:
            return
        try:
            while True:
                scan_epoch, blocks, elapsed_ms, used_engine = self._ui_queue.get_nowait()
                if scan_epoch != self._scan_epoch:
                    continue
                self._last_blocks = blocks
                if self._is_demo_active() and self._demo_win is not None:
                    self._demo_win.set_translated_blocks(blocks, display_mode=self.config.display_mode)
                    self.overlay.clear()
                else:
                    self.overlay.render_blocks(blocks, active_roi=self._get_effective_roi())
                self.perf_lbl.setText(f"{used_engine.upper()} • {elapsed_ms:.0f} ms")
                self.block_badge.setText(f"{len(blocks)} BLOK")
                self.telemetry_cockpit.push_telemetry(elapsed_ms, used_engine, len(blocks))
                if blocks:
                    self._update_feed(blocks)
                    dialogue_candidate = max(blocks, key=lambda b: len(b.translated))
                    if len(dialogue_candidate.translated) >= 12:
                        self.tts_worker.enqueue(dialogue_candidate.translated)
        except queue.Empty:
            pass

        try:
            failed_epoch, message = self._error_queue.get_nowait()
            if failed_epoch == self._scan_epoch:
                self.telemetry_cockpit.set_status(message, False)
        except queue.Empty:
            pass
        # This timer belongs to the GUI thread. Worker threads only publish data.
        with self._scan_lock:
            rescan = self._pending_forced_scan and not self._scan_busy
            if rescan:
                self._pending_forced_scan = False
        if rescan:
            self.trigger_single_scan(force=True)

    def _update_feed(self, blocks: list[TextBlock]) -> None:
        html_parts: list[str] = []
        for blk in sorted(blocks, key=lambda b: bool(b.speaker), reverse=True)[:6]:
            if not blk.translated:
                continue
            en_esc = blk.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            tr_esc = blk.translated.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html_parts.append(
                f"<div style='margin-bottom:10px;'>"
                f"<span style='color:#9EA1AE; font-family:Segoe UI; font-size:12px;'>EN · {en_esc}</span><br/>"
                f"<span style='color:#F0F1F5; font-family:Segoe UI; font-size:13px;'>TR · {tr_esc}</span>"
                f"</div>"
            )
        self.feed_box.setHtml("".join(html_parts))

    def shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._model_setup.cancel()
        self.live_active = False
        with self._scan_lock:
            self._scan_epoch += 1
            self._pending_forced_scan = False
        for timer in (self._hdr_timer, self._hk_timer, self._queue_timer, self._live_timer, self._reload_timer):
            timer.stop()
        self._executor.submit(self.ocr_engine.close)
        self._executor.shutdown(wait=False, cancel_futures=False)
        try:
            self.tts_worker.shutdown()
        except Exception:
            pass
        try:
            self.overlay.close()
        except Exception:
            pass
        try:
            if self._demo_win:
                self._demo_win.close()
        except Exception:
            pass
        try:
            self.win.close()
            self.qapp.quit()
        except Exception:
            pass

    def run(self) -> None:
        sys.exit(self.qapp.exec())
