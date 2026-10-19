# Usage: python3 render2.py <out dir> [unfold compass portal buddy]
# Motion test v2: walk in, jump, 360 spin, then talk/pose, with a synthesized signature sound per mascot.
# Reuses the helpers of render.py (same folder). Needs ffmpeg, PIL, numpy.
import math, os, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R

FPS, SEC, SR = 30, 10, 44100
W, H = R.W, R.H
FLOOR = 1560

# ---------------- timeline (seconds)
WALK = (0.0, 2.2)
JUMP = (2.5, 3.6)   # 0.2 anticipation, airborne, landing
SPIN = (4.0, 5.2)
TALK = 5.4

def smooth(t): t = min(max(t, 0), 1); return t * t * (3 - 2 * t)

def pose_at(t, sp, kw):
    """returns sprite, cx, base_y, sx, sy, rot"""
    jamp, bounce = kw.get('jamp', 12), kw.get('bounce', 0.04)
    step = kw.get('step', 2.6)  # steps per second
    cx, y, sx, sy, rot = W / 2, FLOOR, 1.0, 1.0, 0.0
    s = sp
    if t < WALK[1]:
        k = smooth(t / WALK[1])
        cx = -sp.width * 0.6 + (W / 2 + sp.width * 0.6) * k
        ph = t * step * 2 * math.pi
        y -= abs(math.sin(ph)) * 34 * (1 - k * 0.3)
        sq = 0.05 * math.cos(2 * ph)
        sx, sy = 1 + sq * 0.6, 1 - sq
        rot = -5 + 3 * math.sin(ph)
        s = R.jelly(sp, jamp * 1.3, ph + 1.2)
    elif t < JUMP[0]:  # settle
        q = (t - WALK[1]) / (JUMP[0] - WALK[1])
        sq = 0.08 * math.sin(q * math.pi) ; sx, sy = 1 + sq, 1 - sq
        s = R.jelly(sp, jamp * (1 - q), q * 10)
    elif t < JUMP[1]:
        q = t - JUMP[0]; d = JUMP[1] - JUMP[0]
        if q < 0.2:  # anticipation
            a = smooth(q / 0.2); sx, sy = 1 + 0.12 * a, 1 - 0.18 * a
        elif q < d - 0.25:  # airborne
            a = (q - 0.2) / (d - 0.45)
            y -= math.sin(a * math.pi) * 330
            st = 0.14 * (1 - abs(2 * a - 1)); sx, sy = 1 - st * 0.5, 1 + st
            rot = 8 * math.sin(a * 2 * math.pi)
            s = R.jelly(sp, jamp * 1.5, a * 7)
        else:  # landing squash
            a = (q - (d - 0.25)) / 0.25
            sq = 0.2 * math.sin(a * math.pi) * (1 - a * 0.4); sx, sy = 1 + sq, 1 - sq
    elif t < SPIN[1] + 0.2:
        q = min(1, (t - SPIN[0]) / (SPIN[1] - SPIN[0])) if t >= SPIN[0] else 0
        th = smooth(q) * 2 * math.pi
        c = math.cos(th)
        y -= math.sin(q * math.pi) * 60
        sx = max(0.04, abs(c))
        if c < 0:  # back side: mirrored and a little darker, reads as turning around
            s = ImageEnhance.Brightness(sp.transpose(Image.FLIP_LEFT_RIGHT)).enhance(0.8)
    else:
        b = R.idle(t - TALK + 0.6, sp, bounce=bounce, sway=kw.get('sway', 3), jamp=jamp)
        s, sx, sy, rot = b[0], b[1], b[2], b[3]
        y += b[5]
    return s, cx, y, sx, sy, rot

def dust(c, t, t_land, cx):
    q = (t - t_land) / 0.45
    if not 0 <= q < 1: return
    d = ImageDraw.Draw(c)
    for side in (-1, 1):
        for i in range(3):
            r = 18 + 26 * q + i * 6
            x = cx + side * (120 + 160 * q + i * 40); y = FLOOR - 10 - i * 14 * q
            a = int(120 * (1 - q))
            d.ellipse((x - r, y - r, x + r, y + r), fill=(201, 211, 242, a))

def speed_lines(c, t, cx):
    if not SPIN[0] <= t < SPIN[1]: return
    d = ImageDraw.Draw(c); q = (t - SPIN[0]) / (SPIN[1] - SPIN[0])
    for i in range(5):
        ang = q * 12 + i * 1.25
        x = cx + math.cos(ang) * 470; y = FLOOR - 430 + math.sin(ang) * 120
        d.arc((x - 90, y - 30, x + 90, y + 30), 200, 340, fill=(6, 65, 255, 110), width=8)

# ---------------- sound design (numpy synth)
def env(n, a=0.005, r=0.2):
    t = np.arange(n) / SR
    return np.minimum(1, t / a) * np.exp(-t / r)

def tone(f0, f1, dur, wave_='sine', r=0.2, vib=0.0, vibf=6):
    n = int(dur * SR); t = np.arange(n) / SR
    f = np.geomspace(f0, f1, n) * (1 + vib * np.sin(2 * np.pi * vibf * t))
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) if wave_ == 'sine' else np.sign(np.sin(ph)) * 0.3 + np.sin(ph) * 0.7
    return x * env(n, r=r)

def noise(dur, lo=0.2, r=0.1, sweep=None):
    n = int(dur * SR); x = np.random.default_rng(7).standard_normal(n)
    if sweep:  # crude band sweep: moving average of varying length
        out = np.zeros(n); k0, k1 = sweep
        for i in range(0, n, 512):
            k = int(k0 + (k1 - k0) * i / n); seg = x[max(0, i - k):i + 512 + k]
            out[i:i + 512] = np.convolve(seg, np.ones(k) / k, 'same')[k if i else 0:][:len(out[i:i + 512])]
        x = out * 4
    return x * env(n, a=dur * lo, r=r)

def bell(f, dur=0.9):
    return plus(*[tone(f * m, f * m, dur, r=dur / (1 + i)) * g for i, (m, g) in enumerate([(1, 1), (2.76, .4), (5.4, .2)])])

def mix(parts, dur):
    out = np.zeros(int(dur * SR))
    for t0, x, g in parts:
        i = int(t0 * SR); j = min(len(out), i + len(x)); out[i:j] += x[:j - i] * g
    return out

SIGS = {  # signature sound: plays when the mascot lands its intro and again after the spin
    'unfold': lambda: np.concatenate([tone(180, 420, 0.18, vib=0.08), tone(420, 260, 0.35, vib=0.12, vibf=11)]),   # jelly boing
    'compass': lambda: np.concatenate([bell(1318.5, 0.35), bell(1975.5, 0.8)]),                                    # compass chime
    'portal': lambda: mix([(i * 0.07, bell(f, 0.7), 0.6) for i, f in enumerate([523, 659, 784, 1046, 1318])]
                          + [(0, noise(1.0, lo=0.6, r=0.3, sweep=(40, 4)), 0.25)], 1.1),                           # portal shimmer
    'buddy': lambda: mix([(0, tone(520, 880, 0.09), 0.8), (0.09, tone(880, 1320, 0.12), 0.8)]
                         + [(0.25 + i * 0.05, noise(0.06, lo=0.02, r=0.03), 0.5) for i in range(4)]
                         + [(0.25 + i * 0.05, tone(4200 + 700 * i, 4200 + 700 * i, 0.08, r=0.05), 0.3) for i in range(4)], 0.6),  # bloop + key jingle
}

def plus(*xs):
    out = np.zeros(max(len(x) for x in xs))
    for x in xs: out[:len(x)] += x
    return out

def put(track, t, x, g=1.0):
    i = int(t * SR); j = min(len(track), i + len(x))
    if i < len(track): track[i:j] += x[:j - i] * g

def soundtrack(name, step):
    tr = np.zeros(SEC * SR)
    for k in range(int(WALK[1] * step * 2)):  # footsteps
        put(tr, (k + 0.5) / (step * 2), plus(tone(140, 70, 0.09, r=0.04) * 0.5, noise(0.05, lo=0.05, r=0.02) * 0.08))
    put(tr, JUMP[0] + 0.18, tone(220, 900, 0.3, vib=0.05) * 0.5)          # boing up
    put(tr, JUMP[1] - 0.25, plus(tone(110, 50, 0.25, r=0.08) * 0.8, noise(0.2, lo=0.02, r=0.06) * 0.15))  # land
    put(tr, SPIN[0], noise(SPIN[1] - SPIN[0], lo=0.5, r=0.5, sweep=(60, 3)) * 0.3)                   # whoosh
    sig = SIGS[name]()
    put(tr, WALK[1] + 0.05, sig, 0.7)
    put(tr, SPIN[1] + 0.05, sig, 0.55)
    for k in range(3):  # soft pop for each speech bubble
        put(tr, TALK + 0.2 + k * 1.5, tone(600, 1100, 0.07, r=0.03) * 0.3)
    tr /= max(1e-6, np.abs(tr).max()) / 0.85
    return tr

def write_wav(path, x):
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())

# ---------------- clips
CAST = {
    'unfold':  ('01', 'UNFOLD', 'เดิน กระโดด หมุนตัว + เสียงประจำตัว', dict(bounce=0.06, sway=3, jamp=22, step=2.4), 820),
    'compass': ('02', 'COMPASS', 'เดิน กระโดด หมุนตัว + เสียงประจำตัว', dict(bounce=0.03, sway=3, jamp=10, step=3.2), 820),
    'portal':  ('03', 'PORTAL', 'เดิน กระโดด หมุนตัว + เสียงประจำตัว', dict(bounce=0.05, sway=2.5, jamp=18, step=2.2), 760),
    'buddy':   ('04', 'KEYS BUDDY', 'เดิน กระโดด หมุนตัว + เสียงประจำตัว', dict(bounce=0.035, sway=2.5, jamp=10, step=2.8), 840),
}
SAY = ['สวัสดีครับ', 'ราคาปรับให้แล้ว', 'ส่องคู่แข่งให้ด้วย']
BUDDY_TALK = ['buddy_wave', 'buddy_analyze', 'buddy_point']

def clip(name, out):
    num, title, sub, kw, h = CAST[name]
    sp = R.load(name, h, 900)
    talk = [R.load(n, h, 900) for n in BUDDY_TALK] if name == 'buddy' else None
    def fr(t):
        c = R.BASE.copy(); R.header(c, num, title, sub)
        cur = sp
        if talk and t >= TALK: cur = talk[min(2, int((t - TALK) // 1.5))]
        s, cx, y, sx, sy, rot = pose_at(t, cur, kw)
        speed_lines(c, t, cx)
        R.place(c, s, cx, y if t < JUMP[0] or t > JUMP[1] else FLOOR, sx, sy, rot, shadow=False)
        dust(c, t, JUMP[1] - 0.25, cx)
        if t >= TALK:
            k = min(2, int((t - TALK) // 1.5))
            R.bubble(c, W / 2, FLOOR - h - 40, SAY[k], TALK + k * 1.5 + 0.2, t)
        return c
    silent = out + '.video.mp4'; wav = out + '.wav'
    R.FPS, R.SEC = FPS, SEC
    R.render(silent, frame_with_shadow(fr, sp, kw))
    write_wav(wav, soundtrack(name, kw['step']))
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', silent, '-i', wav, '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k',
                    '-shortest', '-movflags', '+faststart', out], check=True)
    os.remove(silent); os.remove(wav); print('muxed', out)

def frame_with_shadow(fr, sp, kw):
    def f(t):
        s, cx, y, sx, sy, rot = pose_at(t, sp, kw)
        lift = FLOOR - y
        c = R.BASE.copy()
        sw = int(sp.width * 0.62 * max(sx, 0.3) * (1 - min(lift, 330) / 700)); sh = max(8, int(sw * 0.13))
        g = Image.new('RGBA', (sw + 40, sh + 40)); ImageDraw.Draw(g).ellipse((20, 20, 20 + sw, 20 + sh), fill=(11, 28, 79, int(55 * (1 - min(lift, 330) / 500))))
        from PIL import ImageFilter
        g = g.filter(ImageFilter.GaussianBlur(9))
        top = fr(t)
        c.alpha_composite(g, (int(cx - g.width / 2), int(FLOOR - g.height / 2)))
        # fr() already painted the background; lay the shadow under the character by compositing fr over a shadowed base
        mask = np.asarray(top).astype(np.int16); base = np.asarray(R.BASE).astype(np.int16)
        diff = (np.abs(mask - base).sum(2) > 6)
        out = np.asarray(c).copy(); out[diff] = np.asarray(top)[diff]
        return Image.fromarray(out, 'RGBA')
    return f

if __name__ == '__main__':
    out = sys.argv[1]
    for n in (sys.argv[2:] or list(CAST)):
        clip(n, f'{out}/v2-{CAST[n][0]}-{n}.mp4')
