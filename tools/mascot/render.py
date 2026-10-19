# Usage: python3 render.py <out dir> [unfold compass portal buddy compare]  (needs ffmpeg, PIL, numpy; fonts: IBM Plex Sans Thai)
# Motion test for keys mascot concepts: 2D puppet animation from the concept stills.
# Renders 9:16 clips (one per mascot + a side-by-side comparison) with ffmpeg.
import math, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

M = '/tmp/claude-0/m/'
FPS, SEC = 30, 9
W, H = 1080, 1920
BG_TOP, BG_BOT = (244, 246, 252), (226, 232, 248)
NAVY, BLUE = (11, 28, 79), (6, 65, 255)
F = lambda s, w=700: ImageFont.truetype(f'/tmp/claude-0/fonts/thai{w}.ttf', s)

def load(name, h, maxw=None):
    im = Image.open(M + name + '.png').convert('RGBA')
    k = h / im.height
    if maxw: k = min(k, maxw / im.width)
    return im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)

def bg(w, h):
    g = np.linspace(0, 1, h)[:, None, None]
    a = np.array(BG_TOP)[None, None] * (1 - g) + np.array(BG_BOT)[None, None] * g
    return Image.fromarray(np.repeat(a, w, 1).astype(np.uint8), 'RGB').convert('RGBA')

def ease_back(t):  # overshoot pop
    t = min(max(t, 0), 1); c = 1.9
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2

def jelly(sprite, amp, phase, power=1.6):
    """sway the top of the sprite sideways, feet stay planted"""
    a = np.asarray(sprite); h, w = a.shape[:2]; pad = int(abs(amp)) + 4
    a = np.pad(a, ((0, 0), (pad, pad), (0, 0)))
    y = np.arange(h); wgt = ((h - y) / h) ** power
    shift = (amp * wgt * math.sin(phase)).astype(int)
    xs = np.clip(np.arange(w + 2 * pad)[None, :] - shift[:, None], 0, w + 2 * pad - 1)
    return Image.fromarray(a[y[:, None], xs], 'RGBA')

def place(canvas, sprite, cx, base_y, sx=1.0, sy=1.0, rot=0.0, shadow=True):
    w, h = sprite.size
    s = sprite.resize((max(1, round(w * sx)), max(1, round(h * sy))), Image.BILINEAR)
    if rot:
        s = s.rotate(rot, resample=Image.BICUBIC, expand=True, center=(s.width / 2, s.height))
    if shadow:
        sw = int(w * 0.62 * sx); sh = max(8, int(sw * 0.13))
        sh_im = Image.new('RGBA', (sw + 40, sh + 40)); d = ImageDraw.Draw(sh_im)
        d.ellipse((20, 20, 20 + sw, 20 + sh), fill=(11, 28, 79, 55))
        sh_im = sh_im.filter(ImageFilter.GaussianBlur(9))
        canvas.alpha_composite(sh_im, (int(cx - sh_im.width / 2), int(base_y - sh_im.height / 2)))
    canvas.alpha_composite(s, (int(cx - s.width / 2), int(base_y - s.height)))

def text_c(d, xy, txt, font, fill, anchor='mm'):
    d.text(xy, txt, font=font, fill=fill, anchor=anchor)

def bubble(canvas, cx, y, txt, t_in, t, size=54, maxw=880):
    if t < t_in: return
    k = ease_back((t - t_in) / 0.35)
    n = int(len(txt) * min(1, (t - t_in) / 0.9))  # typewriter
    font = F(size, 600); d = ImageDraw.Draw(canvas)
    bw = min(maxw, int(d.textlength(txt, font=font)) + 70); bh = size + 54
    layer = Image.new('RGBA', (bw + 30, bh + 40))
    ld = ImageDraw.Draw(layer)
    ld.rounded_rectangle((0, 0, bw, bh), radius=bh // 2, fill=(255, 255, 255, 245), outline=(201, 211, 242), width=3)
    ld.polygon([(bw // 2 - 22, bh - 2), (bw // 2 + 22, bh - 2), (bw // 2, bh + 30)], fill=(255, 255, 255, 245))
    ld.text((bw // 2, bh // 2), txt[:n], font=font, fill=NAVY, anchor='mm')
    layer = layer.resize((max(1, int(layer.width * k)), max(1, int(layer.height * k))), Image.BILINEAR)
    canvas.alpha_composite(layer, (int(cx - layer.width / 2 + 15 * k), int(y - layer.height)))

def header(canvas, num, name, sub):
    d = ImageDraw.Draw(canvas)
    d.text((70, 110), 'keys', font=F(64), fill=NAVY)
    d.text((70, 250), f'{num} / ', font=F(58), fill=(160, 166, 190))
    x = 70 + d.textlength(f'{num} / ', font=F(58))
    d.text((x, 250), name, font=F(58), fill=NAVY)
    d.text((70, 335), sub, font=F(36, 600), fill=(100, 109, 150))

def caption(canvas, t, lines):
    d = ImageDraw.Draw(canvas)
    for (t0, txt) in lines:
        if t >= t0:
            cur = txt
    if t < lines[0][0]: return
    a = min(1, (t - max(t0 for t0, _ in lines if t >= t0)) / 0.25)
    font = F(60)
    tw = d.textlength(cur, font=font)
    y = 1650
    box = Image.new('RGBA', (int(tw) + 80, 110))
    ImageDraw.Draw(box).rounded_rectangle((0, 0, box.width - 1, 109), radius=26, fill=(11, 28, 79, int(230 * a)))
    ImageDraw.Draw(box).text((box.width // 2, 55), cur, font=font, fill=(255, 255, 255, int(255 * a)), anchor='mm')
    canvas.alpha_composite(box, (int(W / 2 - box.width / 2), y))

# ---------------- motion per mascot (t in seconds) -> list of (sprite, sx, sy, rot, dx, dy)
def idle(t, sprite, bounce=0.045, sway=4.0, jamp=14, speed=1.0):
    pop = ease_back(t / 0.6)
    beat = t * 2.2 * speed
    sq = bounce * math.sin(beat * 2 * math.pi)          # squash & stretch
    hop = max(0, math.sin(beat * 2 * math.pi)) * 26 if 2.5 < t < 4.0 else 0
    s = jelly(sprite, jamp, t * 2 * math.pi * 0.9 * speed)
    return s, pop * (1 + sq * 0.6), pop * (1 - sq), sway * math.sin(t * 2 * math.pi * 0.55), 0, -hop

def render(path, frame_fn):
    p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
                          '-r', str(FPS), '-i', '-', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20',
                          '-preset', 'medium', '-movflags', '+faststart', path], stdin=subprocess.PIPE)
    for i in range(FPS * SEC):
        p.stdin.write(frame_fn(i / FPS).convert('RGB').tobytes())
    p.stdin.close(); p.wait(); print('wrote', path)

BASE = bg(W, H)
LINES = lambda nick: [(1.0, f'สวัสดีครับ ผม{nick}'), (3.4, 'ตั้งราคาห้องให้อัตโนมัติ'), (6.0, 'ไม่ต้องเฝ้าทั้งคืน')]

SINGLE = [
    ('unfold', '01', 'UNFOLD', 'นุ่มนิ่ม เด้งได้ทั้งตัว', 'น้อง Unfold', dict(bounce=0.06, sway=3, jamp=22), 900),
    ('compass', '02', 'COMPASS', 'จิ้งจอกนำทาง ขี้เล่น', 'น้อง Compass', dict(bounce=0.03, sway=3, jamp=10, speed=1.2), 900),
    ('portal', '03', 'PORTAL', 'ประตูสู่รายได้ เรียบง่าย', 'น้อง Portal', dict(bounce=0.05, sway=2.5, jamp=18), 820),
]

def single(name, num, title, sub, nick, kw, h):
    sp = load(name, h)
    def fr(t):
        c = BASE.copy(); header(c, num, title, sub)
        s, sx, sy, rot, dx, dy = idle(t, sp, **kw)
        place(c, s, W / 2 + dx, 1560 + dy, sx, sy, rot)
        bubble(c, W / 2, 1560 - h - 30, ['สวัสดีครับ', 'ราคาปรับแล้ว!', 'ส่องคู่แข่งให้ด้วย'][min(2, int(t // 3))], [0.9, 3.3, 5.9][min(2, int(t // 3))], t)
        caption(c, t, LINES(nick))
        return c
    return fr

# KEYS BUDDY: real pose library -> swap poses with a squash transition
POSES = [(0.0, 'buddy_wave', 'สวัสดีครับ'), (2.6, 'buddy', 'มาดูรายได้กัน'), (4.8, 'buddy_analyze', 'วิเคราะห์ให้แล้ว'), (6.9, 'buddy_point', 'ราคานี้ดีสุด!')]
def buddy():
    h = 900
    sps = {n: load(n, h) for _, n, _ in POSES}
    def fr(t):
        c = BASE.copy(); header(c, '04', 'KEYS BUDDY', 'คนช่วยตั้งราคา มีมือ มีท่าทาง')
        k = max(i for i, (t0, _, _) in enumerate(POSES) if t >= t0)
        t0, n, say = POSES[k]
        s, sx, sy, rot, dx, dy = idle(t, sps[n], bounce=0.035, sway=2.5, jamp=10)
        if k:  # little squash-and-pop on every pose change
            q = (t - t0) / 0.3
            if q < 1: sy *= 0.86 + 0.14 * ease_back(q); sx *= 1.08 - 0.08 * ease_back(q)
        place(c, s, W / 2 + dx, 1560 + dy, sx, sy, rot)
        bubble(c, W / 2, 1560 - h - 30, say, t0 + 0.2, t)
        caption(c, t, LINES('คีย์ บัดดี้'))
        return c
    return fr

# side-by-side: all four moving at once
def compare():
    cw, ch = W // 2, 810
    cells = [('unfold', '01 UNFOLD', dict(bounce=0.06, sway=3, jamp=22)), ('compass', '02 COMPASS', dict(bounce=0.03, sway=3, jamp=10, speed=1.2)),
             ('portal', '03 PORTAL', dict(bounce=0.05, sway=2.5, jamp=18)), ('buddy', '04 KEYS BUDDY', dict(bounce=0.035, sway=2.5, jamp=10))]
    sps = {n: load(n, 500, 420) for n, _, _ in cells}
    bud = {n: load(n, 520, 420) for _, n, _ in POSES}
    def fr(t):
        c = BASE.copy(); d = ImageDraw.Draw(c)
        text_c(d, (W / 2, 120), 'keys · เทียบมาสคอต 4 แบบ', F(58), NAVY)
        text_c(d, (W / 2, 195), 'แบบไหนขยับแล้วน่ารัก จำง่าย สื่อสารได้ดีสุด?', F(36, 600), (100, 109, 150))
        for i, (n, label, kw) in enumerate(cells):
            x0 = (i % 2) * cw; y0 = 270 + (i // 2) * ch
            d.rounded_rectangle((x0 + 18, y0 + 10, x0 + cw - 18, y0 + ch - 20), radius=36, fill=(255, 255, 255, 150), outline=(221, 226, 240), width=2)
            sp = sps[n]
            if n == 'buddy':
                k = int(t // 2.25) % 4; sp = bud[POSES[k][1]]
            tl = (t - i * 0.15)
            s, sx, sy, rot, dx, dy = idle(max(tl, 0), sp, **{**kw, 'jamp': kw['jamp'] * 0.6})
            place(c, s, x0 + cw / 2, y0 + ch - 120 + dy, sx, sy, rot)
            text_c(d, (x0 + cw / 2, y0 + ch - 60), label, F(40), NAVY)
        return c
    return fr

if __name__ == '__main__':
    OUT = sys.argv[1]
    which = sys.argv[2:] or ['unfold', 'compass', 'portal', 'buddy', 'compare']
    for name, num, title, sub, nick, kw, h in SINGLE:
        if name in which: render(f'{OUT}/{num}-{name}.mp4', single(name, num, title, sub, nick, kw, h))
    if 'buddy' in which: render(f'{OUT}/04-buddy.mp4', buddy())
    if 'compare' in which: render(f'{OUT}/00-compare.mp4', compare())
