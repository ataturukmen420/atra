"""
ATA Game Translator — PyQt6 32-Bit Per-Pixel Alpha DirectComposition Overlay & ROI Selector
Uses QPainter Hardware Anti-Aliasing, True Translucent Glassmorphic Patches,
Win32 WS_EX_TRANSPARENT Click-Through, and WDA_EXCLUDEFROMCAPTURE Stealth Layering.
"""
from __future__ import annotations

import ctypes
import sys
from typing import Callable, Optional

import ctranslate2  # noqa: F401
import sentencepiece  # noqa: F401

from PyQt6.QtCore import QPoint, QRect, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QKeyEvent,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QApplication, QWidget

from src.config import AppConfig
from src.ocr_engine import TextBlock

user32 = ctypes.windll.user32

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000

WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011

HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040


_QAPP_REF: Optional[QApplication] = None


def _ensure_qapp() -> QApplication:
    global _QAPP_REF
    app = QApplication.instance()
    if app is None:
        _QAPP_REF = QApplication(sys.argv)
        return _QAPP_REF
    _QAPP_REF = app  # type: ignore[assignment]
    return _QAPP_REF  # type: ignore[return-value]


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


class GameOverlayWindow(QWidget):
    """
    32-Bit Per-Pixel Alpha Click-Through Game Overlay.
    Renders anti-aliased rounded glass In-Place translation patches and Cinema Subtitles
    while remaining 100% invisible to screen capture via WDA_EXCLUDEFROMCAPTURE.
    """

    def __init__(self, _parent_compat: Optional[object], config: AppConfig) -> None:
        _ensure_qapp()
        super().__init__(None)
        self.config = config
        self._last_render_sig: Optional[tuple[object, ...]] = None
        self._blocks: list[TextBlock] = []
        self._active_roi: Optional[list[int]] = config.roi

        screen = QGuiApplication.primaryScreen()
        geo = screen.virtualGeometry() if screen else QRect(0, 0, 1920, 1080)
        self.screen_w = geo.width()
        self.screen_h = geo.height()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        # Use screen_h - 1 to prevent Windows 10/11 DWM from promoting the borderless window
        # into Exclusive Fullscreen mode (which disables WS_EX_LAYERED per-pixel alpha compositing)
        self.setGeometry(geo.x(), geo.y(), self.screen_w, max(200, self.screen_h - 1))
        self.show()

        self.hwnd = int(self.winId())
        self._apply_win32_clickthrough()
        self.set_capture_exclusion(True)
        if screen:
            screen.virtualGeometryChanged.connect(self._refresh_geometry)

    def _refresh_geometry(self, geo: QRect) -> None:
        self.screen_w, self.screen_h = geo.width(), geo.height()
        self.setGeometry(geo.x(), geo.y(), geo.width(), max(1, geo.height()-1))
        self._last_render_sig = None
        self.update()

    def _apply_win32_clickthrough(self) -> None:
        ex_style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        new_style = (
            ex_style
            | WS_EX_LAYERED
            | WS_EX_TRANSPARENT
            | WS_EX_TOPMOST
            | WS_EX_TOOLWINDOW
            | WS_EX_NOACTIVATE
        )
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, new_style)
        self.ensure_topmost()

    def ensure_topmost(self) -> None:
        user32.SetWindowPos(
            self.hwnd,
            HWND_TOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )

    def set_capture_exclusion(self, exclude: bool = True) -> None:
        affinity = WDA_EXCLUDEFROMCAPTURE if exclude else WDA_NONE
        user32.SetWindowDisplayAffinity(self.hwnd, affinity)

    def clear(self) -> None:
        self._last_render_sig = None
        self._blocks = []
        self._active_roi = None
        self.update()

    def draw_roi_indicator(self, active_roi: Optional[list[int]] = None) -> None:
        self._active_roi = active_roi if active_roi is not None else self.config.roi
        self.ensure_topmost()
        self.update()

    def render_blocks(self, blocks: list[TextBlock], active_roi: Optional[list[int]] = None) -> bool:
        valid_blocks: list[TextBlock] = []
        for b in blocks:
            tr = b.translated.strip()
            if not tr:
                continue
            if self.config.hide_unchanged_blocks and tr.lower() == b.text.strip().lower():
                continue
            valid_blocks.append(b)

        eff_roi = active_roi if active_roi is not None else self.config.roi
        roi_key = tuple(eff_roi or [])
        sig = (
            self.config.display_mode,
            self.config.font_family, self.config.subtitle_font_size,
            self.config.inplace_padding, self.config.overlay_opacity,
            roi_key,
            tuple(
                (b.translated, b.x, b.y, b.w, b.h, b.line_count, b.avg_line_h, b.bg_hex, b.fg_hex)
                for b in valid_blocks
            ),
        )
        if sig == self._last_render_sig:
            self.ensure_topmost()
            return False

        self._last_render_sig = sig
        self._blocks = valid_blocks
        self._active_roi = eff_roi
        self.ensure_topmost()
        self.update()
        return True

    def _fit_font(self, text: str, box_w: int, box_h: int, line_count: int, avg_line_h: float) -> tuple[QFont, int]:
        family = self.config.font_family
        is_single = line_count == 1 and box_h < 38 and len(text) < 58
        target_px = max(11, min(28, int(avg_line_h * 0.88)))

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

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        # OCR rectangles use virtual-desktop coordinates, including negative origins.
        painter.translate(-self.x(), -self.y())

        # 1. Draw Sci-Fi ROI Corner Reticles if active
        if self._active_roi and len(self._active_roi) == 4:
            self._paint_roi_brackets(painter, self._active_roi)

        if not self._blocks:
            painter.end()
            return

        if self.config.display_mode == "subtitle":
            self._paint_cinema_subtitle(painter)
        else:
            self._paint_inplace_blocks(painter)

        painter.end()

    def _paint_roi_brackets(self, painter: QPainter, roi: list[int]) -> None:
        rx, ry, rw, rh = [int(v) for v in roi]
        x2, y2 = rx + rw, ry + rh
        clen = 20

        # Outer soft cyan glow pen
        glow_pen = QPen(QColor(120, 174, 245, 20), 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        core_pen = QPen(QColor(120, 174, 245, 135), 1.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)

        for pen in (glow_pen, core_pen):
            painter.setPen(pen)
            # Top-Left
            painter.drawLine(rx, ry, rx + clen, ry)
            painter.drawLine(rx, ry, rx, ry + clen)
            # Top-Right
            painter.drawLine(x2 - clen, ry, x2, ry)
            painter.drawLine(x2, ry, x2, ry + clen)
            # Bottom-Left
            painter.drawLine(rx, y2 - clen, rx, y2)
            painter.drawLine(rx, y2, rx + clen, y2)
            # Bottom-Right
            painter.drawLine(x2 - clen, y2, x2, y2)
            painter.drawLine(x2, y2 - clen, x2, y2)

    def _paint_inplace_blocks(self, painter: QPainter) -> None:
        pad_x = max(3, self.config.inplace_padding)
        pad_y = 3

        for blk in self._blocks:
            screen = QGuiApplication.screenAt(QPoint(blk.x, blk.y)) or QGuiApplication.primaryScreen()
            area = screen.geometry()
            available_w = max(20, area.right()-max(area.left(), blk.x)-pad_x*2)
            source_w = min(max(20, blk.w), available_w)
            fnt, wrap_w = self._fit_font(
                blk.translated,
                source_w,
                max(18, blk.h),
                blk.line_count,
                blk.avg_line_h,
            )
            fm = QFontMetrics(fnt)

            if wrap_w == 0:
                text_w = fm.horizontalAdvance(blk.translated)
                actual_w = min(available_w, max(source_w, text_w + 6))
                actual_h = blk.h
            else:
                actual_w = min(available_w, max(source_w, wrap_w))
                bound = fm.boundingRect(
                    QRect(0, 0, actual_w, 2000),
                    int(Qt.TextFlag.TextWordWrap),
                    blk.translated,
                )
                actual_h = max(blk.h, bound.height() + 4)

            x1 = float(max(area.left(), blk.x - pad_x))
            y1 = float(max(area.top(), min(blk.y-pad_y, area.bottom()-actual_h-pad_y*2)))
            w_box = float(actual_w + pad_x * 2)
            h_box = float(actual_h + pad_y * 2)
            rect_f = QRectF(x1, y1, w_box, h_box)

            # Seamless 100% opaque exact-color patch so it melts invisibly into the game's UI panel
            bg_col = _hex_to_qcolor(blk.bg_hex, 255)
            fg_col = _hex_to_qcolor(blk.fg_hex, 255)

            path = QPainterPath()
            path.addRoundedRect(rect_f, 4.0, 4.0)
            painter.fillPath(path, bg_col)

            painter.setFont(fnt)
            if wrap_w == 0:
                tx = int(x1 + pad_x)
                ty = int(y1 + pad_y + (actual_h + fm.ascent() - fm.descent()) * 0.5)
                painter.setPen(QColor(2, 6, 23, 220))
                painter.drawText(tx + 1, ty + 1, blk.translated)
                painter.setPen(fg_col)
                painter.drawText(tx, ty, blk.translated)
            else:
                trect = QRect(int(x1 + pad_x), int(y1 + pad_y), int(actual_w), int(actual_h + 6))
                trect_sh = trect.translated(1, 1)
                painter.setPen(QColor(2, 6, 23, 220))
                painter.drawText(trect_sh, int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), blk.translated)
                painter.setPen(fg_col)
                painter.drawText(trect, int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop), blk.translated)

    def _paint_cinema_subtitle(self, painter: QPainter) -> None:
        dialogue = [b for b in self._blocks if b.speaker and not b.speaker.startswith("Ana Görev")]
        sorted_blocks = sorted(dialogue or self._blocks, key=lambda b: b.y)[-3:]
        sorted_blocks.sort(key=lambda b: b.y)
        combined_text = "\n".join(b.translated for b in sorted_blocks if b.translated)
        if not combined_text.strip():
            return

        fnt = QFont("Segoe UI Semibold")
        fnt.setPixelSize(max(18, self.config.subtitle_font_size))
        fnt.setWeight(QFont.Weight.DemiBold)
        fm = QFontMetrics(fnt)

        anchor = self._blocks[-1]
        screen = QGuiApplication.screenAt(QPoint(anchor.x, anchor.y)) or QGuiApplication.primaryScreen()
        area = QRect(*self._active_roi) if self._active_roi else screen.geometry()
        max_bar_w = max(100, min(area.width()-24, int(area.width() * .86)))
        bound = fm.boundingRect(
            QRect(0, 0, max_bar_w - 64, 1000),
            int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignHCenter),
            combined_text,
        )
        bar_w = min(max_bar_w, max(240, bound.width() + 72))
        bar_h = max(64, bound.height() + 36)

        bx = float(area.x() + (area.width() - bar_w) * 0.5)
        by = float(max(area.y()+12, area.y()+area.height()-bar_h-24))
        rect_f = QRectF(bx, by, float(bar_w), float(bar_h))

        # Glassmorphic dark gradient plate
        grad = QLinearGradient(bx, by, bx, by + bar_h)
        grad.setColorAt(0.0, QColor(34, 35, 41, 242))
        grad.setColorAt(1.0, QColor(23, 24, 28, 248))

        path = QPainterPath()
        path.addRoundedRect(rect_f, 14.0, 14.0)
        painter.fillPath(path, grad)

        painter.setPen(QPen(QColor(255, 255, 255, 38), 1.0))
        painter.drawPath(path)

        # Quiet top light on the cinema material.
        top_strip = QPainterPath()
        top_strip.addRoundedRect(QRectF(bx + 28, by + 1, bar_w - 56, 1.0), .5, .5)
        painter.fillPath(top_strip, QColor(255, 255, 255, 28))

        painter.setFont(fnt)
        trect = QRect(int(bx + 32), int(by + 16), int(bar_w - 64), int(bar_h - 28))
        flags = int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignCenter)
        painter.setPen(QColor(2, 6, 23, 230))
        painter.drawText(trect.translated(1, 2), flags, combined_text)
        painter.setPen(QColor(248, 250, 252, 255))
        painter.drawText(trect, flags, combined_text)


class RoiSelectorModal(QWidget):
    """
    Fullscreen Interactive Crosshair Region Selector with Live Dimension Readout.
    Left-Click Drag to select an area; Right-Click or ESC to reset to Full Screen.
    """

    def __init__(self, _parent_compat: Optional[object], on_selected: Callable[[Optional[list[int]]], None]) -> None:
        _ensure_qapp()
        super().__init__(None)
        self.on_selected = on_selected
        self._start_pt: Optional[QPoint] = None
        self._cur_pt: Optional[QPoint] = None

        screen = QGuiApplication.primaryScreen()
        geo = screen.virtualGeometry() if screen else QRect(0, 0, 1920, 1080)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self.setGeometry(geo)
        self.show()
        self.activateWindow()
        self.raise_()

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)

        # Dimmed screen backdrop
        painter.fillRect(self.rect(), QColor(5, 8, 17, 135))

        # Top instruction pill
        bw, bh = 740, 48
        bx = (self.width() - bw) * 0.5
        by = 36.0
        pill = QPainterPath()
        pill.addRoundedRect(QRectF(bx, by, bw, bh), 12.0, 12.0)
        painter.fillPath(pill, QColor(29, 30, 36, 245))
        painter.setPen(QPen(QColor(120, 174, 245, 100), 1.0))
        painter.drawPath(pill)

        fnt = QFont("Segoe UI", 12, QFont.Weight.DemiBold)
        painter.setFont(fnt)
        painter.setPen(QColor(248, 250, 252))
        painter.drawText(
            QRect(int(bx), int(by), bw, bh),
            int(Qt.AlignmentFlag.AlignCenter),
            "Çeviri alanını seçin · Fareyle sürükleyin     Sıfırla: Esc / sağ tık",
        )

        if self._start_pt and self._cur_pt:
            x0 = min(self._start_pt.x(), self._cur_pt.x())
            y0 = min(self._start_pt.y(), self._cur_pt.y())
            w = abs(self._cur_pt.x() - self._start_pt.x())
            h = abs(self._cur_pt.y() - self._start_pt.y())
            sel_rect = QRectF(float(x0), float(y0), float(w), float(h))

            painter.fillRect(sel_rect, QColor(0, 242, 254, 28))
            painter.setPen(QPen(QColor(120, 174, 245, 220), 1.2))
            painter.drawRoundedRect(sel_rect, 4.0, 4.0)

            if w > 40 and h > 20:
                dim_fnt = QFont("Consolas", 10, QFont.Weight.Bold)
                painter.setFont(dim_fnt)
                painter.setPen(QColor("#78AEF5"))
                painter.drawText(x0 + 8, max(22, y0 - 8), f"{w} × {h} px")

        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.close()
            self.on_selected(None)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pt = event.pos()
            self._cur_pt = event.pos()
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._start_pt is not None:
            self._cur_pt = event.pos()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._start_pt is not None:
            end_pt = event.pos()
            x0 = min(self._start_pt.x(), end_pt.x())
            y0 = min(self._start_pt.y(), end_pt.y())
            w = abs(end_pt.x() - self._start_pt.x())
            h = abs(end_pt.y() - self._start_pt.y())
            self.close()
            if w >= 50 and h >= 25:
                origin = self.mapToGlobal(QPoint(x0, y0))
                self.on_selected([origin.x(), origin.y(), w, h])
            else:
                self.on_selected(None)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            self.on_selected(None)
