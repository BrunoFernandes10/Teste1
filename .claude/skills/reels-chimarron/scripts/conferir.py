"""Confere um vídeo pronto antes da entrega: formato, áudio e logo fixo em todos os quadros.

Uso: python -I conferir.py <video>
Sai com código 1 se algo reprovar. Não avalia enquadramento: para isso, olhe a folha de quadros (folha.py).
"""
import json
import subprocess
import sys

import numpy as np
from PIL import Image

LOGO = r"C:\Users\PICHAU\Claude\chimarron-delivery-video\assets\logo_chimarron.png"
sys.stdout.reconfigure(encoding="utf-8")

video = sys.argv[1]
info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", video],
                                 capture_output=True, text=True, check=True).stdout)
v = next(s for s in info["streams"] if s["codec_type"] == "video")
a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
w, h = int(v["width"]), int(v["height"])
problemas = []

print(f"Formato: {w}x{h}, {v['r_frame_rate']} fps, {float(info['format']['duration']):.2f} s")
if (w, h) not in ((1080, 1920), (1080, 1350)):
    problemas.append(f"tamanho inesperado {w}x{h}")
if a is None:
    problemas.append("sem áudio")
else:
    print(f"Áudio: {a['sample_rate']} Hz, {a['channels']} canais")
    if a["sample_rate"] != "48000":
        problemas.append(f"áudio em {a['sample_rate']} Hz (o celular só toca bem em 48000)")

# posição do logo como o kit desenha: 280 px no topo 120 (9:16); 229 px no topo 45 (4:5)
lw, top = (280, 120) if h == 1920 else (229, 45)
marca = Image.open(LOGO).convert("RGBA")
lh = round(marca.height * lw / marca.width)
mascara = np.asarray(marca.resize((lw, lh), Image.LANCZOS).getchannel("A")) > 240
x0 = (w - lw) // 2
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", f"format=gray,crop={lw}:{lh}:{x0}:{top}",
                      "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
q = np.frombuffer(raw, np.uint8).reshape(-1, lh, lw)[:, mascara]

# nos pixels das letras, um quadro com logo é quase todo branco (ou marrom escuro no logo "dark").
# Limite: logo marrom sobre fundo escuro (ex.: véu do fechamento) passa mesmo sem logo; confira esse trecho a olho.
branco = np.percentile(q, 30, axis=1) >= 190
marrom = np.percentile(q, 70, axis=1) <= 90
presente = branco if branco.sum() >= marrom.sum() else marrom
falhas = np.where(~presente)[0]
print(f"Logo: {presente.sum()}/{len(q)} quadros ({'branco' if presente is branco else 'marrom'})")
if len(falhas):
    trechos, ini = [], falhas[0]
    for i, j in zip(falhas, list(falhas[1:]) + [None]):
        if j != i + 1:
            trechos.append(f"{ini / 24:.2f}-{i / 24:.2f}s")
            ini = j
    problemas.append(f"logo falha em {len(falhas)} quadros: {', '.join(trechos[:8])}")

if problemas:
    print("REPROVADO:")
    for p in problemas:
        print(" -", p)
    sys.exit(1)
print("APROVADO (falta olhar o enquadramento na folha de quadros)")
