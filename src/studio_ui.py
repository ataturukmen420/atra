"""Atra's native Studio surfaces. Presentation only; no capture or translation work."""
from __future__ import annotations

from collections import deque
from typing import Callable, Optional
import ctranslate2  # noqa: F401
import sentencepiece  # noqa: F401
from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QAbstractButton, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from . import brand
from .svg_medallions import SpringAnimator, render_duotone_svg


def ui_font(size: int, weight=QFont.Weight.Normal, mono=False) -> QFont:
    font = QFont("Consolas" if mono else "Segoe UI Variable Text")
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


def _lerp_qcolor(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0., min(1., t))
    return QColor(*[round(x+(y-x)*t) for x,y in zip(a.getRgb(), b.getRgb())])


def rounded(p: QPainter, rect: QRectF, radius: float, fill, border=None):
    path = QPainterPath(); path.addRoundedRect(rect, radius, radius)
    p.fillPath(path, fill)
    if border is not None:
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(border, 1.))
        p.drawPath(path)
    return path


def text(p, rect, content, size=13, color=brand.TEXT, weight=QFont.Weight.Normal,
         align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, mono=False):
    p.setFont(ui_font(size, weight, mono))
    p.setPen(QColor(color))
    p.drawText(rect, int(align), content)


def focus_ring(p, rect, radius):
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(123,168,255,200), 2.))
    p.drawRoundedRect(rect.adjusted(2,2,-2,-2), radius, radius)


class StudioButton(QAbstractButton):
    """One material family, native button behavior, explicit content geometry."""
    def __init__(self, text: str, on_click: Callable[[], None], *, subtitle="", kbd_tag="",
                 accent_hex=brand.ACCENT, icon="", is_hero=False,
                 top_idle="#34363D", bot_idle="#2B2D33", border_idle="#44464D",
                 top_hover="#3D4048", bot_hover="#33363D", border_hover="#5A5D66",
                 fg_idle=brand.TEXT, fg_hover="#FFFFFF", height=60, font_px=14, radius=12.):
        super().__init__()
        self.text_str, self.subtitle_str, self.kbd_tag = text, subtitle, kbd_tag
        self.on_click, self.icon_name, self.is_hero = on_click, icon, is_hero
        self.accent_hex, self.radius, self.font_px = accent_hex, radius, font_px
        for name,value in locals().copy().items():
            if name.startswith(('top_','bot_','border_','fg_')):
                setattr(self,name,QColor(value))
        self.setFixedHeight(height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(text)
        self.setToolTip(text + (" · "+subtitle if subtitle else ""))
        self._hover_t, self._scale_t = 0., 1.
        self._hover_spring = SpringAnimator(0.,self._hover,stiffness=440,damping=34,parent=self)
        self._scale_spring = SpringAnimator(1.,self._scale,stiffness=540,damping=34,parent=self)
        self.pressed.connect(lambda: self._scale_spring.set_target(.98))
        self.released.connect(lambda: self._scale_spring.set_target(1.))
        self.clicked.connect(lambda _=False: self.on_click())

    def _hover(self,v): self._hover_t=max(0.,min(1.,v)); self.update()
    def _scale(self,v): self._scale_t=v; self.update()

    def set_palette(self, *, text, icon, accent_hex=None, subtitle=None, kbd_tag=None,
                    top_idle="#34363D", bot_idle="#2B2D33", border_idle="#44464D",
                    top_hover="#3D4048", bot_hover="#33363D", border_hover="#5A5D66",
                    fg_idle=brand.TEXT, fg_hover="#FFFFFF"):
        self.text_str, self.icon_name = text, icon
        if subtitle is not None: self.subtitle_str=subtitle
        if kbd_tag is not None: self.kbd_tag=kbd_tag
        if accent_hex is not None: self.accent_hex=accent_hex
        for name,value in locals().copy().items():
            if name.startswith(('top_','bot_','border_','fg_')):
                setattr(self,name,QColor(value))
        self.setAccessibleName(text)
        self.setToolTip(text + (" · "+self.subtitle_str if self.subtitle_str else ""))
        self.update()

    def enterEvent(self,event):
        self._hover_spring.set_target(1.); super().enterEvent(event)

    def leaveEvent(self,event):
        self._hover_spring.set_target(0.); super().leaveEvent(event)

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and not event.isAutoRepeat():
            self.click(); event.accept()
        else: super().keyPressEvent(event)

    def text_geometry(self):
        """Content reservation shared by painting and overflow inspection."""
        left = 58 if self.icon_name else 12
        if self.is_hero and self.icon_name: left=62
        reserved=14
        if self.kbd_tag:
            fm=QFontMetrics(ui_font(10,QFont.Weight.Medium,True))
            reserved=max(30,fm.horizontalAdvance(self.kbd_tag)+14)+24
        return QRectF(left,0,max(0,self.width()-left-reserved),self.height())

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        w,h=self.width(),self.height()
        p.translate(w/2,h/2); p.scale(self._scale_t,self._scale_t); p.translate(-w/2,-h/2)
        if not self.isEnabled(): p.setOpacity(.45)
        t=self._hover_t
        rect=QRectF(1,1,w-2,h-3)
        rounded(p,rect.translated(0,1.5),self.radius,QColor(0,0,0,95))
        gradient=QLinearGradient(0,0,0,h)
        gradient.setColorAt(0,_lerp_qcolor(self.top_idle,self.top_hover,t))
        gradient.setColorAt(1,_lerp_qcolor(self.bot_idle,self.bot_hover,t))
        rounded(p,rect,self.radius,gradient,_lerp_qcolor(self.border_idle,self.border_hover,t))
        p.setPen(QPen(QColor(255,255,255,35 if self.is_hero else 22),1))
        p.drawLine(QPointF(self.radius+2,2),QPointF(w-self.radius-2,2))
        if self.hasFocus(): focus_ring(p,rect,self.radius-2)
        if not self.icon_name:
            text(p,QRectF(0,0,w,h),self.text_str,self.font_px,align=Qt.AlignmentFlag.AlignCenter)
            return
        badge=QRectF(13,(h-32)/2,32,32)
        rounded(p,badge,9,QColor(255,255,255,18 if self.is_hero else 8),QColor(255,255,255,15))
        render_duotone_svg(p,self.icon_name,badge.center().x(),badge.center().y(),19,
                           "#FFFFFF" if self.is_hero else "#CED1DB")
        content=self.text_geometry()
        fg=_lerp_qcolor(self.fg_idle,self.fg_hover,t).name()
        if self.subtitle_str:
            text(p,QRectF(content.x(),h/2-21,content.width(),23),self.text_str,self.font_px,fg,QFont.Weight.DemiBold)
            text(p,QRectF(content.x(),h/2+1,content.width(),19),self.subtitle_str,12,
                 "#F4F7FF" if self.is_hero else brand.SECONDARY)
        else: text(p,content,self.text_str,self.font_px,fg,QFont.Weight.DemiBold)
        if self.kbd_tag:
            fm=QFontMetrics(ui_font(10,QFont.Weight.Medium,True))
            kw=max(30,fm.horizontalAdvance(self.kbd_tag)+14)
            key=QRectF(w-kw-13,(h-22)/2,kw,22)
            rounded(p,key.translated(0,1),6,QColor(255,255,255,18))
            rounded(p,key,6,QColor(0,0,0,38 if self.is_hero else 50),QColor(0,0,0,28))
            text(p,key,self.kbd_tag,10,"#EBF1FF" if self.is_hero else "#B8BBC6",
                 QFont.Weight.Medium,Qt.AlignmentFlag.AlignCenter,True)


class StudioSegmentedBar(QWidget):
    def __init__(self,options,initial_key,on_change,*,active_top=brand.ACCENT,
                 active_bot="#244875",active_fg="#FFFFFF",height=40):
        super().__init__()
        self.options,self.current_key,self.on_change=options,initial_key,on_change
        self.active_top=QColor(active_top)
        self.setFixedHeight(height); self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(" / ".join(label for _,label,_ in options))
        self._pill_pos=float(self._index_for_key(initial_key))
        self._spring=SpringAnimator(self._pill_pos,self._on_spring,stiffness=440,damping=34,parent=self)

    def _index_for_key(self,key): return next((i for i,item in enumerate(self.options) if item[0]==key),0)
    def _on_spring(self,v): self._pill_pos=v; self.update()
    def set_key(self,key,animate=True):
        self.current_key=key; self._spring.set_target(float(self._index_for_key(key)),immediate=not animate)
        self.setAccessibleDescription(next((label for k,label,_ in self.options if k==key),key))
        self.update()
    def _choose(self,index):
        key=self.options[index][0]
        if key!=self.current_key: self.set_key(key); self.on_change(key)
    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton:
            self._choose(max(0,min(len(self.options)-1,int(e.position().x()*len(self.options)/max(1,self.width())))))
    def keyPressEvent(self,e):
        if e.key() in (Qt.Key.Key_Left,Qt.Key.Key_Right):
            self._choose((self._index_for_key(self.current_key)+(1 if e.key()==Qt.Key.Key_Right else -1))%len(self.options))
            e.accept()
        else: super().keyPressEvent(e)
    def paintEvent(self,e):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w,h=self.width(),self.height(); sw=(w-6)/len(self.options)
        rounded(p,QRectF(1,1,w-2,h-2),10,QColor(brand.RECESSED),QColor(0,0,0,60))
        pos=3+self._pill_pos*sw
        gradient=QLinearGradient(0,3,0,h-3)
        gradient.setColorAt(0,QColor("#4A4C55")); gradient.setColorAt(1,QColor("#3B3D45"))
        rounded(p,QRectF(pos,3,sw,h-6).translated(0,1),8,QColor(0,0,0,75))
        rounded(p,QRectF(pos,3,sw,h-6),8,gradient,QColor(255,255,255,28))
        p.setPen(QPen(QColor(255,255,255,20),1)); p.drawLine(QPointF(pos+8,4),QPointF(pos+sw-8,4))
        for i,(key,label,icon) in enumerate(self.options):
            active=key==self.current_key
            font=ui_font(12 if len(self.options)>2 else 13,QFont.Weight.DemiBold if active else QFont.Weight.Normal)
            tw=QFontMetrics(font).horizontalAdvance(label); total=tw+22
            start=3+(i+.5)*sw-total/2
            render_duotone_svg(p,icon,start+8,h/2,16,"#E9EEFF" if active else "#9396A3")
            p.setFont(font); p.setPen(QColor(brand.TEXT if active else brand.SECONDARY))
            p.drawText(QRectF(start+22,0,tw+2,h),int(Qt.AlignmentFlag.AlignVCenter),label)
        if self.hasFocus(): focus_ring(p,QRectF(1,1,w-2,h-2),9)


class StudioToggleSwitch(QAbstractButton):
    def __init__(self,checked,on_toggle,active_hex="#51D88A"):
        super().__init__()
        self.on_toggle,self.active_col=on_toggle,QColor(active_hex)
        self.setCheckable(True); super().setChecked(bool(checked))
        self.setFixedSize(46,27); self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._pos=float(bool(checked))
        self._spring=SpringAnimator(self._pos,self._on_spring,stiffness=460,damping=34,parent=self)
        self.clicked.connect(self._clicked)
    def _on_spring(self,v): self._pos=v; self.update()
    def _clicked(self,_=False):
        self._spring.set_target(float(self.isChecked())); self.on_toggle(self.isChecked())
    def setChecked(self,value,animate=True):
        super().setChecked(bool(value))
        if hasattr(self,'_spring'): self._spring.set_target(float(bool(value)),immediate=not animate)
        self.update()
    def keyPressEvent(self,e):
        if e.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter): self.click(); e.accept()
        else: super().keyPressEvent(e)
    def paintEvent(self,e):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t=max(0,min(1,self._pos))
        track=_lerp_qcolor(QColor("#484B54"),self.active_col,t)
        rounded(p,QRectF(1,1,44,25),12.5,track,QColor(0,0,0,45))
        cx=14+18*t
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(0,0,0,65)); p.drawEllipse(QPointF(cx,14.5),10,10)
        gradient=QLinearGradient(0,3,0,24)
        gradient.setColorAt(0,QColor("#FFFFFF")); gradient.setColorAt(1,QColor("#E9EBEF"))
        p.setBrush(gradient); p.drawEllipse(QPointF(cx,13.5),10,10)
        if self.hasFocus(): focus_ring(p,QRectF(0,0,46,27),13)


class _TrafficLight(QAbstractButton):
    def __init__(self,color,symbol,callback,label,parent):
        super().__init__(parent); self.color=QColor(color); self.symbol=symbol
        self.setFixedSize(22,24); self.setAccessibleName(label); self.setToolTip(label)
        self.setCursor(Qt.CursorShape.PointingHandCursor); self.clicked.connect(lambda _=False: callback())
    def paintEvent(self,e):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(self.color.darker(120),.7)); p.setBrush(self.color); p.drawEllipse(QRectF(4,6,12,12))
        if self.underMouse() or self.hasFocus():
            text(p,QRectF(3,3,14,17),self.symbol,11,"#492513",QFont.Weight.DemiBold,Qt.AlignmentFlag.AlignCenter)
    def enterEvent(self,e): self.update()
    def leaveEvent(self,e): self.update()


class _CompactButton(QAbstractButton):
    """Compact window control with a distinct, accessible layout glyph."""
    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self.text_str = 'Kompakt'
        self.setAccessibleName('Kompakt görünüm')
        self.setToolTip('Kompakt görünüme geç')
        self.setFixedSize(90, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.clicked.connect(lambda _=False: callback())

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.isAutoRepeat():
            self.click(); event.accept()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1, 1, self.width()-2, self.height()-2)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0, QColor('#41444C' if self.underMouse() else '#34363D'))
        gradient.setColorAt(1, QColor('#34363D' if self.underMouse() else '#292B31'))
        rounded(p, rect, 8, gradient, QColor('#50535D' if self.underMouse() else '#42444D'))
        font = ui_font(11, QFont.Weight.Medium)
        label_width = QFontMetrics(font).horizontalAdvance(self.text_str)
        start = (self.width() - (12 + 6 + label_width)) / 2
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor('#C4C8D3'), 1.25))
        p.drawRoundedRect(QRectF(start, 8, 12, 10), 2, 2)
        p.drawLine(QPointF(start+3, 12), QPointF(start+9, 12))
        text(p, QRectF(start+18, 0, label_width+1, self.height()), self.text_str,
             11, '#E7E9EF', QFont.Weight.Medium)
        if self.hasFocus():
            focus_ring(p, rect, 8)


class StudioHeaderBanner(QWidget):
    def __init__(self,parent_win,on_mini,on_close,on_sim=None):
        super().__init__(parent_win)
        self.parent_win,self.on_mini,self.on_close,self.on_sim=parent_win,on_mini,on_close,on_sim
        self.live_active=False; self._drag_offset=None; self.setFixedHeight(106)
        self._logo_pix=QPixmap(str(brand.ASSETS/'app_logo.png'))
        bar=QHBoxLayout(); bar.setSpacing(0)
        for color,symbol,callback,label in [('#FF5F57','×',on_close,'Kapat'),
                ('#FEBC2E','−',on_mini,'Kompakt görünüm'),('#28C840','+',on_sim or on_mini,'Simülatör')]:
            bar.addWidget(_TrafficLight(color,symbol,callback,label,self))
        bar.addStretch()
        self.mini_btn=_CompactButton(on_mini,self); bar.addWidget(self.mini_btn)
        self.close_btn=_TrafficLight('#FF5F57','×',on_close,'Kapat',self); self.close_btn.hide()
        layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0); layout.addLayout(bar); layout.addStretch()
    def tick_animation(self,live): self.live_active=live; self.update()
    def paintEvent(self,e):
        p=QPainter(self); p.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform)
        w=self.width()
        if not self._logo_pix.isNull(): p.drawPixmap(QRectF(2,45,52,52),self._logo_pix,QRectF(self._logo_pix.rect()))
        text(p,QRectF(68,46,w-220,48),brand.PRODUCT_NAME,29,brand.TEXT,QFont.Weight.Medium)
        status=QRectF(w-108,59,106,26)
        gradient=QLinearGradient(status.topLeft(),status.bottomLeft())
        gradient.setColorAt(0,QColor('#293832' if self.live_active else '#303138'))
        gradient.setColorAt(1,QColor('#222C28' if self.live_active else '#282A30'))
        rounded(p,status.translated(0,1),10,QColor(0,0,0,45))
        rounded(p,status,10,gradient,QColor('#3C5948' if self.live_active else '#42444C'))
        p.setPen(QPen(QColor(255,255,255,20),1))
        p.drawLine(QPointF(status.left()+12,status.top()+1),QPointF(status.right()-12,status.top()+1))
        color='#A7D8B9' if self.live_active else '#CDD0D8'
        caption='Çeviri açık' if self.live_active else 'Hazır'
        caption_width=QFontMetrics(ui_font(11,QFont.Weight.Medium)).horizontalAdvance(caption)
        content_x=status.center().x()-(6+7+caption_width)/2
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(color))
        p.drawEllipse(QPointF(content_x+3,status.center().y()),3,3)
        text(p,QRectF(content_x+13,status.top(),caption_width+1,status.height()),caption,11,color,QFont.Weight.Medium)
    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton: self._drag_offset=e.globalPosition().toPoint()-self.parent_win.pos()
    def mouseMoveEvent(self,e):
        if self._drag_offset is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.parent_win.move(e.globalPosition().toPoint()-self._drag_offset)
    def mouseReleaseEvent(self,e): self._drag_offset=None


class GlassCard(QFrame):
    def __init__(self,parent=None,*,is_hero=False):
        super().__init__(parent); self.is_hero=is_hero
    def tick_shader(self,angle,live): pass
    def paintEvent(self,e):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient=QLinearGradient(0,0,0,self.height())
        gradient.setColorAt(0,QColor('#25262C' if self.is_hero else '#222329'))
        gradient.setColorAt(1,QColor('#202126' if self.is_hero else '#202126'))
        rounded(p,QRectF(1,1,self.width()-2,self.height()-2),16,gradient,QColor(255,255,255,16))
        p.setPen(QPen(QColor(255,255,255,18),1))
        p.drawLine(QPointF(18,2),QPointF(self.width()-18,2))


class BentoTelemetryCockpit(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent); self.setFixedHeight(74)
        self.live_active=False; self.status_text='Çeviriye hazır'
        self.engine_name='OFFLINE'; self.last_ms=0.; self.block_count=0
        self._samples=deque(maxlen=28)
    def set_status(self,target_status,live): self.status_text=target_status; self.live_active=live; self.update()
    def push_telemetry(self,elapsed_ms,engine_name,block_count):
        self.last_ms=max(0.,elapsed_ms); self.engine_name=engine_name.upper(); self.block_count=block_count
        self._samples.append(self.last_ms); self.update()
    def tick_animation(self,live):
        if live!=self.live_active: self.live_active=live; self.update()
    def paintEvent(self,e):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w=self.width(); split=w*.59
        notice=self.status_text not in ('Çeviriye hazır','Canlı çeviri','Duraklatıldı')
        if notice:
            text(p,QRectF(0,0,w,22),self.status_text,12,'#F2AD9D')
        else:
            text(p,QRectF(0,0,w,22),'İngilizce',12,brand.SECONDARY)
            text(p,QRectF(61,0,30,22),'→',14,brand.MUTED)
            text(p,QRectF(85,0,100,22),'Türkçe',12,brand.TEXT,QFont.Weight.Medium)
        engine={'OFFLINE':'Çevrimdışı','GOOGLE':'Google','DEEPL':'DeepL','OLLAMA':'Ollama'}.get(self.engine_name,self.engine_name.title())
        if not notice:
            text(p,QRectF(w-110,0,110,22),engine,11,brand.SECONDARY,align=Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter)
        p.setPen(QPen(QColor('#3A3C44'),1)); p.drawLine(QPointF(split,33),QPointF(split,70))
        text(p,QRectF(0,29,142,32),f'{self.last_ms:.0f} ms' if self.last_ms else '— ms',25,brand.TEXT,QFont.Weight.Medium,mono=True)
        text(p,QRectF(0,59,120,15),'Son tarama',10,brand.MUTED)
        samples=list(self._samples)
        if len(samples)>1:
            x,y,sw,sh=145.,37.,max(20.,split-160),24.
            low,high=min(samples),max(samples); span=max(20.,high-low)
            pts=[QPointF(x+i*sw/(len(samples)-1),y+sh-(v-low)*sh/span) for i,v in enumerate(samples)]
            line=QPainterPath(pts[0])
            for a,b in zip(pts,pts[1:]):
                mid=(a.x()+b.x())/2; line.cubicTo(QPointF(mid,a.y()),QPointF(mid,b.y()),b)
            p.setPen(QPen(QColor('#7BA8FF'),1.6)); p.drawPath(line)
        ring=QRectF(split+19,32,37,37)
        p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor('#484C57'),1.2)); p.drawEllipse(ring)
        text(p,ring,str(self.block_count),16,brand.TEXT,QFont.Weight.Medium,Qt.AlignmentFlag.AlignCenter,True)
        text(p,QRectF(split+68,32,w-split-68,22),'Çeviri bölgesi',12,brand.TEXT,QFont.Weight.Medium)
        text(p,QRectF(split+68,53,w-split-68,18),'Ekranda' if self.block_count else 'Tarama bekliyor',10,brand.MUTED)


class StudioControlPanelWindow(QWidget):
    def __init__(self):
        super().__init__(None); self.setWindowTitle(brand.PRODUCT_TITLE)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
    def tick_shader(self): pass
    def closeEvent(self,e):
        if hasattr(self,'on_close'): self.on_close()
        e.accept()
    def paintEvent(self,e):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(1,1,self.width()-2,self.height()-2)
        gradient=QLinearGradient(0,0,0,self.height())
        gradient.setColorAt(0,QColor('#1D1E23')); gradient.setColorAt(.3,QColor(brand.WINDOW)); gradient.setColorAt(1,QColor('#141519'))
        rounded(p,rect,23,gradient,QColor('#484A53'))
        p.setPen(QPen(QColor(255,255,255,26),1)); p.drawLine(QPointF(24,2),QPointF(self.width()-24,2))
