"""Página do Q*bert ao vivo com o Laya: Laya, robô de código ou você no teclado.

O Laya (github.com/NandhaKishorM/laya, Apache-2.0) é carregado dentro deste servidor, na placa de vídeo.
Na primeira vez baixa o modelo do Hugging Face (~800 MB) para D:\\Mateus\\.hf-cache.

Uso:
    .venv\\Scripts\\python.exe qbert\\servidor_laya.py
    abrir http://127.0.0.1:8768
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import math
import os
from pathlib import Path
import threading
import time
import uuid

os.environ.setdefault("HF_HOME", r"D:\Mateus\.hf-cache")

from estado_compacto import compactar  # noqa: E402
from qbert_env import APROXIMACOES, QbertEnv, bot_scores  # noqa: E402

HERE = Path(__file__).resolve().parent
RECORDE = HERE / "recorde.json"  # recorde e nome, como no placar do Odyssey ("0000→??????")
INSTRUCTIONS = ("Choose the next action that maximizes the probability of completing the stated task successfully "
                "before its deadline. Use the visible state, action descriptions, remaining time, and recorded history.")
# Situação enxuta (estado_compacto.py): ~190 tokens, cabe no limite de 512 do Laya — mesmo formato do treino.
MAX_LEN = 512
SESSIONS, LOCK = {}, threading.Lock()
LAYA = {"agent": None, "erro": None, "gpu": threading.Lock()}


def carregar_laya(device, modelo):
    try:
        import laya
        t0 = time.time()
        LAYA["agent"] = laya.load(modelo, device=device)
        LAYA["modelo"] = modelo
        print(f"Laya carregado em {time.time() - t0:.0f}s ({device}): {modelo}", flush=True)
    except Exception as e:  # mostra o erro na página em vez de derrubar o servidor
        LAYA["erro"] = f"{type(e).__name__}: {e}"
        print("Falha ao carregar o Laya:", LAYA["erro"], flush=True)


def ask_model(obs):
    if LAYA["erro"]:
        raise RuntimeError(f"o Laya não carregou: {LAYA['erro']}")
    if LAYA["agent"] is None:
        raise RuntimeError("o Laya ainda está carregando; tente de novo em alguns segundos")
    questions = {"action": {"type": "choice", "instructions": INSTRUCTIONS, "criteria": obs["candidates"]}}
    with LAYA["gpu"]:
        answer = LAYA["agent"].predict(compactar(obs["state"]), questions, max_len=MAX_LEN)["answers"]["action"]
    return answer["probabilities"], answer["choice"]


def load_record():
    try:
        return json.loads(RECORDE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"odyssey": {"score": 0, "name": ""}, "arcade": {"score": 0, "name": ""}}


def save_record(ruleset, score, name):
    with LOCK:
        record = load_record()
        if score > record.get(ruleset, {}).get("score", 0):
            record[ruleset] = {"score": score, "name": name}
            RECORDE.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        return record


def softmax(scores, temperature=8.0):
    top = max(scores.values())
    exp = {k: math.exp((v - top) / temperature) for k, v in scores.items()}
    total = sum(exp.values())
    return {k: v / total for k, v in exp.items()}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def receive_video(self):
        """Recebe o .webm gravado pela página, salva em qbert/videos e converte para MP4."""
        try:
            from converter_video import SAIDA, converter
            size = int(self.headers.get("Content-Length", 0))
            if not 0 < size <= 2 * 2**30:
                raise ValueError("vídeo vazio ou grande demais")
            nome = "qbert_laya_" + time.strftime("%Y%m%d_%H%M%S")
            SAIDA.mkdir(exist_ok=True)
            webm = SAIDA / f"{nome}.webm"
            with open(webm, "wb") as f:
                left = size
                while left:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            mp4 = converter(webm)
            webm.unlink(missing_ok=True)  # o .webm era só intermediário
            self.send_json(200, {"mp4": str(mp4), "mb": round(mp4.stat().st_size / 2**20, 1)})
        except Exception as e:
            self.send_json(400, {"error": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        self.path = self.path.split("?", 1)[0]  # ignora parâmetros como ?auto=bot
        if self.path in ("/", "/index.html"):
            body = (HERE / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/regras":
            self.send_json(200, {"aproximacoes": APROXIMACOES, "recorde": load_record()})
        elif self.path == "/api/health":
            self.send_json(200, {"laya_pronto": LAYA["agent"] is not None, "erro": LAYA["erro"], "modelo": LAYA.get("modelo")})
        else:
            self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        if self.path.startswith("/api/video"):
            return self.receive_video()
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path == "/api/recorde":
                name = "".join(ch for ch in str(data.get("name", "")).upper() if ch.isalnum() or ch == " ")[:6]
                s = SESSIONS[data["sid"]]
                env = s["env"]
                if not env.terminated or s.get("recorded"):
                    raise ValueError("só dá para gravar o recorde no fim da partida, uma vez")
                s["recorded"] = True
                self.send_json(200, {"recorde": save_record(env.ruleset, env.score, name or "??????")})
                return
            if self.path == "/api/new":
                lives = int(data["lives"]) if data.get("lives") else None
                env = QbertEnv(level=int(data.get("level", 1)), lives=lives,
                               max_steps=int(data.get("max_steps", 250)),
                               stop_at_round_end=not data.get("continue_rounds", False),
                               ruleset=data.get("ruleset", "odyssey"))
                obs = env.reset(int(data.get("seed", 1)))
                sid = uuid.uuid4().hex
                with LOCK:
                    SESSIONS[sid] = {"env": env, "obs": obs}
                self.send_json(200, {"sid": sid, "view": env.view(), "state_text": obs["state"]})
            elif self.path == "/api/step":
                s = SESSIONS[data["sid"]]
                env, obs = s["env"], s["obs"]
                if env.terminated:
                    raise ValueError("partida já terminou")
                player = data.get("player", "model")
                started = time.perf_counter()
                probs = None
                if player == "human":
                    choice = data["action"]
                elif player == "bot":
                    probs = softmax(bot_scores(env))
                    choice = max(probs, key=probs.get)
                else:
                    probs, choice = ask_model(obs)
                seconds = time.perf_counter() - started
                obs, reward, terminated, truncated, info = env.step(choice)
                s["obs"] = obs
                self.send_json(200, {"view": env.view(), "state_text": obs["state"], "choice": choice,
                                     "probabilities": probs, "events": info["events"], "seconds": seconds})
            else:
                self.send_json(404, {"error": "not_found"})
        except Exception as e:
            self.send_json(400, {"error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=8768)
    p.add_argument("--device", default="cuda", help="cuda (placa de vídeo) ou cpu")
    p.add_argument("--modelo", default=str(HERE.parent / "runs" / "laya_qbert_v1" / "melhor"),
                   help="pasta do Laya treinado, ou convaiinnovations/laya para o original")
    a = p.parse_args()
    threading.Thread(target=carregar_laya, args=(a.device, a.modelo), daemon=True).start()  # a página abre já
    print(f"Q*bert com Laya em http://127.0.0.1:{a.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
