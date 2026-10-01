"""Converte o vídeo gravado na página do Q*bert (.webm) para MP4 (opcional: aumentar com pixels nítidos).

Sem argumentos, pega o qbert_*.webm mais recente da pasta Downloads.
Uso:
    .venv\\Scripts\\python.exe qbert\\converter_video.py
    .venv\\Scripts\\python.exe qbert\\converter_video.py caminho\\do\\video.webm --escala 2
Saída: mesmo nome, com .mp4 (H.264), na pasta D:\\Mateus\\NanoJev\\qbert\\videos\\
"""
import argparse
from pathlib import Path
import subprocess
import sys

import imageio_ffmpeg

SAIDA = Path(__file__).resolve().parent / "videos"


def converter(origem, escala=1):
    """Converte `origem` (.webm) para MP4 em qbert/videos/ e devolve o caminho do MP4."""
    SAIDA.mkdir(exist_ok=True)
    destino = SAIDA / (Path(origem).stem + ".mp4")
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(origem),
           "-vf", f"fps=30,scale=iw*{escala}:ih*{escala}:flags=neighbor,pad=ceil(iw/2)*2:ceil(ih/2)*2",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", str(destino)]
    subprocess.run(cmd, check=True)
    return destino


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("video", nargs="?", help="arquivo .webm (padrão: o qbert_*.webm mais recente em Downloads)")
    p.add_argument("--escala", type=int, default=1, help="aumenta o tamanho N vezes, sem borrar os pixels (padrão: igual)")
    a = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.video:
        origem = Path(a.video)
    else:
        candidatos = sorted((Path.home() / "Downloads").glob("qbert_*.webm"), key=lambda f: f.stat().st_mtime)
        if not candidatos:
            sys.exit("Nenhum qbert_*.webm encontrado em Downloads. Grave pelo botão '⏺ Gravar 3 min' da página.")
        origem = candidatos[-1]
    destino = converter(origem, a.escala)
    print(f"Pronto: {destino}  ({destino.stat().st_size / 2**20:.1f} MB)")


if __name__ == "__main__":
    main()
