"""Create presentation sheets from the final item and native-pose Blender renders."""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUTPUT = Path(__file__).resolve().parents[1] / "dist/bee-sneaker-set"
FONT_DIR = Path("C:/Windows/Fonts")


def font(size, bold=False):
    return ImageFont.truetype(str(FONT_DIR / ("segoeuib.ttf" if bold else "segoeui.ttf")), size)


def sheet(items, directory, title, subtitle, filename, columns, cell, alpha=False):
    pad, gap, header, caption_height = 26, 12, 114, 48
    rows = math.ceil(len(items) / columns)
    width = columns * cell[0] + (columns - 1) * gap + 2 * pad
    height = header + rows * (cell[1] + caption_height) + (rows - 1) * gap + pad
    canvas = Image.new("RGB", (width, height), "#1c2226")
    draw = ImageDraw.Draw(canvas)
    draw.text((pad, 17), title, fill="#f6ecd7", font=font(45, True))
    draw.text((pad + 2, 75), subtitle, fill="#a8b7bd", font=font(23))
    for i, (basename, label) in enumerate(items):
        x = pad + (i % columns) * (cell[0] + gap)
        y = header + (i // columns) * (cell[1] + caption_height + gap)
        image = Image.open(OUTPUT / directory / f"{basename}.png").convert("RGBA" if alpha else "RGB")
        image.thumbnail(cell, Image.Resampling.LANCZOS)
        if alpha:
            draw.rectangle((x, y, x + cell[0], y + cell[1]), fill="#c8c5bd")
        xy = (x + (cell[0] - image.width) // 2, y + (cell[1] - image.height) // 2)
        canvas.paste(image, xy, image if alpha else None)
        draw.text((x + 6, y + cell[1] + 5), label, fill="#f0deae", font=font(22, True))
    canvas.save(OUTPUT / filename, optimize=True)


items = [
    ("antennae", "Усики"), ("sweater", "Вязаный свитер"),
    ("sleeve-left", "Левый рукав"), ("sleeve-right", "Правый рукав"),
    ("abdomen", "Полосатое брюшко"), ("wings", "Крылья"),
    ("shoe-left", "Левый кед"), ("shoe-right", "Правый кед"),
]


if __name__ == "__main__":
    sheet(items, "concepts", "Пчела в кедах", "Отдельные макеты для Meshy 7.1",
          "concepts.png", 4, (320, 293), alpha=True)
    if not (OUTPUT / "renders" / "crouch-up-three-quarter.png").is_file():
        raise SystemExit
    sheet(items, "renders", "Пчела в кедах", "Восемь оптимизированных моделей Meshy 7.1",
          "items.png", 4, (300, 300))
    if (OUTPUT / "sleeve-check.json").is_file():
        sheet([("sleeve-left", "Левый рукав"), ("sleeve-right", "Правый рукав")],
              "renders", "Полные рукава", "Закрытые плечи и манжеты в цвет свитера",
              "sleeves.png", 2, (460, 390))
    sheet([
        ("stand-front", "Стойка · спереди"), ("stand-three-quarter", "Стойка · ¾"),
        ("stand-rear", "Стойка · сзади"), ("crouch-front", "Присед · спереди"),
        ("crouch-three-quarter", "Присед · ¾"), ("crouch-rear", "Присед · сзади"),
    ], "renders", "Пчела в кедах на семиботе", "Стойка и присед · три ракурса",
          "assembly.png", 3, (365, 452))
    sheet([
        ("stand-down-three-quarter", "Стойка · вниз"),
        ("stand-up-three-quarter", "Стойка · вверх"),
        ("crouch-down-three-quarter", "Присед · вниз"),
        ("crouch-up-three-quarter", "Присед · вверх"),
    ], "renders", "Проверка посадки в наклонах", "Штатные позы рига, снятые в R.E.P.O. 0.5.3",
          "tilts.png", 4, (330, 409))
