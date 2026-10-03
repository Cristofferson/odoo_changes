#!/usr/bin/env python3
"""Mide la vista de frente (-p) de un anillo: usa el hueco interior como regla (medida 4 = 14.86 mm)
y saca el grosor del aro abajo y a los lados, y la altura de la cabeza. Uso: mide.py <foto-p.jpg> [salida_debug.png]"""
import sys, json
from collections import deque
from PIL import Image, ImageDraw
D_INT = 14.86          # mm, diámetro interior de la medida 4 (US/MX)
im = Image.open(sys.argv[1]).convert('L'); W, H = im.size; px = im.load()
fondo = lambda v: v >= int(__import__("os").environ.get("UMBRAL","252"))
# 1) componente de fondo conectado al borde
ext = [[False]*W for _ in range(H)]; q = deque()
for x in range(W):
    for y in (0, H-1):
        if fondo(px[x, y]) and not ext[y][x]: ext[y][x] = True; q.append((x, y))
for y in range(H):
    for x in (0, W-1):
        if fondo(px[x, y]) and not ext[y][x]: ext[y][x] = True; q.append((x, y))
while q:
    x, y = q.popleft()
    for nx, ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
        if 0<=nx<W and 0<=ny<H and not ext[ny][nx] and fondo(px[nx, ny]): ext[ny][nx] = True; q.append((nx, ny))
# 2) huecos interiores: fondo NO conectado al borde; el más grande es el hueco del aro
vis = [[False]*W for _ in range(H)]; huecos = []
for y in range(H):
    for x in range(W):
        if fondo(px[x, y]) and not ext[y][x] and not vis[y][x]:
            comp = []; q = deque([(x, y)]); vis[y][x] = True
            while q:
                a, b = q.popleft(); comp.append((a, b))
                for nx, ny in ((a+1,b),(a-1,b),(a,b+1),(a,b-1)):
                    if 0<=nx<W and 0<=ny<H and not vis[ny][nx] and fondo(px[nx, ny]) and not ext[ny][nx]: vis[ny][nx] = True; q.append((nx, ny))
            huecos.append(comp)
if not huecos: print(json.dumps({'error': 'sin hueco'})); sys.exit()
h = max(huecos, key=len)
hx = [p[0] for p in h]; hy = [p[1] for p in h]
x0, x1, y0, y1 = min(hx), max(hx), min(hy), max(hy)
d_px = x1 - x0 + 1; mm = D_INT / d_px
cx = (x0 + x1) // 2; cy = (y0 + y1) // 2
metal = lambda x, y: not ext[y][x] and not (fondo(px[x, y]) and not ext[y][x])
# silueta exterior: todo lo que no es fondo exterior
def corre(x, y, dx, dy):
    n = 0
    while 0 <= x < W and 0 <= y < H and not ext[y][x]: x += dx; y += dy; n += 1
    return n
abajo = corre(cx, y1 + 1, 0, 1); izq = corre(x0 - 1, cy, -1, 0); der = corre(x1 + 1, cy, 1, 0)
arriba = corre(cx, y0 - 1, 0, -1)   # incluye cabeza y piedra
ys = [y for y in range(H) for x in range(W) if not ext[y][x]]
top = min(ys); bot = max(ys)
r = {'px_mm': round(1/mm, 2), 'hueco_alto_mm': round((y1-y0+1)*mm, 2),
     'grosor_abajo_mm': round(abajo*mm, 2), 'grosor_izq_mm': round(izq*mm, 2), 'grosor_der_mm': round(der*mm, 2),
     'arriba_del_hueco_mm': round(arriba*mm, 2), 'alto_total_mm': round((bot-top+1)*mm, 2)}
print(json.dumps(r))
if len(sys.argv) > 2:
    dbg = Image.open(sys.argv[1]).convert('RGB'); d = ImageDraw.Draw(dbg)
    d.rectangle([x0, y0, x1, y1], outline=(255, 0, 0)); d.line([cx, y1, cx, y1+abajo], fill=(0, 0, 255), width=2)
    d.line([x0-izq, cy, x0, cy], fill=(0, 160, 0), width=2); d.line([x1, cy, x1+der, cy], fill=(0, 160, 0), width=2)
    dbg.save(sys.argv[2])
