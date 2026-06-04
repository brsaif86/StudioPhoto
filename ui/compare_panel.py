"""
ui/compare_panel.py — Aperçu comparatif Avant / Après
======================================================
Charge une image, l'étalonne en mémoire (core.grading.grade_preview) dans un
thread, puis affiche un comparateur à curseur (split slider) Original | Étalonné.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, Signal, QPointF, QRectF
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QFont

from core.grading import grade_preview, SUPPORTED_EXTENSIONS
from ui.style import ACCENT, TEXT2, TEXT3, BG0


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

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self._path = path

    def run(self) -> None:
        try:
            original, graded, mode, metrics = grade_preview(self._path)
            self.done.emit(
                _pil_to_qpixmap(original), _pil_to_qpixmap(graded), mode, metrics
            )
        except Exception as exc:
            self.error.emit(str(exc))


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


# ── Panneau complet ────────────────────────────────────────────────────────────

class ComparePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._build()

    def _build(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(14)

        # Barre supérieure : bouton charger + infos
        top = QHBoxLayout()
        self.btn_load = QPushButton("Charger une image…")
        self.btn_load.setObjectName("btn_browse")
        self.btn_load.setCursor(Qt.PointingHandCursor)
        self.btn_load.setMinimumWidth(160)
        self.btn_load.clicked.connect(self._browse)

        self.lbl_name = QLabel("Aucune image")
        self.lbl_name.setObjectName("progress_file")

        self.lbl_info = QLabel("")
        self.lbl_info.setObjectName("hint_label")

        top.addWidget(self.btn_load)
        top.addSpacing(14)
        top.addWidget(self.lbl_name)
        top.addStretch()
        top.addWidget(self.lbl_info)
        v.addLayout(top)

        # Vue comparateur
        self.view = BeforeAfterView()
        v.addWidget(self.view, stretch=1)

        # Aide
        hint = QLabel("Glisse le curseur central pour comparer · l'aperçu utilise "
                      "exactement le même algorithme que le traitement par lot.")
        hint.setObjectName("hint_label")
        hint.setWordWrap(True)
        v.addWidget(hint)

    # ── Chargement ────────────────────────────────────────────────────────────
    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir une image",
            "", "Images (*.jpg *.jpeg *.JPG *.JPEG)"
        )
        if path:
            self.load_image(Path(path))

    def load_image(self, path: Path) -> None:
        if path.suffix not in SUPPORTED_EXTENSIONS:
            self.lbl_info.setText("Format non supporté (JPEG uniquement)")
            return
        self.lbl_name.setText(path.name)
        self.lbl_info.setText("Étalonnage en cours…")
        self.btn_load.setEnabled(False)

        self._worker = PreviewWorker(path)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, orig_px, graded_px, mode: str, metrics: dict) -> None:
        self.view.set_images(orig_px, graded_px)
        self.btn_load.setEnabled(True)
        if metrics:
            lum = metrics.get("mean_lum", 0)
            lum_label = ("sombre" if lum < 0.45 else "moyenne" if lum < 0.60 else "lumineuse")
            self.lbl_info.setText(
                f"{mode}  ·  lum: {lum_label}  ·  "
                f"cast: {metrics.get('warm_cast', 0):+.2f}  ·  "
                f"hl: {metrics.get('highlight_ratio', 0):.0%}"
            )
        else:
            self.lbl_info.setText(f"{mode}  ·  traitement doux (lift + S-curve)")

    def _on_error(self, msg: str) -> None:
        self.btn_load.setEnabled(True)
        self.lbl_info.setText(f"Erreur : {msg}")
        self.view.clear()
