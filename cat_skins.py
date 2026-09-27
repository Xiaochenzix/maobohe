"""Original round-faced pixel cat, restored from the initial source."""
import math
from bongo_skins import STYLES as BONGO_STYLES, draw_bongo
THEMES = {
    '奶油橘': ('#f8dda8', '#f4bd79', '#de9470'),
    '薄荷绿': ('#dbeacb', '#aecda3', '#79a987'),
    '香芋紫': ('#e5dcf1', '#c8b5df', '#9b89ba'),
    '蜜桃粉': ('#f8dadd', '#e8b2bc', '#cd8d9f'),
    '云朵白': ('#f6f4e9', '#d8dcd8', '#9dafad'),
    '夜空蓝': ('#b9d0e5', '#91acc9', '#71849e'),
}
STYLES = ('经典围巾', '元气兔耳', '魔法学徒', '草莓奶帽', '上班领带', '太空旅客')
ORIGINAL_STYLES = STYLES
STYLES += BONGO_STYLES
INK = '#4b5145'

def draw_cat(canvas, cx, cy, scale=4, theme='奶油橘', phase=0, state='idle', side='left', style='经典围巾'):
    """Draw crisp vector pixels, centred within a 44 by 42 logical cell."""
    if style.startswith('model:'):
        return canvas._root().model_renderer.draw(canvas,cx,cy,scale,phase,state,side,style)
    if style in BONGO_STYLES:
        return draw_bongo(canvas, cx, cy, scale, phase, state, side, style)
    canvas.delete('cat')
    fur, shade, trim = THEMES.get(theme, THEMES['奶油橘'])
    bob = 1 if math.sin(phase) > .65 and state not in ('sleep', 'tap') else 0
    ox, oy = cx - 22 * scale, cy - 22 * scale - bob * scale

    def rect(x, y, w, h, color):
        canvas.create_rectangle(ox + x * scale, oy + y * scale,
                                ox + (x + w) * scale, oy + (y + h) * scale,
                                fill=color, outline='', tags='cat')

    def poly(points, color):
        canvas.create_polygon(*[v for x, y in points for v in (ox + x * scale, oy + y * scale)],
                              fill=color, outline='', tags='cat')

    # Curled tail and sitting body.
    rect(34, 28, 6, 10, INK)
    rect(38, 23, 4, 11, INK)
    rect(36, 29, 3, 7, shade)
    rect(39, 25, 2, 7, fur)
    poly([(12, 22), (31, 22), (31, 25), (34, 25), (34, 38), (31, 38),
          (31, 40), (10, 40), (10, 37), (8, 37), (8, 28), (12, 28)], INK)
    rect(12, 26, 18, 12, fur)
    rect(10, 30, 22, 6, fur)
    rect(18, 30, 10, 8, '#fff5dd')
    # Stepped ears and rounded pixel silhouette.
    shape = [(6, 4), (10, 4), (10, 6), (13, 6), (13, 9), (29, 9), (29, 6),
             (32, 6), (32, 4), (36, 4), (36, 19), (38, 19), (38, 26),
             (35, 26), (35, 29), (9, 29), (9, 27), (6, 27), (6, 24), (4, 24),
             (4, 17), (6, 17)]
    poly(shape, INK)
    poly([(8, 7), (10, 7), (10, 10), (14, 10), (14, 12), (29, 12),
          (29, 10), (33, 10), (33, 7), (34, 7), (34, 20), (36, 20),
          (36, 24), (33, 24), (33, 27), (10, 27), (10, 25), (8, 25),
          (8, 23), (6, 23), (6, 19), (8, 19)], fur)
    rect(8, 10, 3, 6, '#eab3a3')
    rect(31, 10, 3, 6, '#eab3a3')
    rect(18, 12, 2, 4, shade)
    rect(22, 12, 2, 3, shade)
    rect(26, 12, 2, 4, shade)
    sleeping = state == 'sleep'
    blink = phase % 14 > 13.25 or sleeping
    if blink or state == 'happy':
        rect(12, 20, 5, 1, INK)
        rect(27, 20, 5, 1, INK)
        if state == 'happy':
            rect(13, 19, 3, 1, INK)
            rect(28, 19, 3, 1, INK)
    else:
        rect(13, 18, 2, 4, INK)
        rect(28, 18, 2, 4, INK)
        rect(13, 18, 1, 1, '#fffdf5')
        rect(28, 18, 1, 1, '#fffdf5')
    rect(8, 23, 4, 2, '#eeb6a3')
    rect(31, 23, 4, 2, '#eeb6a3')
    rect(20, 22, 3, 1, trim)
    rect(21, 23, 1, 2, INK)
    rect(19, 25, 2, 1, INK)
    rect(22, 25, 2, 1, INK)
    # Small green neckerchief.
    rect(13, 28, 18, 3, '#729a70')
    poly([(23, 30), (28, 30), (28, 35), (25, 35), (25, 33), (23, 33)], '#567b56')
    # Independent paw raises give left/right click feedback.
    for paw, x in [('left', 10), ('right', 28)]:
        raised = (state == 'tap' and paw == side) or (state == 'happy' and paw == 'right')
        y = 29 if raised else 36
        rect(x, y, 7, 5, INK)
        rect(x + 1, y, 5, 3, '#fff1d5')
        rect(x + 2, y + 3, 1, 1, shade)
    if style == '元气兔耳':
        for x in (10, 28):
            rect(x - 1, -1, 7, 15, INK)
            rect(x, 0, 5, 13, '#fff9e9')
            rect(x + 1, 2, 3, 9, '#edb5bb')
    elif style == '魔法学徒':
        poly([(9, 11), (13, 11), (13, 7), (18, 7), (18, 3), (22, 3), (22, -1),
              (25, -1), (25, 4), (29, 4), (29, 8), (33, 8), (33, 12), (37, 12), (37, 15), (7, 15), (7, 12)], '#72668d')
        rect(11, 12, 23, 2, '#c0a8d5')
        rect(23, 6, 2, 5, '#f9dda0')
        rect(21, 8, 6, 1, '#f9dda0')
    elif style == '草莓奶帽':
        poly([(7, 12), (7, 6), (11, 6), (11, 3), (17, 3), (17, 1), (28, 1),
              (28, 3), (34, 3), (34, 6), (37, 6), (37, 12)], '#d98588')
        rect(7, 11, 30, 3, '#f7cbd1')
        rect(19, 0, 8, 3, '#78a579')
        rect(22, -2, 3, 5, '#78a579')
        for x, y in ((12, 7), (18, 5), (25, 7), (31, 6)):
            rect(x, y, 1, 2, '#fff0bb')
    elif style == '上班领带':
        rect(13, 28, 18, 3, '#edf2f3')
        rect(23, 31, 6, 5, fur)
        poly([(19, 30), (24, 30), (23, 32), (25, 36), (22, 39), (19, 36), (21, 32)], '#7b93aa')
        for x in (10, 25):
            rect(x, 17, 9, 1, INK)
            rect(x, 23, 9, 1, INK)
            rect(x, 17, 1, 7, INK)
            rect(x + 8, 17, 1, 7, INK)
        rect(19, 19, 6, 1, INK)
    elif style == '太空旅客':
        for x in (2, 38):
            rect(x, 12, 4, 17, '#8daeb5')
            rect(x + 1, 14, 2, 12, '#cce4e5')
        rect(7, 5, 30, 2, '#bddbdd')
        rect(8, 29, 28, 3, '#8daeb5')
        rect(10, 30, 23, 2, '#e0efef')
        rect(13, 33, 17, 5, '#cce4e5')
        rect(17, 34, 3, 2, '#d29485')
    if sleeping:
        canvas.create_text(ox + 38 * scale, oy + 6 * scale, text='z', fill=trim,
                           font=('Consolas', round(scale * 3), 'bold'), tags='cat')


