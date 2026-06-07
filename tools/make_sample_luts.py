"""
tools/make_sample_luts.py — Génère des LUT 3D `.cube` d'exemple (mariage / cinéma).

Chaque LUT est un rendu colorimétrique appliqué à la grille identité, écrit au
format `.cube` standard (ROUGE variant le plus vite). Lancer :

    python tools/make_sample_luts.py

Les fichiers sont écrits dans assets/luts/. Tailles : LUT_3D_SIZE 33 (qualité pro).
"""
from __future__ import annotations

from pathlib import Path
import numpy as np

SIZE = 33
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "luts"

LUM = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


# ── Briques d'étalonnage (opèrent sur un tableau (...,3) en 0..1) ─────────────
def clip01(x: np.ndarray) -> np.ndarray:
    return np.clip(x, 0.0, 1.0)


def luma(c: np.ndarray) -> np.ndarray:
    return (c * LUM).sum(axis=-1, keepdims=True)


def cdl(c, slope=(1, 1, 1), offset=(0, 0, 0), power=(1, 1, 1)):
    """ASC-CDL par canal : out = (c*slope + offset) ^ power."""
    s = np.array(slope, np.float32)
    o = np.array(offset, np.float32)
    p = np.array(power, np.float32)
    return clip01(np.power(clip01(c * s + o), p))


def contrast(c, amount=0.0, pivot=0.45):
    return clip01((c - pivot) * (1.0 + amount) + pivot)


def saturation(c, s=1.0):
    l = luma(c)
    return clip01(l + (c - l) * s)


def temp_tint(c, temp=0.0, tint=0.0):
    """temp>0 = plus chaud (R↑, B↓) ; tint>0 = plus magenta (G↓)."""
    out = c.copy()
    out[..., 0] = c[..., 0] * (1.0 + temp)
    out[..., 2] = c[..., 2] * (1.0 - temp)
    out[..., 1] = c[..., 1] * (1.0 - tint)
    return clip01(out)


def split_tone(c, shadow=(0, 0, 0), highlight=(0, 0, 0), strength=1.0):
    """Teinte les ombres et les hautes lumières séparément (split-toning)."""
    l = luma(c)
    sw = (1.0 - l) ** 2
    hw = l ** 2
    sh = np.array(shadow, np.float32)
    hi = np.array(highlight, np.float32)
    return clip01(c + (sh * sw + hi * hw) * strength)


# ── Les 6 rendus ─────────────────────────────────────────────────────────────
def golden_hour(c):
    c = temp_tint(c, temp=0.06, tint=0.012)
    c = cdl(c, slope=(1.05, 1.005, 0.93), offset=(0.012, 0.006, 0.0),
            power=(0.94, 0.97, 1.03))
    c = split_tone(c, shadow=(0.010, 0.005, -0.005), highlight=(0.050, 0.025, -0.020))
    c = contrast(c, 0.07)
    return saturation(c, 1.06)


def cinematic_teal_orange(c):
    c = contrast(c, 0.12)
    c = split_tone(c, shadow=(-0.025, 0.005, 0.050), highlight=(0.050, 0.020, -0.045))
    c = temp_tint(c, temp=0.02)
    return saturation(c, 1.04)


def light_and_airy(c):
    c = cdl(c, slope=(1.0, 1.0, 1.02), offset=(0.030, 0.035, 0.045),
            power=(0.84, 0.85, 0.86))
    c = contrast(c, -0.10)
    c = temp_tint(c, temp=0.008, tint=-0.006)
    return saturation(c, 0.95)


def soft_romance(c):
    c = cdl(c, slope=(1.03, 1.0, 1.0), offset=(0.025, 0.020, 0.030),
            power=(0.90, 0.92, 0.93))
    c = split_tone(c, shadow=(0.018, 0.0, 0.020), highlight=(0.030, 0.012, 0.0))
    c = contrast(c, -0.05)
    return saturation(c, 0.93)


def vintage_film(c):
    c = cdl(c, slope=(1.04, 1.0, 0.92), offset=(0.045, 0.035, 0.025),
            power=(0.96, 0.95, 1.0))
    c = split_tone(c, shadow=(0.012, 0.022, -0.012), highlight=(0.035, 0.022, -0.030))
    c = contrast(c, -0.04)
    return saturation(c, 0.84)


def moody_cool(c):
    c = temp_tint(c, temp=-0.045, tint=0.012)
    c = cdl(c, slope=(0.97, 1.0, 1.05), offset=(0.0, 0.0, 0.006),
            power=(1.06, 1.03, 0.99))
    c = split_tone(c, shadow=(-0.012, 0.0, 0.030), highlight=(0.0, 0.0, -0.012))
    c = contrast(c, 0.10)
    return saturation(c, 0.90)


LOOKS = {
    "Golden Hour":            golden_hour,
    "Cinematic Teal-Orange":  cinematic_teal_orange,
    "Light & Airy":           light_and_airy,
    "Soft Romance":           soft_romance,
    "Vintage Film":           vintage_film,
    "Moody Cool":             moody_cool,
}


def build_grid(size: int) -> np.ndarray:
    """Grille identité (size,size,size,3) où R varie le plus vite (axe interne)."""
    idx = np.linspace(0.0, 1.0, size, dtype=np.float32)
    b, g, r = np.meshgrid(idx, idx, idx, indexing="ij")  # b=axe0 (lent), r=axe2 (rapide)
    return np.stack([r, g, b], axis=-1)                  # canaux = (R, G, B)


def write_cube(path: Path, title: str, size: int, graded: np.ndarray) -> None:
    flat = graded.reshape(-1, 3)  # ordre C : b lent, r rapide → ordre .cube ✓
    with path.open("w", encoding="utf-8") as f:
        f.write(f"# StudioPhoto — LUT d'exemple : {title}\n")
        f.write(f'TITLE "{title}"\n')
        f.write(f"LUT_3D_SIZE {size}\n")
        np.savetxt(f, flat, fmt="%.6f")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    grid = build_grid(SIZE)
    for title, fn in LOOKS.items():
        out = fn(grid.copy()).astype(np.float32)
        path = OUT_DIR / f"{title}.cube"
        write_cube(path, title, SIZE, out)
        # garde-fou : la LUT ne doit PAS être l'identité
        delta = float(np.abs(out - grid).mean())
        print(f"  ✓ {path.name:30s}  écart moyen / identité = {delta:.4f}")
    print(f"\n{len(LOOKS)} LUT générées dans {OUT_DIR}")


if __name__ == "__main__":
    main()
