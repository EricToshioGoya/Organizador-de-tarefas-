"""Gera os ícones PNG do PWA (RNF20) a partir do desenho de web/icons/icon.svg.

Uso: python tools/make_icons.py   (requer Pillow — requirements-dev.txt)
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "icons"
FILL = (29, 29, 27, 255)  # grafite (--accent)
INK = (255, 255, 255, 255)


def draw_icon(size: int, *, maskable: bool = False) -> Image.Image:
    scale = 4  # desenha maior e reduz: bordas suaves
    s = size * scale
    unit = s / 64
    image = Image.new("RGBA", (s, s), FILL if maskable else (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if not maskable:
        draw.rounded_rectangle((0, 0, s - 1, s - 1), radius=16 * unit, fill=FILL)

    inset = 10 * unit if maskable else 0  # zona segura do ícone mascarável
    span = (s - 2 * inset) / 64

    def pt(x: float, y: float) -> tuple[float, float]:
        return (inset + x * span, inset + y * span)

    def stroke(points: list[tuple[float, float]], width: int, color: tuple[int, int, int, int]) -> None:
        draw.line(points, fill=color, width=width, joint="curve")
        for x, y in (points[0], points[-1]):
            r = width / 2
            draw.ellipse((x - r, y - r, x + r, y + r), fill=color)

    stroke([pt(18, 34.5), pt(27, 43.5), pt(47, 22.5)], round(6 * span), INK)
    faded = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(faded)
    stroke([pt(18, 22.5), pt(29, 22.5)], round(5 * span), (255, 255, 255, 115))
    image.alpha_composite(faded)
    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    draw_icon(192).save(OUT / "icon-192.png")
    draw_icon(512).save(OUT / "icon-512.png")
    draw_icon(512, maskable=True).save(OUT / "maskable-512.png")
    apple = Image.new("RGBA", (180, 180), FILL)
    apple.alpha_composite(draw_icon(180))
    apple.convert("RGB").save(OUT / "apple-touch-icon.png")
    print("Ícones gerados em", OUT)


if __name__ == "__main__":
    main()
