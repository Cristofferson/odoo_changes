#!/usr/bin/env python3
"""Blanco → amarillo SIN IA: tiñe de oro solo el METAL (píxeles grises de brillo medio/alto y poca textura de faceta).
Los diamantes se respetan: se protege la zona de la piedra (alta varianza local)."""
import sys, colorsys
from PIL import Image, ImageFilter, ImageChops
im = Image.open(sys.argv[1]).convert('RGB'); W, H = im.size
g = im.convert('L')
# varianza local: facetas de piedra = mucho contraste en poco espacio
var = ImageChops.difference(g, g.filter(ImageFilter.BoxBlur(2))).filter(ImageFilter.MaxFilter(5))
px = im.load(); vp = var.load(); out = im.copy(); op = out.load()
for y in range(H):
    for x in range(W):
        r, gg, b = px[x, y]; h, s, v = colorsys.rgb_to_hsv(r/255, gg/255, b/255)
        if s > 0.18 or v > 0.97 or v < 0.08: continue
        if vp[x, y] > 38: continue          # probablemente piedra
        L = v
        R = min(255, int(255 * min(1, L * 1.08))); G = int(255 * L * 0.86); B = int(255 * L * 0.42)
        op[x, y] = (R, G, B)
out.save(sys.argv[2], quality=92)
