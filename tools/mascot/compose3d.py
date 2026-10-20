# python3 compose3d.py <frames dir> <out.mp4>
# Lays the transparent Blender frames (buddy3d.py) over the brand background, adds header + speech bubbles,
# and muxes the same soundtrack as the 2D test (render2.soundtrack) so timings match.
import glob, os, subprocess, sys
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R
import render2 as V

src, out = sys.argv[1], sys.argv[2]
frames = sorted(glob.glob(os.path.join(src, 'f*.png')))
tmp = out + '.frames'; os.makedirs(tmp, exist_ok=True)
for i, f in enumerate(frames):
    t = i / V.FPS
    c = R.BASE.copy(); R.header(c, '04', 'KEYS BUDDY 3D', 'โมเดล 3D · เดิน กระโดด หมุนตัว 360° + เสียงประจำตัว')
    im = Image.open(f).convert('RGBA').resize((R.W, R.H), Image.LANCZOS)
    c.alpha_composite(im)
    if t >= V.TALK:
        k = min(2, int((t - V.TALK) // 1.5))
        R.bubble(c, R.W / 2 + 230, 640, V.SAY[k], V.TALK + k * 1.5 + 0.2, t)
    c.convert('RGB').save(os.path.join(tmp, f'{i:04d}.jpg'), quality=92)
wav = out + '.wav'
V.write_wav(wav, V.soundtrack('buddy', 2.8))
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(V.FPS), '-i', os.path.join(tmp, '%04d.jpg'), '-i', wav,
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '21', '-preset', 'slow', '-c:a', 'aac', '-b:a', '128k',
                '-shortest', '-movflags', '+faststart', out], check=True)
subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', '9', '-i', out, '-frames:v', '1', '-vf', 'scale=540:-1', '-q:v', '4',
                out.replace('.mp4', '.jpg')], check=True)
for f in glob.glob(os.path.join(tmp, '*')): os.remove(f)
os.rmdir(tmp); os.remove(wav)
print('wrote', out)
