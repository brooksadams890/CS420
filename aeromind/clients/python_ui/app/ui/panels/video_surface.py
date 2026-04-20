from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QWidget


class _ReticleOverlay(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        center = self.rect().center()
        painter.setPen(QPen(QColor(125, 211, 252, 28), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(center, 56, 56)
        painter.drawEllipse(center, 104, 104)

        painter.setPen(QPen(QColor(148, 163, 184, 34), 1))
        painter.drawLine(center.x() - 160, center.y(), center.x() - 84, center.y())
        painter.drawLine(center.x() + 84, center.y(), center.x() + 160, center.y())
        painter.drawLine(center.x(), center.y() - 160, center.x(), center.y() - 84)
        painter.drawLine(center.x(), center.y() + 84, center.x(), center.y() + 160)

        frame_color = QColor(148, 163, 184, 24)
        painter.setPen(QPen(frame_color, 1))
        inset = 28
        arm = 48
        painter.drawLine(inset, inset, inset + arm, inset)
        painter.drawLine(inset, inset, inset, inset + arm)
        painter.drawLine(self.width() - inset - arm, inset, self.width() - inset, inset)
        painter.drawLine(self.width() - inset, inset, self.width() - inset, inset + arm)
        painter.drawLine(inset, self.height() - inset, inset + arm, self.height() - inset)
        painter.drawLine(inset, self.height() - inset - arm, inset, self.height() - inset)
        painter.drawLine(self.width() - inset - arm, self.height() - inset, self.width() - inset, self.height() - inset)
        painter.drawLine(self.width() - inset, self.height() - inset - arm, self.width() - inset, self.height() - inset)


class VideoSurface(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("videoSurface")
        self.setAutoFillBackground(True)
        self._is_live = False
        self._current_status = "No Signal"
        self._compact_mode = False
        self._latest_video_pixmap = QPixmap()
        self._latest_gesture_preview_pixmap = QPixmap()

        palette = self.palette()
        palette.setColor(QPalette.Window, QColor("#020617"))
        self.setPalette(palette)

        self.video_label = QLabel("", self)
        self.video_label.setObjectName("videoSurfaceLabel")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setScaledContents(False)

        self.placeholder_label = QLabel("NO DRONE FEED", self)
        self.placeholder_label.setObjectName("videoSurfaceLabel")
        self.placeholder_label.setAlignment(Qt.AlignCenter)

        self.placeholder_subtext = QLabel("Waiting for MJPEG stream", self)
        self.placeholder_subtext.setObjectName("videoSurfaceSubtext")
        self.placeholder_subtext.setAlignment(Qt.AlignCenter)

        self.reticle_overlay = _ReticleOverlay(self)
        self.reticle_overlay.raise_()

        self.overlay_container = QWidget(self)
        self.overlay_container.setObjectName("videoOverlayContainer")
        self.overlay_container.setAttribute(Qt.WA_StyledBackground, False)
        self.overlay_container.setStyleSheet("background: transparent;")
        self.overlay_container.raise_()

        self.stream_status_label = QLabel("NO SIGNAL", self.overlay_container)
        self.stream_status_label.setObjectName("videoStatusBadge")
        self.stream_status_label.setAlignment(Qt.AlignCenter)
        self.stream_status_label.setProperty("compact", False)
        self.stream_status_label.raise_()

        self.gesture_hud_label = QLabel("", self.overlay_container)
        self.gesture_hud_label.setObjectName("gestureLiveHud")
        self.gesture_hud_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.gesture_hud_label.setWordWrap(True)
        self.gesture_hud_label.setProperty("compact", False)
        self.gesture_hud_label.hide()
        self.gesture_hud_label.raise_()

        self.gesture_preview_label = QLabel("", self.overlay_container)
        self.gesture_preview_label.setObjectName("gesturePreviewLabel")
        self.gesture_preview_label.setAlignment(Qt.AlignCenter)
        self.gesture_preview_label.setScaledContents(False)
        self.gesture_preview_label.setStyleSheet(
            "background-color: rgba(2, 6, 23, 210);"
            "border: 1px solid rgba(125, 211, 252, 170);"
            "border-radius: 10px;"
        )
        self.gesture_preview_label.setText("Gesture cam")
        self.gesture_preview_label.hide()
        self.gesture_preview_label.raise_()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.video_label.setGeometry(self.rect())
        self.placeholder_label.setGeometry(0, max(0, self.height() // 2 - 26), self.width(), 24)
        self.placeholder_subtext.setGeometry(0, max(0, self.height() // 2 + 2), self.width(), 18)
        self.reticle_overlay.setGeometry(self.rect())
        self.overlay_container.setGeometry(self.rect())
        badge_width = 102 if self._compact_mode else 118
        badge_height = 24 if self._compact_mode else 28
        badge_margin = 14 if self._compact_mode else 18
        self.stream_status_label.setGeometry(self.width() - badge_width - badge_margin, badge_margin, badge_width, badge_height)
        hud_margin = 14 if self._compact_mode else 18
        hud_width = min(280 if self._compact_mode else 320, max(180, self.width() // 3))
        hud_height = 108 if self._compact_mode else 126
        self.gesture_hud_label.setGeometry(hud_margin, hud_margin, hud_width, hud_height)
        preview_width = 300 if not self._compact_mode else 240
        preview_height = 220 if not self._compact_mode else 170
        preview_x = self.width() - preview_width - hud_margin
        preview_top_offset = badge_margin + badge_height + 12
        preview_y = preview_top_offset
        self.gesture_preview_label.setGeometry(preview_x, preview_y, preview_width, preview_height)

    def set_compact_mode(self, compact: bool) -> None:
        compact = bool(compact)
        if compact == self._compact_mode:
            return
        self._compact_mode = compact
        self.stream_status_label.setProperty("compact", compact)
        self.gesture_hud_label.setProperty("compact", compact)
        self.stream_status_label.style().unpolish(self.stream_status_label)
        self.stream_status_label.style().polish(self.stream_status_label)
        self.gesture_hud_label.style().unpolish(self.gesture_hud_label)
        self.gesture_hud_label.style().polish(self.gesture_hud_label)
        self.stream_status_label.update()
        self.gesture_hud_label.update()
        self.updateGeometry()

    def set_video_pixmap(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            self.video_label.setPixmap(QPixmap())
            self.set_stream_live(False)
            return

        self._latest_video_pixmap = pixmap.copy()
        scaled = pixmap.scaled(
            self.video_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.video_label.setPixmap(scaled)
        self.set_stream_live(True)

    def set_stream_status(self, text: str) -> None:
        self._current_status = text.strip() if text else "No Signal"
        status_text = self._current_status.upper()
        self.stream_status_label.setText(status_text)

        if self._current_status == "Live":
            self.set_stream_live(True)
            return

        self.set_stream_live(False)

        if self._current_status == "Connecting":
            self.placeholder_label.setText("CONNECTING TO DRONE FEED")
            self.placeholder_subtext.setText("Opening MJPEG stream")
        elif self._current_status == "Reconnecting":
            self.placeholder_label.setText("RECONNECTING")
            self.placeholder_subtext.setText("Restoring MJPEG stream")
        elif self._current_status == "Stopped":
            self.placeholder_label.setText("FEED STOPPED")
            self.placeholder_subtext.setText("Video worker stopped")
        else:
            self.placeholder_label.setText("NO DRONE FEED")
            self.placeholder_subtext.setText("Waiting for MJPEG stream")

    def set_stream_live(self, is_live: bool) -> None:
        self._is_live = is_live
        has_pixmap = self.video_label.pixmap() is not None and not self.video_label.pixmap().isNull()

        if is_live and has_pixmap:
            self.placeholder_label.hide()
            self.placeholder_subtext.hide()
            self.reticle_overlay.hide()
            return

        self.video_label.setPixmap(QPixmap())
        self.placeholder_label.show()
        self.placeholder_subtext.show()
        self.reticle_overlay.show()

    def set_gesture_hud_text(self, text: str, *, visible: bool) -> None:
        if visible and text.strip():
            self.gesture_hud_label.setText(text)
            self.gesture_hud_label.show()
            return
        self.gesture_hud_label.clear()
        self.gesture_hud_label.hide()

    def set_gesture_preview_pixmap(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            self._latest_gesture_preview_pixmap = QPixmap()
            self.gesture_preview_label.clear()
            self.gesture_preview_label.setText("Gesture cam")
            self.gesture_preview_label.hide()
            return

        self._latest_gesture_preview_pixmap = pixmap.copy()
        scaled = pixmap.scaled(
            self.gesture_preview_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.gesture_preview_label.setPixmap(scaled)
        self.gesture_preview_label.show()

    def latest_video_pixmap(self) -> QPixmap:
        if not self._latest_video_pixmap.isNull():
            return self._latest_video_pixmap.copy()
        pixmap = self.video_label.pixmap()
        if pixmap is None:
            return QPixmap()
        return pixmap.copy()

    def latest_gesture_preview_pixmap(self) -> QPixmap:
        if not self._latest_gesture_preview_pixmap.isNull():
            return self._latest_gesture_preview_pixmap.copy()
        pixmap = self.gesture_preview_label.pixmap()
        if pixmap is None:
            return QPixmap()
        return pixmap.copy()
