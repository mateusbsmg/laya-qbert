"""Gera ARTIGO_LINKEDIN_LAYA_post.txt: o artigo com "negrito" em letras Unicode (o post do LinkedIn não aceita
formatação). Título e títulos de seção ficam em negrito; confere o limite de 3.000 caracteres.

Uso: .venv\\Scripts\\python.exe gerar_post_linkedin.py
"""
import re
import sys
import unicodedata
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def bold(text):
    """Letras e números em 'Mathematical Sans-Serif Bold'; acento vira letra negrito + acento combinado."""
    res = []
    for ch in unicodedata.normalize("NFD", text):
        o = ord(ch)
        if "A" <= ch <= "Z":
            res.append(chr(0x1D5D4 + o - ord("A")))
        elif "a" <= ch <= "z":
            res.append(chr(0x1D5EE + o - ord("a")))
        elif "0" <= ch <= "9":
            res.append(chr(0x1D7EC + o - ord("0")))
        else:
            res.append(ch)
    return "".join(res)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    md = (AQUI / "ARTIGO_LINKEDIN_LAYA.md").read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n")
    linhas = []
    for line in md.split("\n"):
        if line.startswith("# "):
            linhas.append(bold(line[2:]))
        else:
            linhas.append(re.sub(r"\*\*(.+?)\*\*", lambda m: bold(m.group(1)), line))
    texto = "\n".join(linhas)
    (AQUI / "ARTIGO_LINKEDIN_LAYA_post.txt").write_text(texto + "\n", encoding="utf-8")
    plano = re.sub(r"(?m)^# ", "", md.replace("**", ""))
    palavras = len([w for w in plano.split() if re.search(r"\w", w)])
    utf16 = len(texto.encode("utf-16-le")) // 2
    print(f"{palavras} palavras | texto normal {len(plano)} caracteres | post com negrito {utf16} (limite 3.000)")


if __name__ == "__main__":
    main()
