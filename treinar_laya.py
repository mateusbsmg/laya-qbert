"""Fine-tuning do Laya no Q*bert, imitando as notas do professor (mesmos exemplos usados no NanoJev).

- Entrada: D:\\Mateus\\NanoJev\\qbert\\dados\\{train,dev}.jsonl (30 mil decisões geradas pelo professor).
- Situação em versão enxuta (qbert/estado_compacto.py): ~190 tokens, cabe no limite de 512 do Laya.
- Notas do professor recalculadas com temperatura 4 (mais "decididas"), como no treino v2 do NanoJev.
- Perda: entropia cruzada entre as notas do professor e as do Laya.
- Proteções: pausas se a placa passar de 75 °C, teto de memória, ponto de retomada, guarda a melhor versão.
- Saída: uma pasta que abre com laya.load(pasta) (rl_agent_config.json + model.safetensors + tokenizer/ + encoder/).

Uso:
    .venv\\Scripts\\python.exe treinar_laya.py --passos 20 --saida runs\\teste        (teste curto)
    .venv\\Scripts\\python.exe treinar_laya.py --passos 1500 --saida runs\\laya_qbert_v1
"""
import argparse
import glob
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time

os.environ.setdefault("HF_HOME", r"D:\Mateus\.hf-cache")
AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI / "qbert"))

import torch  # noqa: E402
from safetensors.torch import save_file  # noqa: E402

import laya  # noqa: E402
from laya.common import collate_items  # noqa: E402
from estado_compacto import compactar  # noqa: E402

INSTR = ("Choose the next action that maximizes the probability of completing the stated task successfully "
         "before its deadline. Use the visible state, action descriptions, remaining time, and recorded history.")
DADOS = Path(r"D:\Mateus\NanoJev\qbert\dados")


def gpu_temp():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout
        return int(out.strip().splitlines()[0])
    except Exception:
        return None


def esfriar(alvo, retomar):
    t = gpu_temp()
    if t is None or t <= alvo:
        return 0.0, t
    inicio = time.time()
    while t is not None and t > retomar and time.time() - inicio < 600:
        time.sleep(5)
        t = gpu_temp()
    return time.time() - inicio, t


def notas_professor(row, temperatura):
    vals = row["metadata"]["values"]
    top = max(vals.values())
    exp = {k: math.exp((v - top) / temperatura) for k, v in vals.items()}
    s = sum(exp.values())
    return {k: e / s for k, e in exp.items()}


def preparar(agent, rows, temperatura):
    """Uma linha de treino -> item do Laya (tokens, posições das opções) + alvo na ordem das opções."""
    itens = []
    for r in rows:
        crit = r["questions"]["action"]["criteria"]
        q = {"type": "choice", "instructions": INSTR, "criteria": crit}
        item = agent._encode_state(compactar(r["state"]), ["action"], {"action": agent._to_internal(q)})[0]
        alvo = notas_professor(r, temperatura)
        item["target"] = [alvo[k] for k in crit]  # mesma ordem dos marcadores (ordem das opções)
        itens.append(item)
    return itens


def perda(logits, lote):
    alvo = lote["target"].to(logits.device)
    logp = torch.log_softmax(logits.float().masked_fill(~lote["marker_mask"].to(logits.device), -1e4), -1)
    return -(alvo * logp).sum(-1)


@torch.no_grad()
def avaliar(model, itens, pad_id, dev, cfg):
    model.eval()
    ce, acordo, n = 0.0, 0, 0
    for i in range(0, len(itens), 32):
        esfriar(cfg.temp_alvo, cfg.temp_retomar)
        lote = collate_items([[it] for it in itens[i:i + 32]], pad_id)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            logits, _ = model(lote["input_ids"].to(dev), lote["attention_mask"].to(dev), lote["marker_pos"].to(dev),
                              lote["marker_mask"].to(dev), lote["qtype"].to(dev))
        ce += perda(logits, lote).sum().item()
        k = lote["marker_mask"].sum(-1)
        for j in range(len(k)):
            acordo += int(logits[j, :k[j]].argmax() == lote["target"][j, :k[j]].argmax())
        n += len(k)
    model.train()
    return {"ce": ce / n, "concorda_com_professor": acordo / n, "exemplos": n}


def salvar(model, snap, pasta, info):
    pasta.mkdir(parents=True, exist_ok=True)
    save_file({k: v.detach().to("cpu").contiguous() for k, v in model.state_dict().items()},
              str(pasta / "model.safetensors"))
    for d in ("tokenizer", "encoder"):
        if (snap / d).exists():
            shutil.copytree(snap / d, pasta / d, dirs_exist_ok=True)
    cfg = json.loads((snap / "rl_agent_config.json").read_text(encoding="utf-8"))
    cfg["temperature"] = [1.0, 1.0, 1.0]      # calibração original era da triagem; aqui as notas já vêm do treino
    cfg["temperature_by_options"] = {}
    cfg["qbert_training"] = info
    (pasta / "rl_agent_config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--saida", required=True)
    p.add_argument("--passos", type=int, default=1500)
    p.add_argument("--lote", type=int, default=32, help="situações por passo")
    p.add_argument("--lr-encoder", type=float, default=2e-5)
    p.add_argument("--lr-cabeca", type=float, default=1e-4)
    p.add_argument("--temp-professor", type=float, default=4.0)
    p.add_argument("--avaliar-cada", type=int, default=150)
    p.add_argument("--salvar-cada", type=int, default=25)
    p.add_argument("--limite-avaliacao", type=int, default=600)
    p.add_argument("--temp-alvo", type=int, default=75)
    p.add_argument("--temp-retomar", type=int, default=68)
    p.add_argument("--teto-gpu-gb", type=float, default=10.0)
    p.add_argument("--seed", type=int, default=17)
    a = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    torch.manual_seed(a.seed)
    out = AQUI / a.saida
    out.mkdir(parents=True, exist_ok=True)
    dev = torch.device("cuda:0")
    total = torch.cuda.get_device_properties(0).total_memory
    torch.cuda.set_per_process_memory_fraction(min(1.0, a.teto_gpu_gb * 2**30 / total), 0)

    snap = Path(glob.glob(r"D:\Mateus\.hf-cache\hub\models--convaiinnovations--laya\snapshots\*")[0])
    agent = laya.load(str(snap), device="cuda")
    model = agent.model
    model.float().to(dev)
    if hasattr(model.encoder, "gradient_checkpointing_enable"):
        model.encoder.gradient_checkpointing_enable()
    model.head_checkpointing = True
    model.train()
    pad_id = agent.tok.pad_token_id

    t0 = time.time()
    rng = random.Random(a.seed)
    treino = [json.loads(l) for l in open(DADOS / "train.jsonl", encoding="utf-8")]
    validacao = [json.loads(l) for l in open(DADOS / "dev.jsonl", encoding="utf-8")]
    random.Random(a.seed).shuffle(validacao)
    itens_dev = preparar(agent, validacao[:a.limite_avaliacao], a.temp_professor)
    print(f"dados: treino {len(treino)} | validação {len(itens_dev)} | preparo {time.time() - t0:.0f}s", flush=True)

    enc = [p_ for n, p_ in model.named_parameters() if n.startswith("encoder.")]
    cab = [p_ for n, p_ in model.named_parameters() if not n.startswith("encoder.")]
    opt = torch.optim.AdamW([{"params": enc, "lr": a.lr_encoder}, {"params": cab, "lr": a.lr_cabeca}],
                            weight_decay=0.01, fused=True)
    info = {k: v for k, v in vars(a).items()}

    inicio, pausas, decorrido_antes, log = 1, 0.0, 0.0, []
    ret = out / "retomar.pt"
    if ret.exists():
        st = torch.load(ret, map_location=dev, weights_only=False)
        model.load_state_dict(st["modelo"])
        opt.load_state_dict(st["otimizador"])
        rng.setstate(st["sorteio"])
        log, pausas, decorrido_antes, inicio = st["log"], st["pausas"], st["decorrido"], st["passo"] + 1
        print(f"retomando do passo {st['passo']}", flush=True)
    else:
        ev = avaliar(model, itens_dev, pad_id, dev, a)
        print("antes do treino:", json.dumps(ev, ensure_ascii=False), flush=True)
        log.append({"passo": 0, **ev})

    t_treino = time.time() - decorrido_antes
    for passo in range(inicio, a.passos + 1):
        ts = time.time()
        lote = collate_items([[it] for it in preparar(agent, rng.sample(treino, a.lote), a.temp_professor)], pad_id)
        opt.zero_grad(set_to_none=True)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            logits, _ = model(lote["input_ids"].to(dev), lote["attention_mask"].to(dev), lote["marker_pos"].to(dev),
                              lote["marker_mask"].to(dev), lote["qtype"].to(dev))
        loss = perda(logits, lote).mean()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(enc + cab, 1.0)
        opt.step()
        dur = time.time() - ts
        pausa, temp = esfriar(a.temp_alvo, a.temp_retomar)
        pausas += pausa
        decorrido = time.time() - t_treino
        falta = decorrido / passo * (a.passos - passo)
        mem = torch.cuda.max_memory_allocated() / 2**30
        print(f"passo {passo}/{a.passos}: perda {loss.item():.4f} | {dur:.1f}s + pausa {pausa:.0f}s (placa {temp} C)"
              f" | memória pico {mem:.2f} GB | falta ~{falta / 60:.0f} min", flush=True)
        if passo % a.avaliar_cada == 0 or passo == a.passos:
            ev = avaliar(model, itens_dev, pad_id, dev, a)
            print(f"avaliação passo {passo}:", json.dumps(ev, ensure_ascii=False), flush=True)
            anteriores = [e["ce"] for e in log]
            log.append({"passo": passo, **ev})
            if not anteriores or ev["ce"] < min(anteriores):
                salvar(model, snap, out / "melhor", {**info, "passo": passo, **ev})
                print(f"melhor versão até agora (passo {passo}) salva em {out / 'melhor'}", flush=True)
        (out / "log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
        u = log[-1]
        (out / "progresso.txt").write_text(
            f"Treino do Laya no Q*bert\nPasso {passo} de {a.passos} ({100 * passo / a.passos:.0f}%)\n"
            f"Tempo decorrido: {decorrido / 60:.0f} min | falta ~{falta / 60:.0f} min "
            f"(término ~{time.strftime('%H:%M', time.localtime(time.time() + falta))})\n"
            f"Placa: {temp} C | pausas para esfriar: {pausas / 60:.0f} min | memória pico {mem:.2f} GB\n"
            f"Última avaliação (passo {u['passo']}): concorda com o professor em {100 * u['concorda_com_professor']:.0f}%"
            f" | erro {u['ce']:.3f}\n", encoding="utf-8")
        if passo % a.salvar_cada == 0 and passo < a.passos:
            tmp = out / "retomar.pt.tmp"
            torch.save({"modelo": model.state_dict(), "otimizador": opt.state_dict(), "sorteio": rng.getstate(),
                        "log": log, "pausas": pausas, "decorrido": time.time() - t_treino, "passo": passo}, tmp)
            os.replace(tmp, ret)

    salvar(model, snap, out / "final", {**info, "passo": a.passos})
    ret.unlink(missing_ok=True)
    print(f"modelo salvo em {out / 'final'}", flush=True)


if __name__ == "__main__":
    main()
