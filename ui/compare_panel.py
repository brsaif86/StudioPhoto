"""
ui/compare_panel.py — Widgets d'aperçu comparatif Avant / Après
================================================================
Composants réutilisés par l'onglet Étalonnage :
  - PreviewWorker   : étalonne une image EN MÉMOIRE dans un QThread.
  - BeforeAfterView : vue à curseur (split slider) Original | Étalonné.
"""

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QThread, Signal, QPointF, QRectF
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QFont

from core.grading import grade_preview
from ui.style import ACCENT, TEXT3, BG0


# ── Conversion PIL → QPixmap ───────────────────────────────────────────────────

def _pil_to_qpixmap(pil_img) -> QPixmap:
    rgb = pil_img.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


# ── Thread d'aperçu ────────────────────────────────────────────────────────────

class PreviewWorker(QThread):
    done  = Signal(object, object, str, dict)   # (orig_px, graded_px, mode, metrics)
    error = Signal(str)

    def __init__(self, path, profile: dict = None, edit=None, parent=None):
        super().__init__(parent)
        self._path = path
        self._profile = profile
        self._edit = edit

    def run(self) -> None:
        try:
            original, graded, mode, metrics = grade_preview(
                self._path, profile=self._profile, edit=self._edit
            )
            self.done.emit(
                _pil_to_qpixmap(original), _pil_to_qpixmap(graded), mode, metrics
            )
        except Exception as exc:
            self.error.emit(str(exc))


class ProfileWorker(QThread):
    """Calcule le profil moyen d'un dossier (mode série cohérente) hors UI."""
    done = Signal(object)   # dict | None

    def __init__(self, files: list, parent=None):
        super().__init__(parent)
        self._files = files

    def run(self) -> None:
        try:
            from core.grading import compute_folder_profile
            self.done.emit(compute_folder_profile(self._files))
        except Exception:
            self.done.emit(None)


class ExportWorker(QThread):
    """Enregistre l'image courante en plein format avec les réglages actifs."""
    done = Signal(bool, str)   # (succès, message)

    def __init__(self, src, dst, profile, edit, quality, parent=None):
        super().__init__(parent)
        self._src, self._dst = src, dst
        self._profile, self._edit, self._quality = profile, edit, quality

    def run(self) -> None:
        from core.grading import process_image
        msg = process_image(
            Path(self._src), Path(self._dst), skip_existing=False,
            quality=self._quality, profile=self._profile, edit=self._edit,
        )
        self.done.emit("✗" not in msg, msg)


# ── Vue comparateur à curseur ──────────────────────────────────────────────────

class BeforeAfterView(QWidget):
    """Affiche original (gauche) et étalonné (droite) séparés par un curseur."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._orig: QPixmap | None = None
        self._graded: QPixmap | None = None
        self._split = 0.5          # position du curseur 0..1
        self._dragging = False
        self.setMinimumHeight(360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.SplitHCursor)

    def set_images(self, orig: QPixmap, graded: QPixmap) -> None:
        self._orig = orig
        self._graded = graded
        self.update()

    def clear(self) -> None:
        self._orig = self._graded = None
        self.update()

    # ── Calcul du rectangle d'affichage (letterbox) ───────────────────────────
    def _target_rect(self) -> QRectF:
        if not self._orig:
            return QRectF()
        pw, ph = self._orig.width(), self._orig.height()
        avail_w, avail_h = self.width(), self.height()
        scale = min(avail_w / pw, avail_h / ph)
        w, h = pw * scale, ph * scale
        x = (avail_w - w) / 2
        y = (avail_h - h) / 2
        return QRectF(x, y, w, h)

    # ── Peinture ────────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(BG0))

        if not self._orig or not self._graded:
            p.setPen(QColor(TEXT3))
            p.setFont(QFont("Segoe UI", 12))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Charge une image pour comparer\nl'original et l'étalonnage")
            return

        p.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = self._target_rect()
        split_x = rect.x() + rect.width() * self._split

        # Étalonné (fond complet)
        p.drawPixmap(rect, self._graded, QRectF(self._graded.rect()))

        # Original (partie gauche, clippée jusqu'au curseur)
        left_rect = QRectF(rect.x(), rect.y(), split_x - rect.x(), rect.height())
        p.save()
        p.setClipRect(left_rect)
        p.drawPixmap(rect, self._orig, QRectF(self._orig.rect()))
        p.restore()

        # Ligne de séparation + poignée
        pen = QPen(QColor(ACCENT), 2)
        p.setPen(pen)
        p.drawLine(QPointF(split_x, rect.y()), QPointF(split_x, rect.y() + rect.height()))

        # Poignée centrale
        cy = rect.y() + rect.height() / 2
        p.setBrush(QColor(ACCENT))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(split_x, cy), 9, 9)
        p.setPen(QPen(QColor("#0D0D0D"), 1.5))
        p.drawLine(QPointF(split_x - 3, cy), QPointF(split_x + 3, cy))

        # Étiquettes AVANT / APRÈS
        p.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
        self._tag(p, "AVANT", rect.x() + 10, rect.y() + 10, Qt.AlignLeft)
        self._tag(p, "APRÈS", rect.x() + rect.width() - 10, rect.y() + 10, Qt.AlignRight)

    def _tag(self, p: QPainter, text: str, x: float, y: float, align) -> None:
        metrics = p.fontMetrics()
        tw = metrics.horizontalAdvance(text) + 16
        th = metrics.height() + 6
        rx = x if align == Qt.AlignLeft else x - tw
        bg = QRectF(rx, y, tw, th)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawRoundedRect(bg, 3, 3)
        p.setPen(QColor("#EBEBEB"))
        p.drawText(bg, Qt.AlignCenter, text)

    # ── Interaction curseur ───────────────────────────────────────────────────
    def _update_split(self, x: float) -> None:
        rect = self._target_rect()
        if rect.width() <= 0:
            return
        self._split = min(1.0, max(0.0, (x - rect.x()) / rect.width()))
        self.update()

    def mousePressEvent(self, e):
        if self._orig:
            self._dragging = True
            self._update_split(e.position().x())

    def mouseMoveEvent(self, e):
        if self._dragging:
            self._update_split(e.position().x())

    def mouseReleaseEvent(self, e):
        self._dragging = False
