"""Label the mouth fit samples at the same scale in both poses."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

folder = Path(sys.argv[1])
fonts = Path('C:/Windows/Fonts')
heading = ImageFont.truetype(str(fonts / 'segoeuib.ttf'), 30)
caption = ImageFont.truetype(str(fonts / 'segoeui.ttf'), 23)
width, height = 436, 451
pad, gap, label_height = 24, 10, 68
sheet = Image.new('RGB', (2 * pad + 3 * width + 2 * gap, pad + 2 * (height + label_height)), '#202427')
draw = ImageDraw.Draw(sheet)
states = [('closed', 'Рот закрыт'), ('speaking', 'Открыт на 22,5°'), ('wide', 'Максимум · 45°')]

for row, (pose, name) in enumerate([('stand', 'Стойка'), ('crouch', 'Присед')]):
    top = 12 + row * (height + label_height)
    draw.text((pad, top), name, fill='#f0ede5', font=heading)
    for column, (state, label) in enumerate(states):
        x = pad + column * (width + gap)
        draw.text((x, top + 36), label, fill='#bfc5c5', font=caption)
        with Image.open(folder / f'{pose}-{state}.png') as frame:
            frame = frame.convert('RGB').resize((width, height), Image.Resampling.LANCZOS)
            sheet.paste(frame, (x, top + 66))

sheet.save(folder / 'Semibot-mouth-fit.png', optimize=True)
