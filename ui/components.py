from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QEvent, QPoint, QPropertyAnimation, QRect, QSize, Qt
from PyQt6.QtGui import QFontMetrics, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .tokens import MOTION_TOKENS, mono_font


class GlassCard(QFrame):
    def __init__(self, title: str = "", subtitle: str = "", eyebrow: str = "", variant: str = "default", parent=None):
        super().__init__(parent)
        self.setObjectName("GlassCard")
        self.setProperty("variant", variant)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(14, 14, 14, 14)
        self._layout.setSpacing(10)

        self.eyebrow_label = None
        self.title_label = None
        self.subtitle_label = None
        if eyebrow or title or subtitle:
            header = QVBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.setSpacing(2)
            if eyebrow:
                self.eyebrow_label = QLabel(eyebrow)
                self.eyebrow_label.setProperty("role", "eyebrow")
                header.addWidget(self.eyebrow_label)
            if title:
                self.title_label = QLabel(title)
                self.title_label.setProperty("role", "cardTitle")
                header.addWidget(self.title_label)
            if subtitle:
                self.subtitle_label = QLabel(subtitle)
                self.subtitle_label.setProperty("role", "cardSubtitle")
                self.subtitle_label.setWordWrap(True)
                header.addWidget(self.subtitle_label)
            self._layout.addLayout(header)

    @property
    def layout_root(self):
        return self._layout

    def set_title(self, text: str):
        if self.title_label is not None:
            self.title_label.setText(str(text or ""))

    def set_subtitle(self, text: str):
        if self.subtitle_label is not None:
            self.subtitle_label.setText(str(text or ""))


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin: int = 0, h_spacing: int = 8, v_spacing: int = 8):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item: QLayoutItem):
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:
        width = 0
        height = 0
        for item in self._items:
            hint = item.sizeHint()
            width += hint.width()
            height = max(height, hint.height())
        if self._items:
            width += self._h_spacing * (len(self._items) - 1)
        margins = self.contentsMargins()
        return QSize(width + margins.left() + margins.right(), height + margins.top() + margins.bottom())

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def invalidate(self):
        super().invalidate()

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0
        right_edge = max(effective.right(), effective.x())

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width()
            if line_height > 0 and next_x > right_edge:
                x = effective.x()
                y += line_height + self._v_spacing
                next_x = x + hint.width()
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x + self._h_spacing
            line_height = max(line_height, hint.height())

        return (y - rect.y()) + line_height + margins.bottom()


class WrapRow(QWidget):
    def __init__(self, parent=None, h_spacing: int = 8, v_spacing: int = 8):
        super().__init__(parent)
        self._layout = FlowLayout(self, h_spacing=h_spacing, v_spacing=v_spacing)
        self.setLayout(self._layout)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def addWidget(self, widget: QWidget):
        self._layout.addWidget(widget)
        self.refresh_layout()

    def addStretch(self):
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        spacer.setMaximumWidth(0)
        spacer.setVisible(False)
        self._layout.addWidget(spacer)
        self.refresh_layout()

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._layout.heightForWidth(width)

    def sizeHint(self) -> QSize:
        return self._layout.sizeHint()

    def minimumSizeHint(self) -> QSize:
        return self._layout.minimumSize()

    def refresh_layout(self):
        self._layout.invalidate()
        self.updateGeometry()
        if self.layout() is not None:
            self.layout().activate()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in {QEvent.Type.FontChange, QEvent.Type.StyleChange, QEvent.Type.PaletteChange}:
            self.refresh_layout()


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full_text = str(text or "")
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setWordWrap(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.set_full_text(text)

    def set_full_text(self, text: str):
        self._full_text = str(text or "")
        self.setToolTip(self._full_text)
        self._update_elide()

    def full_text(self) -> str:
        return self._full_text

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_elide()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in {QEvent.Type.FontChange, QEvent.Type.StyleChange, QEvent.Type.PaletteChange}:
            self._update_elide()

    def refresh_elide(self):
        self._update_elide()

    def _update_elide(self):
        metrics = QFontMetrics(self.font())
        width = max(24, self.contentsRect().width())
        self.setText(metrics.elidedText(self._full_text or "--", Qt.TextElideMode.ElideMiddle, width))


class AccentButton(QPushButton):
    def __init__(self, text: str = "", parent=None, accent_kind: str = "primary"):
        super().__init__(text, parent)
        self.setProperty("accent", True)
        self.setProperty("accentKind", str(accent_kind or "primary"))

    def set_accent_kind(self, accent_kind: str):
        self.setProperty("accentKind", str(accent_kind or "primary"))
        self.style().unpolish(self)
        self.style().polish(self)


class StatusPill(QLabel):
    def __init__(self, text: str, tone: str = "muted", parent=None):
        super().__init__(text, parent)
        self.setObjectName("StatusPill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setContentsMargins(10, 4, 10, 4)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.set_tone(tone)
        self.set_density(False)

    def set_tone(self, tone: str):
        self.setProperty("tone", str(tone or "muted"))
        self.style().unpolish(self)
        self.style().polish(self)

    def set_density(self, compact: bool):
        self.setProperty("density", "compact" if compact else "cozy")
        self.style().unpolish(self)
        self.style().polish(self)


class MetricTile(QFrame):
    def __init__(self, label: str, value: str = "--", parent=None, tone: str = "default"):
        super().__init__(parent)
        self.setObjectName("MetricTile")
        self.setProperty("tone", str(tone or "default"))
        self.setMinimumHeight(88)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(4)
        self.lbl = QLabel(label)
        self.lbl.setProperty("role", "metricLabel")
        self.val = QLabel(value)
        self.val.setProperty("role", "metricValue")
        self.val.setWordWrap(True)
        lay.addWidget(self.lbl)
        lay.addWidget(self.val)
        lay.addStretch(1)
        self.set_density(False, False)

    def set_value(self, value: str):
        self.val.setText(str(value))

    def set_tone(self, tone: str):
        self.setProperty("tone", str(tone or "default"))
        self.style().unpolish(self)
        self.style().polish(self)

    def set_density(self, compact: bool, narrow: bool):
        self.setProperty("density", "compact" if compact else "cozy")
        self.setProperty("narrow", "true" if narrow else "false")
        self.setMinimumHeight(68 if compact and narrow else 74 if compact else 82 if narrow else 88)
        self.style().unpolish(self)
        self.style().polish(self)


class InspectorField(QWidget):
    def __init__(self, label: str, widget: QWidget, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        lbl = QLabel(label)
        lbl.setProperty("role", "muted")
        lay.addWidget(lbl)
        lay.addWidget(widget)


class Toast(QFrame):
    def __init__(self, text: str, tone: str = "info", parent=None):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setProperty("tone", str(tone or "info"))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        body = QLabel(text)
        body.setWordWrap(True)
        lay.addWidget(body)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(MOTION_TOKENS["micro_ms"])
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def fade_in(self):
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def fade_out(self):
        self._anim.stop()
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()


class RunCard(GlassCard):
    def __init__(self, run_id: str, run_path: str, title: str = "", parent=None):
        super().__init__(title="", variant="archive", parent=parent)
        self.run_id = run_id
        self.run_path = run_path

        head_row = QHBoxLayout()
        self.title_label = QLabel(title or run_id)
        self.title_label.setProperty("role", "cardTitle")
        self.status = StatusPill("CHECK", "muted")
        head_row.addWidget(self.title_label, 1)
        head_row.addWidget(self.status, 0, Qt.AlignmentFlag.AlignRight)
        self.layout_root.addLayout(head_row)

        self.thumb = QLabel("No Preview")
        self.thumb.setObjectName("RunThumb")
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setMinimumHeight(164)
        self.thumb.setWordWrap(True)
        self.layout_root.addWidget(self.thumb)

        self.summary = QLabel("")
        self.summary.setProperty("role", "cardSubtitle")
        self.summary.setWordWrap(True)
        self.layout_root.addWidget(self.summary)

        self.meta = QLabel("")
        self.meta.setFont(mono_font(9))
        self.meta.setProperty("role", "muted")
        self.meta.setWordWrap(True)
        self.layout_root.addWidget(self.meta)

    def set_summary(self, text: str):
        self.summary.setText(text)

    def set_meta(self, text: str):
        self.meta.setText(text)

    def set_status(self, text: str, tone: str):
        self.status.setText(text)
        self.status.set_tone(tone)

    def set_thumbnail(self, image_path: str):
        if not image_path:
            return
        pix = QPixmap(image_path)
        if pix.isNull():
            return
        self.thumb.setPixmap(
            pix.scaled(360, 168, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        )
