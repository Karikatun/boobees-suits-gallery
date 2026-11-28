"""Compose the Thunderstore icon from the available transparent outfit portraits."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


art, output = map(Path, sys.argv[-2:])
edge = 512
back = Image.new("RGB", (edge, edge))
pixels = back.load()
for y in range(edge):
    for x in range(edge):
        side = max(0, min(1, .5 + (x - 256 + .22 * (y - 256)) / 120))
        falloff = max(.30, 1 - .60 * (((x - 256) ** 2 + (y - 210) ** 2) ** .5 / 360))
        icy, amber = (43, 65, 73), (112, 64, 16)
        pixels[x, y] = tuple(round((a * (1 - side) + b * side) * falloff) for a, b in zip(icy, amber))
canvas = back.convert("RGBA")
layouts = (("boo", 148, 420, 250), ("sneaker", 369, 411, 250))
if (art / "winter.png").is_file():
    layouts = (("boo", 92, 393, 159), ("sneaker", 250, 373, 153), ("winter", 418, 406, 176))
for name, x, size, width in layouts:
    figure = Image.open(art / f"{name}.png").convert("RGBA")
    figure = figure.crop(figure.getchannel("A").getbbox())
    figure.thumbnail((width, size), Image.Resampling.LANCZOS)
    position = (x - figure.width // 2, 449 - figure.height)
    shade = Image.new("RGBA", canvas.size)
    outline = Image.new("RGB", figure.size, (8, 10, 12)).convert("RGBA")
    outline.putalpha(figure.getchannel("A"))
    shade.alpha_composite(outline, (position[0] + 4, position[1] + 8))
    canvas.alpha_composite(shade.filter(ImageFilter.GaussianBlur(7)))
    canvas.alpha_composite(figure, position)
draw = ImageDraw.Draw(canvas)
draw.line((86, 476, 426, 476), fill=(226, 164, 59, 210), width=4)
canvas.resize((256, 256), Image.Resampling.LANCZOS).convert("RGB").save(output, optimize=True)
