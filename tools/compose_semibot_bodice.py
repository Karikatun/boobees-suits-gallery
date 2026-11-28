"""Show the old and new bodice in matched views and the new frontal silhouette."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

folder = Path(sys.argv[1])
fonts = Path('C:/Windows/Fonts')
heading = ImageFont.truetype(str(fonts / 'segoeuib.ttf'), 30)
caption = ImageFont.truetype(str(fonts / 'segoeui.ttf'), 24)
width, height = 448, 412
pad, gap, heading_height = 24, 10, 70
sheet = Image.new('RGB', (2 * pad + 3 * width + 2 * gap, pad + 2 * (height + heading_height)), '#202427')
draw = ImageDraw.Draw(sheet)
views = (('before', 'Было · в три четверти'), ('side', 'Стало · в три четверти'), ('front', 'Стало · спереди'))
for row, (pose, name) in enumerate((('stand', 'Стойка'), ('crouch', 'Присед'))):
    y = 10 + row * (height + heading_height)
    draw.text((pad, y), name, fill='#f0ede5', font=heading)
    for col, (view, label) in enumerate(views):
        x = pad + col * (width + gap)
        draw.text((x, y + 36), label, fill='#c4c6c0', font=caption)
        with Image.open(folder / f'{pose}-{view}.png') as full:
            crop = full.convert('RGB').crop((0, 48, full.width, full.height))
            sheet.paste(crop.resize((width, height), Image.Resampling.LANCZOS), (x, y + 66))
sheet.save(folder / 'Semibot-pear-bodice.png', optimize=True)
