"""Versão enxuta da situação do Q*bert para o Laya (que foi treinado com textos de até 512 tokens).

Pega o texto completo gerado por qbert_env.py e mantém só o que muda de uma jogada para outra:
nível/regra de cor, pirâmide, posição, vidas, discos, inimigos, tempo e as 3 últimas jogadas.
O parágrafo fixo de regras sai: é igual em toda jogada, e o modelo aprende as regras pelos exemplos.
Usada tanto para converter os exemplos de treino quanto na hora de jogar (mesmo formato nos dois).
"""
import json
import re


def _g(padrao, texto, grupo=1, flags=0):
    m = re.search(padrao, texto, flags)
    return m.group(grupo) if m else ""


def compactar(texto: str) -> str:
    nivel = _g(r"Level (\d+), round (\d+)\.", texto)
    rodada = _g(r"Level (\d+), round (\d+)\.", texto, 2)
    regra = _g(r"Color rule: (.*?)\. Cube colors", texto)
    linhas = _g(r"2=target\):\n(.*?)\nCubes not yet target", texto, flags=re.S).split("\n")
    faltam = _g(r"Cubes not yet target: (\d+)", texto)
    q = _g(r"Q\*bert at (\[[^\]]*\])", texto)
    vidas = _g(r"Lives: (\d+)", texto)
    discos = _g(r"Discs available: (.*?)\. Enemies:", texto)
    discos = re.sub(r" \(reached by (up_left|up_right) from (\[[^\]]*\])\)", r" via \1 from \2", discos)
    inimigos = json.loads(_g(r"Enemies: (\[.*?\])\. Enemies frozen", texto) or "[]")
    congelados = _g(r"Enemies frozen for (\d+) more steps", texto)
    restam = _g(r"Remaining: (\d+)\. Outcome", texto)
    historico = json.loads(_g(r"Recent steps: (\[.*\])\.\s*$", texto, flags=re.S) or "[]")

    partes = [
        f"Q*bert game. Level {nivel}, round {rodada}. Color rule: {regra}.",
        "Cubes by row (0=start, 1=intermediate, 2=target): " + " ".join(linhas) + f". Not yet target: {faltam}.",
        f"Q*bert at {q}. Lives {vidas}. Steps left {restam}.",
        f"Discs: {discos or 'none'}.",
        "Enemies: " + (", ".join(f"{e['type']} at {json.dumps(e['position'], separators=(',', ':'))}"
                                 for e in inimigos) or "none") + (f" (frozen {congelados} steps)" if congelados not in ("", "0") else "") + ".",
    ]
    if historico:
        ult = []
        for h in historico[-3:]:
            ev = [e for e in h.get("events", []) if e != "color_change"]
            ult.append(f"{h['action']} {json.dumps(h['from'], separators=(',', ':'))}->"
                       f"{json.dumps(h['to'], separators=(',', ':'))}" + (f" ({', '.join(ev)})" if ev else ""))
        partes.append("Last moves: " + "; ".join(ult) + ".")
    return " ".join(partes)
