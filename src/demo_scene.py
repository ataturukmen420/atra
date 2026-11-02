"""
ATA Game Translator — PyQt6 Frameless AAA RPG Game Simulator (macOS / Linux Studio Toolbar Edition)
Features:
  • Apple macOS Sequoia / Linux Libadwaita draggable header bar & tactile scene selector pills
  • QPainter hardware-antialiased RPG HUD canvas
  • Direct In-Canvas Turkish Overlay Renderer (In-Place patches + Cinema Subtitles + ROI Reticles)
    so translations inside the Simulator are 100% immune to window Z-order, DWM fullscreen quirks,
    DPI scaling offsets, or WDA_EXCLUDEFROMCAPTURE screenshot hiding
  • Zero-occlusion offscreen English RGB buffer (`capture_canvas_rgb`) for genuine WinRT OCR scanning
"""
from __future__ import annotations

import copy
from typing import Callable, Optional

import ctranslate2  # noqa: F401
import sentencepiece  # noqa: F401
import numpy as np
from PyQt6.QtCore import QPoint, QRect, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QImage,
    QPixmap,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.ocr_engine import TextBlock
from src import brand

DEMO_SCENES: list[dict[str, str]] = [
    {
        "name": "Sahne 1: RDR2",
        "chapter": "Main Quest: Shadows Over Blackwater",
        "objective": "Find the hidden entrance behind the waterfall.",
        "tooltip_title": "Ancient Runed Greatsword",
        "tooltip_desc": "Increases critical strike damage by 25 percent against undead enemies.",
        "speaker_line": "Arthur Morgan: We need to head back to the camp before nightfall.",
        "prompt": "Press [E] to open the ancient chest.",
    },
    {
        "name": "Sahne 2: Witcher 3",
        "chapter": "Side Quest: The Whispering Woods",
        "objective": "Speak with Geralt at the tavern before midnight.",
        "tooltip_title": "Potion of Night Vision",
        "tooltip_desc": "Allows the player to see clearly in dark caves for sixty seconds.",
        "speaker_line": "Geralt: Follow the tracks carefully. The monster is hiding nearby.",
        "prompt": "Press [SPACE] to draw your silver sword.",
    },
    {
        "name": "Sahne 3: Cyberpunk",
        "chapter": "Main Quest: Heist in Night City",
        "objective": "Disable the security cameras in the control room.",
        "tooltip_title": "Cybernetic Optical Scanner",
        "tooltip_desc": "Reveals enemy weaknesses and security networks through walls.",
        "speaker_line": "Johnny Silverhand: Wake up samurai, we have a city to burn.",
        "prompt": "Hold [F] to hack the security terminal.",
    },
]


def _hex_to_qcolor(hex_str: str, alpha: int = 255) -> QColor:
    h = hex_str.lstrip("#")
    if len(h) != 6:
        return QColor(15, 22, 36, alpha)
    return QColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def _adjust_qcolor(col: QColor, factor: float, alpha: int = 255) -> QColor:
    r = max(0, min(255, int(col.red() * factor)))
    g = max(0, min(255, int(col.green() * factor)))
    b = max(0, min(255, int(col.blue() * factor)))
    return QColor(r, g, b, alpha)


class GameHudCanvas(QWidget):
    """
    920x520 RPG HUD Canvas rendered via QPainter.
    `render_hud_into(painter)` paints the pure English RPG scene (used for OCR capture).
    `paintEvent` paints `render_hud_into` followed by `render_translations_into` so the user
    always sees crisp, zero-lag Turkish translations directly inside the simulator window.
    """

    CANVAS_W = 920
    CANVAS_H = 520

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(self.CANVAS_W, self.CANVAS_H)
        self.scene_idx = 0
        self.translated_blocks: list[TextBlock] = []
        self.display_mode: str = "inplace"
        self.show_roi_brackets: bool = True

    def set_scene(self, idx: int) -> None:
        self.scene_idx = idx % len(DEMO_SCENES)
        self.translated_blocks = []
        self.update()

    def set_overlay_state(
        self,
        blocks: list[TextBlock],
        display_mode: str = "inplace",
        canvas_origin: Optional[tuple[int, int]] = None,
    ) -> None:
        local_blocks: list[TextBlock] = []
        ox, oy = canvas_origin if canvas_origin is not None else (0, 0)
        for b in blocks:
            tr = b.translated.strip()
            if not tr:
                continue
            bc = copy.copy(b)
            # Convert screen-absolute coordinates to canvas-local coordinates if needed
            if ox != 0 or oy != 0:
                bc.x -= ox
                bc.y -= oy
            local_blocks.append(bc)
        self.translated_blocks = local_blocks
        self.display_mode = display_mode
        self.update()

    def clear_overlay_state(self) -> None:
        self.translated_blocks = []
        self.update()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.render_hud_into(painter)
        self.render_translations_into(painter)
        painter.end()

    def render_hud_into(self, painter: QPainter) -> None:
        scene = DEMO_SCENES[self.scene_idx]

        # 1. Deep Obsidian Game Environment Background
        bg_grad = QLinearGradient(0, 0, 0, self.CANVAS_H)
        bg_grad.setColorAt(0.0, QColor("#1B1C21"))
        bg_grad.setColorAt(1.0, QColor("#15161B"))
        painter.fillRect(0, 0, self.CANVAS_W, self.CANVAS_H, bg_grad)

        # 2. Left Pause Menu Panel
        self._draw_box(painter, 24, 20, 211, 320, "#202126", "#35373F", 2.0)
        menu_items = ["Continue", "Load Game", "Inventory", "Settings", "Quit to Desktop"]
        y_pos = 42
        fnt_menu = QFont("Segoe UI Semibold")
        fnt_menu.setPixelSize(17)
        fnt_menu.setWeight(QFont.Weight.DemiBold)
        painter.setFont(fnt_menu)

        for item in menu_items:
            self._draw_box(painter, 40, y_pos, 178, 42, "#2B2D35", "#454852", 1.0)

            painter.setPen(QColor("#e2e8f0"))
            painter.drawText(
                QRect(58, y_pos, 155, 42),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                item,
            )
            y_pos += 54

        # 3. Top-Right Quest Tracker Box
        self._draw_box(painter, 265, 20, 625, 106, "#23252C", "#44434A", 2.0)


        fnt_title = QFont("Segoe UI")
        fnt_title.setPixelSize(19)
        fnt_title.setWeight(QFont.Weight.Bold)
        painter.setFont(fnt_title)
        painter.setPen(QColor("#E5D4B5"))
        painter.drawText(QRect(288, 36, 585, 30), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), scene["chapter"])

        fnt_body = QFont("Segoe UI")
        fnt_body.setPixelSize(17)
        painter.setFont(fnt_body)
        painter.setPen(QColor("#f1f5f9"))
        painter.drawText(QRect(288, 76, 585, 34), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), scene["objective"])

        # 4. Center-Right Item Tooltip Box
        self._draw_box(painter, 265, 148, 625, 137, "#25262E", "#41434D", 2.0)


        painter.setFont(fnt_title)
        painter.setPen(QColor("#E0E2ED"))
        painter.drawText(QRect(288, 166, 585, 30), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), scene["tooltip_title"])

        painter.setFont(fnt_body)
        painter.setPen(QColor("#e2e8f0"))
        painter.drawText(
            QRect(288, 208, 580, 64),
            int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
            scene["tooltip_desc"],
        )

        # 5. Interaction Prompt Box
        self._draw_box(painter, 265, 308, 625, 52, "#202D28", "#3B5549", 1.2)

        painter.setFont(fnt_menu)
        painter.setPen(QColor("#B6DDC8"))
        painter.drawText(
            QRect(288, 308, 585, 52),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            scene["prompt"],
        )

        # 6. Bottom Dialogue Subtitle Box
        self._draw_box(painter, 24, 390, 866, 105, "#191B21", "#3C3F49", 2.0)

        fnt_sub = QFont("Segoe UI Semibold")
        fnt_sub.setPixelSize(19)
        fnt_sub.setWeight(QFont.Weight.DemiBold)
        painter.setFont(fnt_sub)
        painter.setPen(QColor("#f8fafc"))
        painter.drawText(
            QRect(54, 426, 810, 56),
            int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
            scene["speaker_line"],
        )

    def render_translations_into(self, painter: QPainter) -> None:
        # 1. Draw subtle active ROI corner brackets inside canvas
        if self.show_roi_brackets:
            rx, ry, rw, rh = 3, 3, self.CANVAS_W - 6, self.CANVAS_H - 6
            x2, y2 = rx + rw, ry + rh
            clen = 18
            glow_pen = QPen(QColor(120, 174, 245, 20), 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            core_pen = QPen(QColor(120, 174, 245, 90), 1.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            for pen in (glow_pen, core_pen):
                painter.setPen(pen)
                painter.drawLine(rx, ry, rx + clen, ry)
                painter.drawLine(rx, ry, rx, ry + clen)
                painter.drawLine(x2 - clen, ry, x2, ry)
                painter.drawLine(x2, ry, x2, ry + clen)
                painter.drawLine(rx, y2 - clen, rx, y2)
                painter.drawLine(rx, y2, rx + clen, y2)
                painter.drawLine(x2 - clen, y2, x2, y2)
                painter.drawLine(x2, y2 - clen, x2, y2)

        if not self.translated_blocks:
            return

        if self.display_mode == "subtitle":
            # Hide the original dialogue inside this paint pass, never in OCR capture.
            painter.fillRect(QRect(22, 388, 870, 109), QColor("#15161B"))
            self._paint_cinema_subtitle(painter)
        else:
            self._paint_inplace_blocks(painter)

    def _fit_font(self, text: str, box_w: int, box_h: int, line_count: int, avg_line_h: float) -> tuple[QFont, int]:
        family = "Segoe UI Semibold"
        is_single = line_count == 1 and box_h < 38 and len(text) < 58
        target_px = max(11, min(26, int(avg_line_h * 0.88)))

        if is_single:
            for px in range(target_px, 9, -1):
                fnt = QFont(family)
                fnt.setPixelSize(px)
                fnt.setWeight(QFont.Weight.DemiBold)
                fm = QFontMetrics(fnt)
                if fm.horizontalAdvance(text) <= box_w:
                    return fnt, 0
            fnt = QFont(family)
            fnt.setPixelSize(10)
            fnt.setWeight(QFont.Weight.DemiBold)
            return fnt, max(20, box_w)

        wrap_w = max(80, box_w)
        for px in range(target_px, 10, -1):
            fnt = QFont(family)
            fnt.setPixelSize(px)
            fnt.setWeight(QFont.Weight.DemiBold)
            fm = QFontMetrics(fnt)
            rect = fm.boundingRect(
                QRect(0, 0, wrap_w, 2000),
                int(Qt.TextFlag.TextWordWrap),
                text,
            )
            if rect.height() <= box_h + 14:
                return fnt, wrap_w

        fnt = QFont(family)
        fnt.setPixelSize(11)
        fnt.setWeight(QFont.Weight.DemiBold)
        return fnt, wrap_w

    def _paint_inplace_blocks(self, painter: QPainter) -> None:
        pad_x = 4
        pad_y = 3

        for blk in self.translated_blocks:
            fnt, wrap_w = self._fit_font(
                blk.translated,
                max(50, blk.w),
                max(18, blk.h),
                blk.line_count,
                blk.avg_line_h,
            )
            fm = QFontMetrics(fnt)

            if wrap_w == 0:
                text_w = fm.horizontalAdvance(blk.translated)
                actual_w = max(blk.w, text_w + 6)
                actual_h = blk.h
            else:
                actual_w = max(blk.w, wrap_w)
                bound = fm.boundingRect(
                    QRect(0, 0, actual_w, 2000),
                    int(Qt.TextFlag.TextWordWrap),
                    blk.translated,
                )
                actual_h = max(blk.h, bound.height() + 4)

            x1 = float(max(0, blk.x - pad_x))
            y1 = float(max(0, blk.y - pad_y))
            w_box = float(actual_w + pad_x * 2)
            h_box = float(actual_h + pad_y * 2)
            rect_f = QRectF(x1, y1, w_box, h_box)

            base_bg = _hex_to_qcolor(blk.bg_hex, 255)
            painter.fillRect(rect_f, base_bg)

            painter.setFont(fnt)
            flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if wrap_w > 0:
                flags = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap)

            text_rect = QRect(
                int(x1 + pad_x),
                int(y1 + (pad_y if wrap_w > 0 else 0)),
                int(actual_w),
                int(actual_h if wrap_w > 0 else h_box),
            )

            painter.setPen(QColor(0, 0, 0, 210))
            painter.drawText(text_rect.translated(1, 1), flags, blk.translated)

            fg_col = _hex_to_qcolor(blk.fg_hex, 255)
            painter.setPen(fg_col)
            painter.drawText(text_rect, flags, blk.translated)

    def _paint_cinema_subtitle(self, painter: QPainter) -> None:
        dialogue = [b for b in self.translated_blocks if b.speaker and not b.speaker.startswith(("Ana Görev", "Yan Görev"))]
        sorted_blocks = dialogue or sorted(self.translated_blocks, key=lambda b: b.w * b.h, reverse=True)[:3]
        sorted_blocks.sort(key=lambda b: b.y)

        lines: list[str] = []
        speaker_badge = ""
        for b in sorted_blocks:
            tr = b.translated.strip()
            if not tr:
                continue
            if ":" in tr and not speaker_badge:
                sp, rest = tr.split(":", 1)
                if 2 <= len(sp.strip()) <= 25:
                    speaker_badge = sp.strip()
                    tr = rest.strip()
            lines.append(tr)

        if not lines:
            return

        full_text = "\n".join(lines)
        bar_w = int(self.CANVAS_W * 0.88)
        bar_x = (self.CANVAS_W - bar_w) // 2

        fnt = QFont("Segoe UI Semibold")
        fnt.setPixelSize(18)
        fnt.setWeight(QFont.Weight.DemiBold)
        fm = QFontMetrics(fnt)

        bound = fm.boundingRect(
            QRect(0, 0, bar_w - 48, 1000),
            int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignCenter),
            full_text,
        )
        bar_h = max(68, bound.height() + 36)
        bar_y = self.CANVAS_H - bar_h - 18

        rect_f = QRectF(float(bar_x), float(bar_y), float(bar_w), float(bar_h))
        grad = QLinearGradient(0, float(bar_y), 0, float(bar_y + bar_h))
        grad.setColorAt(0.0, QColor(14, 18, 28, 242))
        grad.setColorAt(1.0, QColor(9, 12, 19, 248))

        path = QPainterPath()
        path.addRoundedRect(rect_f, 12.0, 12.0)
        painter.fillPath(path, grad)

        painter.setPen(QPen(QColor(255, 255, 255, 38), 1.0))
        painter.drawPath(path)

        if speaker_badge:
            sp_fnt = QFont("Segoe UI")
            sp_fnt.setPixelSize(12)
            sp_fnt.setWeight(QFont.Weight.Bold)
            sp_fm = QFontMetrics(sp_fnt)
            sp_w = sp_fm.horizontalAdvance(speaker_badge.upper()) + 24
            sp_rect = QRectF(float(bar_x + 22), float(bar_y - 13), float(sp_w), 24.0)
            sp_path = QPainterPath()
            sp_path.addRoundedRect(sp_rect, 6.0, 6.0)
            painter.fillPath(sp_path, QColor("#303746"))
            painter.setFont(sp_fnt)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(sp_rect, int(Qt.AlignmentFlag.AlignCenter), speaker_badge.upper())

        painter.setFont(fnt)
        text_rect = QRect(bar_x + 24, bar_y + 14, bar_w - 48, bar_h - 28)
        align_flags = int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap)
        painter.setPen(QColor(0, 0, 0, 225))
        painter.drawText(text_rect.translated(1, 2), align_flags, full_text)
        painter.setPen(QColor(248, 250, 252))
        painter.drawText(text_rect, align_flags, full_text)

    @staticmethod
    def _draw_box(
        painter: QPainter,
        x: int,
        y: int,
        w: int,
        h: int,
        fill_hex: str,
        border_hex: str,
        border_w: float,
    ) -> None:
        rect=QRectF(x,y,w,h)
        path=QPainterPath(); path.addRoundedRect(rect,10,10)
        painter.fillPath(path,QColor(fill_hex))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(border_hex),1.0))
        painter.drawPath(path)
        painter.setPen(QPen(QColor(255,255,255,16),1.0))
        painter.drawLine(x+12,y+1,x+w-12,y+1)


class DemoGameWindow(QWidget):
    """
    Frameless Studio RPG Simulator Window with Apple macOS / Linux Libadwaita HeaderBar.
    Provides direct offscreen buffer capture (`capture_canvas_rgb`) AND direct in-canvas
    rendering (`set_translated_blocks`) so simulator translations are 100% bulletproof.
    """

    TOOLBAR_H = 60
    CANVAS_W = 920
    CANVAS_H = 520

    def __init__(
        self,
        _parent_compat: Optional[object] = None,
        on_scene_change: Optional[Callable[[], None]] = None,
        on_closed: Optional[Callable[[], None]] = None,
    ) -> None:
        from src.overlay import _ensure_qapp

        self._qapp = _ensure_qapp()
        super().__init__(None)
        self.on_scene_change = on_scene_change
        self.on_closed = on_closed
        self.scene_idx = 0
        self._drag_offset: Optional[QPoint] = None

        self.setWindowTitle(brand.SIMULATOR_TITLE)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedSize(self.CANVAS_W, self.CANVAS_H + self.TOOLBAR_H)
        self.move(42, 80)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.toolbar=QWidget(self)
        self.toolbar.setFixedHeight(self.TOOLBAR_H)
        self.toolbar.setStyleSheet("QWidget {background:#202126; color:#F5F5F7; border:none;}")
        tb_layout=QHBoxLayout(self.toolbar)
        tb_layout.setContentsMargins(18,10,14,10); tb_layout.setSpacing(8)
        logo=QLabel(); logo.setFixedSize(28,28)
        logo.setPixmap(QPixmap(str(brand.ASSETS/'app_logo.png')).scaled(28,28,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        tb_layout.addWidget(logo)
        title=QLabel("Simülatör")
        title.setStyleSheet("font-family:'Segoe UI Variable Text'; font-size:13px; font-weight:600; padding-right:12px;")
        tb_layout.addWidget(title)
        self._scene_btns=[]
        for idx,name in enumerate(("RDR2","Witcher 3","Cyberpunk")):
            button=QPushButton(name)
            button.setCursor(Qt.CursorShape.PointingHandCursor); button.setFixedHeight(32)
            button.clicked.connect(lambda _checked=False,i=idx:self.select_scene(i))
            tb_layout.addWidget(button); self._scene_btns.append(button)
        tb_layout.addStretch()
        next_btn=QPushButton("Sonraki sahne  ›")
        next_btn.setFixedHeight(32); next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        next_btn.setStyleSheet("QPushButton {background:#34363E; color:#ECEEF4; border:1px solid #484B55; border-radius:8px; padding:0 13px; font-family:'Segoe UI Variable Text'; font-size:12px;} QPushButton:hover {background:#40434C; border-color:#666A77;} QPushButton:focus {border-color:#7BA8FF;}")
        next_btn.clicked.connect(self.next_scene); tb_layout.addWidget(next_btn)
        close_btn=QPushButton("×"); close_btn.setAccessibleName("Simülatörü kapat")
        close_btn.setFixedSize(30,30); close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("QPushButton {background:transparent; color:#AEB1BC; border:none; border-radius:8px; font-size:21px;} QPushButton:hover {background:#393C44; color:#FFFFFF;} QPushButton:focus {border:1px solid #7BA8FF;}")
        close_btn.clicked.connect(self.close); tb_layout.addWidget(close_btn)

        root_layout.addWidget(self.toolbar)

        self.canvas_widget = GameHudCanvas(self)
        self.canvas_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        root_layout.addWidget(self.canvas_widget)

        self._refresh_tab_styles()
        self.show()
        self.hwnd = int(self.winId())

    def set_translated_blocks(self, blocks: list[TextBlock], display_mode: str = "inplace") -> None:
        rx, ry, _, _ = self.get_canvas_screen_rect()
        self.canvas_widget.set_overlay_state(blocks, display_mode=display_mode, canvas_origin=(rx, ry))

    def clear_translations(self) -> None:
        self.canvas_widget.clear_overlay_state()

    def get_scene_blocks(self) -> list[TextBlock]:
        """
        Returns exact deterministic TextBlocks for the current RPG scene in screen coordinates.
        Used for deterministic simulator geometry and as a 100% fail-safe supplement to WinRT OCR.
        """
        rx, ry, _, _ = self.get_canvas_screen_rect()
        sc = DEMO_SCENES[self.scene_idx]
        menu_items = ["Continue", "Load Game", "Inventory", "Settings", "Quit to Desktop"]
        blocks: list[TextBlock] = []

        y_pos = 48
        for item in menu_items:
            blocks.append(
                TextBlock(
                    text=item,
                    x=rx + 56,
                    y=ry + y_pos,
                    w=152,
                    h=28,
                    line_count=1,
                    avg_line_h=22.0,
                    bg_hex="#2B2D35",
                    fg_hex="#e2e8f0",
                )
            )
            y_pos += 54

        blocks.extend(
            [
                TextBlock(
                    text=sc["chapter"],
                    x=rx + 286,
                    y=ry + 34,
                    w=585,
                    h=30,
                    line_count=1,
                    avg_line_h=24.0,
                    bg_hex="#23252C",
                    fg_hex="#E5D4B5",
                ),
                TextBlock(
                    text=sc["objective"],
                    x=rx + 286,
                    y=ry + 74,
                    w=585,
                    h=32,
                    line_count=1,
                    avg_line_h=22.0,
                    bg_hex="#23252C",
                    fg_hex="#f1f5f9",
                ),
                TextBlock(
                    text=sc["tooltip_title"],
                    x=rx + 286,
                    y=ry + 164,
                    w=585,
                    h=30,
                    line_count=1,
                    avg_line_h=24.0,
                    bg_hex="#25262E",
                    fg_hex="#E0E2ED",
                ),
                TextBlock(
                    text=sc["tooltip_desc"],
                    x=rx + 286,
                    y=ry + 206,
                    w=580,
                    h=62,
                    line_count=2,
                    avg_line_h=22.0,
                    bg_hex="#25262E",
                    fg_hex="#e2e8f0",
                ),
                TextBlock(
                    text=sc["prompt"],
                    x=rx + 286,
                    y=ry + 318,
                    w=585,
                    h=32,
                    line_count=1,
                    avg_line_h=22.0,
                    bg_hex="#202D28",
                    fg_hex="#B6DDC8",
                ),
                TextBlock(
                    text=sc["speaker_line"],
                    x=rx + 52,
                    y=ry + 424,
                    w=810,
                    h=54,
                    line_count=1,
                    avg_line_h=24.0,
                    bg_hex="#191B21",
                    fg_hex="#f8fafc",
                ),
            ]
        )
        return blocks

    def _refresh_tab_styles(self) -> None:
        for index,button in enumerate(self._scene_btns):
            active=index==self.scene_idx
            if not active and button.hasFocus():
                button.clearFocus()
            button.setStyleSheet("QPushButton {background:"+("#484B55" if active else "transparent")+"; color:"+("#FFFFFF" if active else "#A5A9B6")+"; border:1px solid "+("#5C606D" if active else "transparent")+"; border-radius:8px; padding:0 14px; font-family:'Segoe UI Variable Text'; font-size:12px; font-weight:"+("600" if active else "400")+";} QPushButton:hover {background:#3A3D46; color:#FFFFFF;} QPushButton:focus {border-color:#7BA8FF;}")
        self.canvas_widget.setFocus()

    def select_scene(self, idx: int) -> None:
        self.scene_idx = idx % len(DEMO_SCENES)
        self.canvas_widget.set_scene(self.scene_idx)
        self._refresh_tab_styles()
        if self.on_scene_change:
            self.on_scene_change()

    def next_scene(self) -> None:
        self.select_scene(self.scene_idx + 1)

    def get_canvas_screen_rect(self) -> list[int]:
        top_left = self.canvas_widget.mapToGlobal(QPoint(0, 0))
        return [
            top_left.x(),
            top_left.y(),
            self.CANVAS_W,
            self.CANVAS_H,
        ]

    def capture_canvas_rgb(self) -> tuple[np.ndarray, tuple[int, int, int, int]]:
        """
        Thread-safe direct QImage rendering of the pure English RPG canvas.
        100% immune to window occlusion, DWM BitBlt quirks, or multi-monitor offsets.
        """
        qimg = QImage(self.CANVAS_W, self.CANVAS_H, QImage.Format.Format_RGB888)
        painter = QPainter(qimg)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.canvas_widget.render_hud_into(painter)
        painter.end()

        ptr = qimg.bits()
        ptr.setsize(qimg.sizeInBytes())
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape((self.CANVAS_H, qimg.bytesPerLine()))
        rgb = arr[:, : self.CANVAS_W * 3].reshape((self.CANVAS_H, self.CANVAS_W, 3)).copy()
        rx, ry, rw, rh = self.get_canvas_screen_rect()
        return rgb, (rx, ry, rw, rh)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= self.TOOLBAR_H:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            if self.on_scene_change:
                self.on_scene_change()

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:
        self._drag_offset = None

    def closeEvent(self, event: object) -> None:
        if self.on_closed:
            self.on_closed()
        super().closeEvent(event)  # type: ignore[arg-type]
