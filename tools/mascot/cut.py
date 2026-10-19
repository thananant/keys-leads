# Usage: python3 cut.py <dir with 1.jpg 2.jpg> <out dir>  (concept sheets -> transparent PNGs)
# cut mascots out of the concept sheets -> transparent PNGs
import sys, numpy as np
from PIL import Image
from scipy import ndimage as nd
I = sys.argv[1]; OUT = sys.argv[2]
a = Image.open(I + '1.jpg').convert('RGB'); b = Image.open(I + '2.jpg').convert('RGB')
boxes = {
  'unfold':  (a, (80, 255, 480, 775)),
  'compass': (a, (535, 290, 1010, 770)),
  'portal':  (a, (1030, 320, 1515, 770)),
  'buddy':   (b, (360, 25, 925, 795)),
  'buddy_wave':    (b, (880, 15, 1160, 385)),
  'buddy_analyze': (b, (1225, 15, 1505, 395)),
  'buddy_point':   (b, (985, 425, 1288, 785)),
}
for name, (img, box) in boxes.items():
    c = np.asarray(img.crop(box)).astype(np.int16)
    bg = np.array([247, 246, 242])
    d = np.abs(c - bg).sum(2)
    # background = paper-coloured pixels connected to the crop border
    lum = c.mean(2)
    near = d < (12 if name == 'compass' else 22)
    # floor shadow: light, unsaturated pixels in the bottom band
    sat = c.max(2) - c.min(2)
    h = c.shape[0]; band = np.zeros_like(near); band[int(h * 0.86):] = True
    near |= band & (lum > 150) & (sat < 25)
    lab, _ = nd.label(near)
    edge = set(np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]])) - {0}
    fg = ~np.isin(lab, list(edge))
    fg = nd.binary_opening(fg, iterations=2)
    fg = nd.binary_fill_holes(fg)
    lab, n = nd.label(fg)
    if n:
        sizes = nd.sum(fg, lab, range(1, n + 1))
        keep = [i + 1 for i, s in enumerate(sizes) if s > 0.02 * sizes.max()]
        fg = np.isin(lab, keep)
    alpha = nd.gaussian_filter(fg.astype(float), 0.8)
    alpha = np.clip((alpha - 0.2) / 0.6, 0, 1)
    rgba = np.dstack([c.astype(np.uint8), (alpha * 255).astype(np.uint8)])
    im = Image.fromarray(rgba, 'RGBA'); im = im.crop(im.getbbox())
    im.save(f'{OUT}/{name}.png'); print(name, im.size)
