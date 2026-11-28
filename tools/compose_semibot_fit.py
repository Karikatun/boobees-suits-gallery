"""Make a pose comparison and, for the two-piece fit, mark the fitted seam."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


parser = argparse.ArgumentParser()
parser.add_argument('output', type=Path)
parser.add_argument('--outfit', action='store_true')
parser.add_argument('--side', action='store_true', help='Show the outfit in three-quarter view')
args = parser.parse_args()
output = args.output
fonts = Path('C:/Windows/Fonts')
bold = ImageFont.truetype(str(fonts / 'segoeuib.ttf'), 32)
regular = ImageFont.truetype(str(fonts / 'segoeui.ttf'), 22)
ink = '#f0ede5'
dim = '#bfc5c5'
background = '#202427'


def load(pose, angle):
    with Image.open(output / f'{pose}-{angle}.png') as img:
        return img.convert('RGB')


views = [('front', 'Спереди'), ('back', 'Со спины')] if args.outfit else [
    ('front', 'Спереди'), ('three-quarter', 'В три четверти')]
if args.outfit and args.side:
    views[1] = ('side', 'В три четверти')
crop = (115, 30, 695, 982) if args.outfit else (207, 4, 693, 996)
width, height = (408, 670) if args.outfit else (354, 722)
pad, gap, group_gap = 24, 8, 28
panel_top = 85
sheet = Image.new('RGB', (2 * pad + 4 * width + 2 * gap + group_gap, panel_top + height + pad), background)
draw = ImageDraw.Draw(sheet)
for j, (pose, label) in enumerate([('stand', 'Стойка'), ('crouch', 'Присед')]):
    left = pad + j * (2 * width + gap + group_gap)
    draw.text((left, 16), label, fill=ink, font=bold)
    for i, (angle, caption) in enumerate(views):
        x = left + i * (width + gap)
        draw.text((x, 55), caption, fill=dim, font=regular)
        image = load(pose, angle)
        panel = image.crop(crop).resize((width, height), Image.Resampling.LANCZOS)
        sheet.paste(panel, (x, panel_top))
sheet.save(output / 'Semibot-poses.png', optimize=True)

if args.outfit:
    raise SystemExit(0)

receipt = json.loads((output / 'fit-receipt.json').read_text(encoding='utf-8'))
detail_size = (555, 555)
header = 63
detail = Image.new('RGB', (2 * detail_size[0] + 3 * pad, detail_size[1] + header + pad), background)
draw = ImageDraw.Draw(detail)
for i, (pose, label) in enumerate([('stand', 'Стойка'), ('crouch', 'Присед')]):
    angle = 'three-quarter'
    x, y = receipt['seamMarkerPixels'][f'{pose}-{angle}']
    left = pad + i * (detail_size[0] + pad)
    top = y - 335
    panel = load(pose, angle).crop((172, top, 727, top + detail_size[1]))
    detail.paste(panel, (left, header))
    draw.text((left, 15), label, fill=ink, font=bold)
    dot_x, dot_y = left + x - 172, header + y - top
    mark_x = left + 478
    draw.line([(dot_x, dot_y), (mark_x - 22, dot_y), (mark_x - 7, dot_y - 16)],
              fill='#8c602c', width=2)
    draw.ellipse((dot_x - 4, dot_y - 4, dot_x + 4, dot_y + 4),
                 fill='#e2b673', outline='#6e522a', width=1)
    draw.text((mark_x - 20, dot_y - 41), 'Стык', fill=ink, font=regular, stroke_width=1, stroke_fill=background)
detail.save(output / 'Semibot-seam.png', optimize=True)
