"""
ATA Game Translator — Bespoke Duotone SVG Iconography, 3-Layer Glass Medallions,
Harmonic Spring Physics Engine (stiffness=480, damping=30), and Cryptographic Text Scrambler.
Implements `bespoke-iconography-svg` and `futuristic-motion-shaders` doctrines.
"""
from __future__ import annotations

import random
import time
from typing import Callable, Optional

import ctranslate2  # noqa: F401
import sentencepiece  # noqa: F401

from PyQt6.QtCore import QByteArray, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QWidget, QStyle


# ── BESPOKE DUOTONE 24x24 SVG TEMPLATES (0.18 Fill Chamber + 1.6px Stroke + Focal Beacon) ──
DUOTONE_SVGS = {'play': '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" '
         'stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"><path d="M8 5L19 12 8 19Z" '
         'fill="{color}" fill-opacity=".14" stroke="{color}"/></svg>',
 'pause': '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" '
          'stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"><path d="M8 5V19M16 5V19" '
          'stroke="{color}" stroke-width="3"/></svg>',
 'bolt': '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" '
         'stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"><path d="M13 3L5 13H11L10 21 19 10H13Z" '
         'stroke="{color}" fill="{color}" fill-opacity=".1"/></svg>',
 'reticle': '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" '
            'stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"><path d="M8 4H4V8M16 4H20V8M4 '
            '16V20H8M20 16V20H16M8 12H16M12 8V16" stroke="{color}"/></svg>',
 'gamepad': '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" '
            'stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"><path d="M7 7H17Q20 7 21 15L21 17Q21 '
            '20 18 18L15 15H9L6 18Q3 20 3 17L3 15Q4 7 7 7Z" stroke="{color}" fill="{color}" '
            'fill-opacity=".08"/><path d="M8 9V13M6 11H10M16 10H16.1M18 12H18.1" stroke="{color}"/></svg>',
 'sweep': '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" '
          'stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"><path d="M15 3L7 12M5 11L13 18 9 21Q5 '
          '20 2 16Z" stroke="{color}" fill="{color}" fill-opacity=".1"/><path d="M15 18H21M18 14H21" '
          'stroke="{color}"/></svg>',
 'pin': '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" '
        'stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"><path d="M12 21S5 14 5 9A7 7 0 0 1 19 '
        '9C19 14 12 21 12 21Z" stroke="{color}"/><circle cx="12" cy="9" r="2.5" stroke="{color}"/></svg>',
 'cinema': '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" '
           'stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"><rect x="3" y="5" width="18" '
           'height="14" rx="3" stroke="{color}"/><path d="M7 12H12M7 15H17M15 12H17" '
           'stroke="{color}"/></svg>',
 'cpu': '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" '
        'stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"><rect x="6" y="6" width="12" height="12" '
        'rx="3" stroke="{color}"/><path d="M9 3V6M15 3V6M9 18V21M15 18V21M3 9H6M3 15H6M18 9H21M18 15H21" '
        'stroke="{color}"/><rect x="9" y="9" width="6" height="6" rx="1" fill="{color}" '
        'fill-opacity=".2"/></svg>',
 'diamond': '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" '
            'stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"><path d="M7 4H17L22 10 12 21 2 10Z" '
            'stroke="{color}"/><path d="M2 10H22M7 4L12 21 17 4" stroke="{color}"/></svg>',
 'terminal': '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" '
             'stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"><rect x="3" y="5" width="18" '
             'height="14" rx="3" stroke="{color}"/><path d="M7 9L10 12 7 15M13 15H17" '
             'stroke="{color}"/></svg>',
 'shield': '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" '
           'stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"><path d="M12 3L20 6V12C20 17 12 21 12 '
           '21S4 17 4 12V6Z" stroke="{color}"/><path d="M8 12L11 15 16 9" stroke="{color}"/></svg>',
 'wave': '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" '
         'stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"><path d="M4 9H8L13 5V19L8 15H4Z" '
         'stroke="{color}"/><path d="M17 8C20 11 20 13 17 16M20 5C24 9 24 15 20 19" stroke="{color}"/></svg>',
 'core': '<svg viewBox="0 0 24 24" fill="none" stroke-width="1.6" stroke-linecap="round" '
         'stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg"><path d="M5 19L10 5Q12 2 14 5L19 19M8 '
         '14H20" stroke="{color}"/></svg>'}

_SVG_CACHE: dict[tuple[str, str], QSvgRenderer] = {}


def render_duotone_svg(
    painter: QPainter,
    icon_name: str,
    cx: float,
    cy: float,
    size: float,
    color_hex: str = "#00f0ff",
    *,
    stroke_hex: Optional[str] = None,
    fill_hex: Optional[str] = None,
    fill_alpha: float = 0.22,
) -> None:
    """Renders a cached Duotone SVG icon centered at (cx, cy)."""
    eff_color = (stroke_hex or color_hex).lower()
    key = (icon_name, eff_color)
    renderer = _SVG_CACHE.get(key)
    if renderer is None:
        tpl = DUOTONE_SVGS.get(icon_name, DUOTONE_SVGS["core"])
        svg_xml = tpl.replace("{color}", eff_color)
        renderer = QSvgRenderer(QByteArray(svg_xml.encode("utf-8")))
        _SVG_CACHE[key] = renderer

    half = size * 0.5
    renderer.render(painter, QRectF(cx - half, cy - half, size, size))


def draw_glass_medallion(
    painter: QPainter,
    cx: float,
    cy: float,
    box_size: float,
    icon_name: str,
    accent_hex: str = "#00f0ff",
    hover_t: float = 0.0,
    *,
    secondary_hex: Optional[str] = None,
    corner_radius: Optional[float] = None,
) -> None:
    """
    Draws a 3-Layer Optical Glass Medallion housing a Duotone SVG icon:
      Layer 1: Ambient radial back-bloom
      Layer 2: Double-ring specular glass container (inset top catch-light)
      Layer 3: Duotone SVG with glowing focal node
    """
    half = box_size * 0.5
    rect_f = QRectF(cx - half, cy - half, box_size, box_size)
    rad = corner_radius if corner_radius is not None else box_size * 0.28
    acc_col = QColor(accent_hex)

    # Layer 1: Inner radial bloom
    bloom = QRadialGradient(QPointF(cx, cy), half * 1.15)
    c_mid = QColor(acc_col)
    c_mid.setAlpha(int(16 + 18 * hover_t))
    bloom.setColorAt(0.0, c_mid)
    bloom.setColorAt(1.0, QColor(0, 0, 0, 0))

    path = QPainterPath()
    path.addRoundedRect(rect_f, rad, rad)

    grad = QLinearGradient(rect_f.left(), rect_f.top(), rect_f.left(), rect_f.bottom())
    grad.setColorAt(0.0, QColor(255, 255, 255, int(24 + 14 * hover_t)))
    grad.setColorAt(1.0, QColor(10, 16, 30, 210))
    painter.fillPath(path, grad)
    painter.fillPath(path, bloom)

    # Layer 2: Specular top rim + outer border
    b_col = QColor(acc_col)
    b_col.setAlpha(int(38 + 42 * hover_t))
    painter.setPen(QPen(b_col, 1.1))
    painter.drawPath(path)

    painter.setPen(QPen(QColor(255, 255, 255, int(28 + 14 * hover_t)), 1.0))
    painter.drawLine(
        QPointF(rect_f.left() + rad, rect_f.top() + 1.0),
        QPointF(rect_f.right() - rad, rect_f.top() + 1.0),
    )

    # Layer 3: Duotone SVG
    icon_sz = box_size * (0.60 + 0.04 * hover_t)
    render_duotone_svg(painter, icon_name, cx, cy, icon_sz, accent_hex)


class GlassMedallionWidget(QWidget):
    """Standalone 3-Layer Glass Medallion QWidget for form/toggle rows."""

    def __init__(
        self,
        icon_name: str,
        accent_hex: str = "#00f0ff",
        size: int = 28,
        *,
        secondary_hex: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.icon_name = icon_name
        self.accent_hex = accent_hex
        self.secondary_hex = secondary_hex
        self.setFixedSize(size, size)

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        sz = float(self.width())
        draw_glass_medallion(
            painter,
            sz * 0.5,
            sz * 0.5,
            sz - 2.0,
            self.icon_name,
            self.accent_hex,
            0.2,
            secondary_hex=self.secondary_hex,
        )
        painter.end()


class SpringAnimator:
    """
    60 FPS Second-Order Harmonic Spring Physics Animator
    (Emil Kowalski / Rauno Freiberg Doctrine: stiffness=460, damping=30).
    """

    def __init__(
        self,
        initial: float,
        on_update: Callable[[float], None],
        stiffness: float = 460.0,
        damping: float = 30.0,
        parent: Optional[QWidget] = None,
    ) -> None:
        self.value = float(initial)
        self.target = float(initial)
        self.velocity = 0.0
        self.stiffness = stiffness
        self.damping = damping
        self.on_update = on_update
        self._last_time = time.monotonic()
        self._animate = parent is None or bool(parent.style().styleHint(QStyle.StyleHint.SH_Widget_Animate))

        self._timer = QTimer(parent)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._step)

    def set_target(self, target: float, immediate: bool = False) -> None:
        self.target = target
        if immediate or not self._animate:
            self.value = target
            self.velocity = 0.0
            self._timer.stop()
            self.on_update(self.value)
            return
        if not self._timer.isActive():
            self._last_time = time.monotonic()
            self._timer.start()

    def impulse(self, dv: float) -> None:
        if not self._animate:
            return
        self.velocity += dv
        if not self._timer.isActive():
            self._last_time = time.monotonic()
            self._timer.start()

    def _step(self) -> None:
        now = time.monotonic()
        remaining = min(.064, max(.001, now-self._last_time))
        self._last_time = now
        # Small integration steps stay stable when a render/event takes longer than 16ms.
        while remaining > 0:
            dt = min(.008, remaining)
            accel = -self.stiffness*(self.value-self.target)-self.damping*self.velocity
            self.velocity += accel*dt
            self.value += self.velocity*dt
            remaining -= dt

        if abs(self.target - self.value) < 0.002 and abs(self.velocity) < 0.01:
            self.value = self.target
            self.velocity = 0.0
            self._timer.stop()

        self.on_update(self.value)


class CryptographicScrambler:
    """
    Cycles characters through '01X/#∆◊_' for 240ms before locking in the target telemetry string.
    """

    GLYPHS = "01X/#∆◊_∑λ"

    def __init__(self, on_text: Callable[[str], None], parent: Optional[QWidget] = None) -> None:
        self.on_text = on_text
        self._target = ""
        self._step = 0
        self._max_steps = 8
        self._timer = QTimer(parent)
        self._timer.setInterval(28)
        self._timer.timeout.connect(self._tick)

    def scramble_to(self, target: str) -> None:
        self._target = target
        self._step = 0
        if not self._timer.isActive():
            self._timer.start()
        self._tick()

    def _tick(self) -> None:
        self._step += 1
        if self._step >= self._max_steps:
            self._timer.stop()
            self.on_text(self._target)
            return

        locked_len = int(len(self._target) * (self._step / self._max_steps))
        out_chars: list[str] = []
        for i, ch in enumerate(self._target):
            if i < locked_len or ch in (" ", "•", "●", ":", "(", ")", "[", "]"):
                out_chars.append(ch)
            else:
                out_chars.append(random.choice(self.GLYPHS))
        self.on_text("".join(out_chars))
