"""Generate the knit atlases shared by the New Year sweater, sleeve pair and abdomen."""

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


OUTPUT = Path(__file__).resolve().parents[1] / "dist/new-year-bee" / "textures"
SIZE = 1024
SPRUCE = (31, 70, 51)
GOLD = (222, 166, 61)


def snowflake():
    mask = Image.new("L", (25, 25))
    paint = ImageDraw.Draw(mask)
    for angle in range(0, 360, 45):
        a = math.radians(angle)
        x, y = math.cos(a), math.sin(a)
        length = 11 if angle % 90 == 0 else 9
        end = (round(12 + length*x), round(12 + length*y))
        paint.line((12, 12, *end), fill=255, width=1)
        for sign in (-1, 1):
            b = a + sign * .78
            start = (12 + (length - 3) * x, 12 + (length - 3) * y)
            end = (start[0] - 4 * math.cos(b), start[1] - 4 * math.sin(b))
            paint.line(tuple(round(i) for i in (*start, *end)), fill=255, width=1)
    paint.rectangle((11, 11, 13, 13), fill=255)
    return mask


def repeat_motif(mask, motif, center_y, width, height, repeat):
    shape = motif.resize((width, height), Image.Resampling.NEAREST)
    for i in range(repeat):
        center_x = round((i + .5) * SIZE / repeat)
        mask.paste(shape, (center_x - width // 2, center_y - height // 2), shape)


def stitch_band(mask, y, count, height, alternating=False):
    pen = ImageDraw.Draw(mask)
    step = SIZE / count
    for i in range(count):
        x = round((i + .5) * step)
        dy = -height // 2 if alternating and i % 2 else 0
        pen.polygon([(x-4,y+dy+height//2),(x,y+dy),(x+4,y+dy+height//2),(x,y+dy+height)], fill=196)


def create(kind, yarn):
    mask = Image.new("L", (SIZE, SIZE))
    if kind == "sweater":
        repeat_motif(mask, snowflake(), 390, 96, 268, 5)
        for y, n, h in ((218, 76, 12), (241, 62, 10), (540, 62, 13), (564, 76, 12)):
            stitch_band(mask, y, n, h, alternating=True)
    elif kind == "sleeve":
        repeat_motif(mask, snowflake(), 690, 182, 156, 2)
        for y in (573, 595, 791):
            stitch_band(mask, y, 62, 11, alternating=True)
    else:
        ImageDraw.Draw(mask).rectangle((0, 470, SIZE-1, 789), fill=255)
    alpha = np.asarray(mask, dtype=float) / 255
    primary, dye = (GOLD, (54, 35, 25)) if kind == "abdomen" else (SPRUCE, GOLD)
    if kind == "sweater":
        rib = np.where(np.indices(alpha.shape)[0] >= 906, 1. + .066*np.cos(np.indices(alpha.shape)[1]*math.tau/9), 1.)
    elif kind == "sleeve":
        rib = np.where(np.indices(alpha.shape)[0] < 128, 1. + .066*np.cos(np.indices(alpha.shape)[1]*math.tau/11), 1.)
    else:
        rib = 1.
    color = np.asarray(primary) + (np.asarray(dye) - primary) * alpha[:, :, None]
    multiplier = yarn * rib
    pixels = np.uint8(np.clip(color * multiplier[:, :, None], 0, 255))
    Image.fromarray(pixels, "RGB").save(OUTPUT / f"{kind}.png")


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=True)
    yy, xx = np.indices((SIZE, SIZE), dtype=float)
    phase = yy * math.tau / 9. + 1.35 * np.cos(xx * math.tau / 10.)
    yarn = 1 + .07 * np.sin(phase) + .052 * np.cos(xx * math.tau / 10.)
    yarn += .025 * np.random.default_rng(11).normal(size=phase.shape)
    for piece in ("sweater", "sleeve", "abdomen"):
        create(piece, yarn)
