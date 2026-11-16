"""Folha de quadros de um vídeo, com o instante escrito em cada um.

Busca cada quadro direto (-ss), sem decodificar o vídeo inteiro: em 4K vindo do Drive isso é bem mais rápido.

Uso:
  python -I folha.py <video> <saida.jpg> --cada 5              # um quadro a cada 5 s
  python -I folha.py <video> <saida.jpg> --em 1 4 7.5 12       # instantes exatos
Opções: --colunas 8, --largura 240
"""
import argparse
import io
import math
import subprocess
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageDraw, ImageFont

ap = argparse.ArgumentParser()
ap.add_argument("video")
ap.add_argument("saida")
ap.add_argument("--cada", type=float)
ap.add_argument("--em", type=float, nargs="+")
ap.add_argument("--colunas", type=int, default=8)
ap.add_argument("--largura", type=int, default=240)
a = ap.parse_args()
if not a.cada and not a.em:
    ap.error("use --cada ou --em")

if a.em:
    tempos = a.em
else:
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", a.video],
                               capture_output=True, text=True, check=True).stdout)
    tempos = [i * a.cada for i in range(math.ceil(dur / a.cada))]


def quadro(t):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", a.video, "-frames:v", "1",
                        "-vf", f"scale={a.largura}:-2", "-f", "image2pipe", "-c:v", "png", "-"], capture_output=True)
    return Image.open(io.BytesIO(r.stdout)).convert("RGB") if r.stdout else None


with ThreadPoolExecutor(4) as ex:
    quadros = list(ex.map(quadro, tempos))
validos = [(t, q) for t, q in zip(tempos, quadros) if q is not None]
if not validos:
    raise SystemExit("nenhum quadro lido")

w, h = validos[0][1].size
linhas = math.ceil(len(validos) / a.colunas)
folha = Image.new("RGB", (w * min(a.colunas, len(validos)), h * linhas))
fonte = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 22)
for i, (t, q) in enumerate(validos):
    d = ImageDraw.Draw(q)
    d.text((6, 4), f"{t:g}", font=fonte, fill=(255, 230, 0), stroke_width=2, stroke_fill=(0, 0, 0))
    folha.paste(q, (i % a.colunas * w, i // a.colunas * h))
folha.save(a.saida, quality=85)
faltam = len(tempos) - len(validos)
print(f"OK {a.saida}: {len(validos)} quadros" + (f", {faltam} não lidos" if faltam else ""))
