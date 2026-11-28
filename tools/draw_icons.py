"""Regenerate the original Boo-Bee sprites with Pillow."""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
INK = '#302623'
THREAD = '#a78e70'
CLOTH = '#f0dfbd'
HONEY = '#e5a52e'
LIGHT = '#ffdd70'


def render(size, paint, background=None):
    scale = 4
    image = Image.new('RGBA', (size * scale, size * scale), background)
    draw = ImageDraw.Draw(image)

    def path(points):
        return [(round(x * scale), round(y * scale)) for x, y in points]

    def ellipse(box, fill, outline=INK, width=2):
        draw.ellipse(tuple(round(v * scale) for v in box), fill, outline, width * scale)

    def polygon(points, fill, outline=None, width=2):
        draw.polygon(path(points), fill, outline, width * scale)

    def line(points, fill, width):
        draw.line(path(points), fill, width * scale, joint='curve')

    paint(ellipse, polygon, line)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def antennae(ellipse, polygon, line):
    line([(47, 94), (39, 58), (32, 37)], INK, 10)
    line([(81, 94), (89, 58), (96, 37)], INK, 10)
    ellipse((20, 22, 43, 45), HONEY)
    ellipse((85, 22, 108, 45), HONEY)
    ellipse((24, 25, 32, 32), LIGHT, None)
    ellipse((89, 25, 97, 32), LIGHT, None)
    ellipse((39, 85, 54, 99), THREAD)
    ellipse((74, 85, 89, 99), THREAD)


def hood(ellipse, polygon, line):
    polygon([(20, 102), (22, 73), (29, 49), (42, 29), (54, 22), (64, 20),
             (75, 22), (89, 31), (100, 48), (107, 73), (108, 102), (94, 99),
             (88, 88), (87, 71), (80, 56), (71, 48), (64, 46), (57, 48),
             (48, 56), (41, 72), (40, 89), (34, 99)], CLOTH, INK, 3)
    line([(29, 94), (34, 72), (41, 53), (51, 44), (64, 40), (77, 44),
          (87, 53), (94, 72), (99, 94)], THREAD, 2)


def bodice(ellipse, polygon, line):
    polygon([(47, 23), (81, 23), (85, 33), (96, 42), (102, 57), (91, 72),
             (94, 103), (34, 103), (37, 72), (26, 57), (32, 42), (43, 33)], CLOTH, INK, 3)
    line([(38, 64), (42, 56), (51, 53), (58, 56), (63, 65),
          (70, 56), (78, 53), (87, 56), (91, 64)], THREAD, 2)
    line([(46, 76), (44, 89), (42, 98)], THREAD, 2)
    line([(82, 76), (84, 89), (86, 98)], THREAD, 2)


def sleeve(ellipse, polygon, line):
    polygon([(47, 26), (71, 20), (80, 31), (79, 52), (81, 75), (88, 94),
             (61, 107), (44, 101), (38, 83), (39, 49)], CLOTH, INK, 3)
    line([(47, 35), (47, 57), (48, 79), (54, 89)], THREAD, 2)
    line([(42, 88), (57, 94), (84, 84)], THREAD, 3)


def sock(ellipse, polygon, line):
    polygon([(25, 24), (56, 24), (57, 57), (63, 69), (82, 73), (96, 79),
             (104, 90), (100, 103), (91, 109), (58, 109), (36, 101), (25, 88),
             (22, 71)], HONEY, INK, 3)
    line([(26, 42), (54, 42)], INK, 9)
    line([(25, 63), (58, 63)], INK, 9)
    line([(34, 87), (63, 86), (93, 88)], INK, 9)


def mantle(ellipse, polygon, line):
    sides = [(43, 26), (85, 26), (88, 39), (94, 54), (101, 75), (112, 98),
             (100, 103), (90, 100), (79, 108), (65, 105), (54, 109), (43, 103),
             (30, 106), (17, 98), (26, 77), (31, 59), (38, 44)]
    polygon(sides, CLOTH, INK, 3)
    line([(44, 32), (40, 57), (36, 86)], THREAD, 2)
    line([(57, 34), (53, 56), (50, 92)], THREAD, 2)
    line([(71, 34), (76, 63), (78, 93)], THREAD, 2)
    line([(85, 37), (88, 61), (93, 89)], THREAD, 2)
    line([(23, 87), (31, 92), (43, 89), (53, 95), (66, 91), (78, 96),
          (90, 89), (101, 92), (106, 88)], HONEY, 6)
    line([(21, 93), (31, 98), (43, 95), (53, 101), (66, 97), (78, 102),
          (90, 95), (100, 98), (109, 94)], INK, 4)


def package(ellipse, polygon, line):
    badge = [(128, 16), (224, 70), (224, 185), (128, 241), (32, 185), (32, 70)]
    polygon(badge, '#362928', '#b6813b', 3)
    ellipse((58, 125, 102, 183), CLOTH, INK, 3)
    ellipse((154, 125, 198, 183), CLOTH, INK, 3)
    ellipse((96, 183, 121, 213), HONEY, INK, 3)
    ellipse((135, 183, 160, 213), HONEY, INK, 3)
    line([(98, 201), (120, 201)], INK, 4)
    line([(137, 201), (158, 201)], INK, 4)
    line([(106, 106), (99, 73), (88, 62)], INK, 10)
    line([(150, 106), (157, 73), (168, 62)], INK, 10)
    ellipse((75, 49, 100, 74), HONEY, INK, 3)
    ellipse((156, 49, 181, 74), HONEY, INK, 3)
    polygon([(75, 183), (83, 151), (86, 125), (94, 104), (109, 93),
             (128, 88), (148, 93), (162, 105), (170, 128), (174, 154),
             (181, 183), (164, 193), (150, 188), (128, 197), (108, 189),
             (93, 193)], CLOTH, INK, 4)
    ellipse((105, 113, 121, 141), INK)
    ellipse((135, 113, 151, 141), INK)
    line([(79, 170), (93, 177), (108, 171), (128, 181), (150, 172), (165, 177),
          (177, 170)], HONEY, 7)
    line([(77, 178), (93, 185), (109, 180), (128, 189), (150, 180), (165, 185),
          (179, 178)], INK, 4)


if __name__ == '__main__':
    icons = ROOT / 'src' / 'Icons'
    icons.mkdir(exist_ok=True)
    for name, draw in [('Antennae', antennae), ('Hood', hood), ('Bodice', bodice),
                       ('Sleeve', sleeve), ('Mantle', mantle), ('Sock', sock)]:
        render(128, draw).save(icons / f'{name}.png')
    render(256, package, '#191618').save(ROOT / 'packaging' / 'icon.png')
