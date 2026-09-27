"""Bongo Cat sprites from Externalizable/bongo.cat (MIT), with canvas outfits."""
from functools import lru_cache
from pathlib import Path
import sys
import math
from PIL import Image, ImageTk

STYLES = ('Bongo · 白猫', 'Bongo · 薄荷围巾', 'Bongo · 蜜桃结',
          'Bongo · 星夜帽', 'Bongo · 草莓帽', 'Bongo · 上班眼镜')
ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'assets' / 'bongo'


@lru_cache(maxsize=8)
def layer(name, down=False):
    with Image.open(ROOT / name) as source:
        x = 800 if down else 0
        return source.convert('RGBA').crop((x + 325, 0, x + 710, 285))


def draw_bongo(canvas, cx, cy, scale, phase, state, side, style):
    canvas.delete('cat')
    ratio = scale / 7.7
    bob = math.sin(phase) * 2 if state == 'idle' else 0
    ox, oy = cx - 192.5 * ratio, cy - 130 * ratio + bob
    def point(x, y):
        return ox + (x - 325) * ratio, oy + y * ratio
    def poly(points, fill, outline='', width=3):
        canvas.create_polygon(*[v for xy in points for v in point(*xy)], fill=fill,
                              outline=outline, width=max(1, width*ratio), tags='cat')
    def oval(box, fill, outline='', width=3):
        canvas.create_oval(*point(*box[:2]), *point(*box[2:]), fill=fill,
                           outline=outline, width=max(1, width*ratio), tags='cat')
    def line(points, fill, width=5):
        canvas.create_line(*[v for xy in points for v in point(*xy)], fill=fill,
                           width=max(1, width*ratio), smooth=True, tags='cat')
    # Fill inside the downloaded line art; costumes remain code-native layers.
    poly([(339,195),(350,160),(350,101),(365,77),(391,82),(430,58),(473,38),(494,19),
          (520,44),(575,64),(625,89),(658,78),(658,154),(674,206),(686,262)], '#fffefa')
    if not hasattr(canvas, '_bongo_images'):
        canvas._bongo_images = {}
    tap_left = state == 'tap' and side == 'left'
    tap_right = state == 'tap' and side == 'right'
    if state == 'happy':
        tap_left, tap_right = int(phase*8) % 2 == 0, int(phase*8) % 2 == 1
    for name, down in [('cat.png', False), ('mouth.png', state == 'happy'),
                       ('paw-left.png', tap_left), ('paw-right.png', tap_right)]:
        key = (name, down, round(ratio, 4))
        if key not in canvas._bongo_images:
            sprite = layer(name, down)
            # Nearest sampling preserves binary alpha on Windows color-key windows.
            sprite = sprite.resize((round(385*ratio), round(285*ratio)), Image.Resampling.NEAREST)
            canvas._bongo_images[key] = ImageTk.PhotoImage(sprite, master=canvas)
        canvas.create_image(ox, oy, anchor='nw', image=canvas._bongo_images[key], tags='cat')
    if state == 'sleep':
        for x,y in [(450,111),(548,140)]:
            oval((x-12,y-12,x+12,y+12), '#fffefa')
            line([(x-8,y),(x,y+3),(x+8,y)], '#282827', 5)
    if style == STYLES[1]:
        poly([(406,160),(560,189),(548,206),(406,176)], '#a0ccb8', '#416454')
        poly([(498,183),(522,188),(512,234),(489,222)], '#a0ccb8', '#416454')
    elif style == STYLES[2]:
        poly([(561,61),(528,39),(523,72),(557,69)], '#f0acbb', '#aa6d81')
        poly([(566,63),(591,46),(599,78),(569,72)], '#f0acbb', '#aa6d81')
        oval((550,57,574,77), '#df8fa7', '#aa6d81')
    elif style == STYLES[3]:
        poly([(444,45),(491,-34),(520,-18),(551,64)], '#77719f', '#48415f')
        poly([(427,39),(560,62),(563,77),(424,55)], '#8b80b0', '#48415f')
        poly([(497,6),(502,19),(516,22),(504,28),(505,42),(494,32),(482,37),(487,23),(478,14),(492,16)], '#f6d993')
    elif style == STYLES[4]:
        oval((421,-7,576,77), '#ed9fa8', '#9d6370')
        poly([(423,43),(568,63),(565,80),(421,57)], '#ffd0d6', '#9d6370')
        poly([(488,4),(471,-13),(494,-8),(507,-26),(510,-7),(531,-10),(515,8)], '#86b391')
        for x,y in [(450,25),(476,22),(509,28),(544,40)]: oval((x,y,x+5,y+9),'#fff1b9')
    elif style == STYLES[5]:
        for x,y in [(450,111),(548,140)]: oval((x-29,y-23,x+29,y+23),'','#596273',5)
        line([(479,116),(501,122),(519,133)], '#596273',5)
        poly([(479,169),(499,173),(489,185),(494,211),(477,221),(467,202),(480,183)], '#8da8c4','#566f89')
    # A short desk edge grounds both paws, matching the original Bongo interaction.
    line([(674,205),(680,232),(686,262)], '#111111', 7)
    line([(350,130),(349,160),(339,195)], '#111111', 7)
    line([(339,195),(505,227),(686,262)], '#777d78', 4)
