"""Q*bert com regras do arcade, em versão por turnos para o NanoJev.

Cada passo = um pulo (ou uma espera) do Q*bert; depois os inimigos se movem.
Tudo é determinístico a partir da semente, como os jogos do autor.

Pirâmide: 7 fileiras, 28 cubos. Coordenada [fileira, posição]:
fileira 0 é o cubo do topo; a fileira r tem posições 0..r.
    up_right   -> [r-1, p]      up_left   -> [r-1, p-1]
    down_right -> [r+1, p+1]    down_left -> [r+1, p]
Pular para fora da pirâmide custa uma vida, exceto se cair num disco.
Um disco à esquerda fica em [d, -1] (alcançado com up_left a partir de [d+1, 0]);
um disco à direita fica em [d, d+1] (alcançado com up_right a partir de [d+1, d+1]).

Regras de cor por nível (0 = cor inicial, 1 = intermediária, 2 = cor-alvo):
    nível 1: 0->2                 nível 2: 0->1->2
    nível 3: 0->2, 2->0 (alterna) nível 4: 0->1->2, 2->1
    nível 5+: 0->1->2, 2->0
Cada nível tem 4 rodadas. Rodada vencida quando os 28 cubos estão na cor-alvo.

Personagens (arcade):
    red_ball    desce pulando ao acaso; mata ao tocar; some ao sair por baixo.
    purple_ball desce até a última fileira e vira o Coily.
    coily       persegue o Q*bert; morre se o Q*bert fugir por um disco (+500).
    green_ball  ao ser tocada congela os inimigos por alguns passos (+100).
    sam/slick   descem desfazendo as cores dos cubos; tocar neles dá +300.
    ugg/wrongway andam de lado a partir dos cantos de baixo; matam ao tocar.

Adaptações por ser por turnos (o arcade é em tempo real) — ver APROXIMACOES.
"""
from collections import deque
import copy
import json
import random

ROWS = 7
CELLS = [(r, p) for r in range(ROWS) for p in range(r + 1)]
MOVES = {"up_right": (-1, 0), "up_left": (-1, -1), "down_right": (1, 1), "down_left": (1, 0)}
ACTIONS = ("up_right", "up_left", "down_right", "down_left", "wait")
DEADLY = {"red_ball", "purple_ball", "coily", "ugg", "wrongway"}
FRIENDLY = {"green_ball", "sam", "slick"}

TRANSITIONS = {1: {0: 2, 2: 2}, 2: {0: 1, 1: 2, 2: 2}, 3: {0: 2, 2: 0},
               4: {0: 1, 1: 2, 2: 1}, 5: {0: 1, 1: 2, 2: 0}}
RULE_TEXT = {
    1: "one landing turns a cube to the target color; target cubes stay target",
    2: "first landing gives the intermediate color, second landing gives the target color; target cubes stay target",
    3: "one landing turns a cube to the target color; landing on a target cube turns it back to the starting color",
    4: "first landing gives the intermediate color, second gives the target color; landing on a target cube turns it back to intermediate",
    5: "first landing gives the intermediate color, second gives the target color; landing on a target cube turns it back to the starting color",
}
FREEZE_STEPS = 6

# Duas versões de regras. "odyssey" segue o manual brasileiro (Philips/Parker) e o vídeo da VGDB;
# "arcade" segue a máquina original da Gottlieb.
RULESETS = {
    "odyssey": {"lives": 7, "max_level": 9, "extra_first": 300, "extra_every": 300, "top_landing_points": True,
                "max_coilies": 3, "stage_bonus": lambda rounds_played: 50,
                "points": {"color_change": 1, "green_ball": 0, "sam": 0, "slick": 0, "coily_lured": 25, "unused_disc": 0}},
    "arcade": {"lives": 3, "max_level": None, "extra_first": 8000, "extra_every": 14000, "top_landing_points": False,
               "max_coilies": 1, "stage_bonus": lambda rounds_played: min(5000, 1000 + 250 * (rounds_played - 1)),
               "points": {"color_change": 25, "green_ball": 100, "sam": 300, "slick": 300, "coily_lured": 500,
                          "unused_disc": 50}},
}
POINTS = RULESETS["arcade"]["points"]  # compatibilidade

APROXIMACOES = {
    "odyssey": [
        "Confirmado no manual/vídeo: 7 Q*berts; +1 ponto por cubo; +25 pela Serpente no disco; +50 por etapa; "
        "Q*bert extra a cada 300 pontos; 9 níveis × 4 etapas; +1 ao pousar no topo no início da etapa; "
        "várias Serpentes ao mesmo tempo; inimigos somem quando o Q*bert perde uma vida; o Manhoso (verde) deixa cubos brancos.",
        "Cores de cada etapa copiadas do vídeo para os níveis 1–4 (nível 4 só a etapa 1 foi vista).",
        "Níveis 5–9 CRIADOS AQUI (não aparecem no vídeo nem no manual): cores próprias, moldura própria, menos discos "
        "nos níveis 7–9 (3, 3, 2), inimigos chegando mais rápido (a cada passo nos níveis 8–9) e até 6 na tela.",
        "Regras de cor dos níveis 5–9 não aparecem no vídeo nem no manual: usa a do arcade (intermediária; alvo volta ao início).",
        "Tempo real virou turnos: 1 passo = 1 pulo do Q*bert (ou esperar), depois cada inimigo anda conforme seu ritmo.",
        "Pula-Pula não foi identificado com clareza no vídeo; comporta-se como Ugg/Wrongway do arcade (anda de lado a partir da base).",
        "Pegar o Paralizante Verde ou o Manhoso não dá pontos (o manual não cita pontos para eles).",
        "Quais inimigos aparecem, o intervalo entre eles e a posição dos discos seguem uma tabela aproximada.",
    ],
    "arcade": [
        "Tempo real virou turnos: 1 passo = 1 pulo do Q*bert (ou esperar), depois cada inimigo anda conforme seu ritmo.",
        "Ritmos: bolas, Sam/Slick andam todo passo; Coily anda 2 de cada 3 passos no nível 1 e todo passo depois; Ugg/Wrongway a cada 2 passos.",
        "Ao usar um disco o Coily sempre é atraído e cai (+500) e os demais inimigos somem.",
        "Ugg/Wrongway andam pelas laterais dos cubos no arcade; aqui ocupam o próprio cubo (tocar = perder vida).",
        "Quais inimigos aparecem em cada rodada e o intervalo entre eles seguem uma tabela aproximada, não a da máquina original.",
        "Bônus de rodada: 1000 + 250 por rodada já jogada (máx. 5000) + 50 por disco não usado.",
    ],
}


def _dist_table():
    table = {}
    for start in CELLS:
        dist, queue = {start: 0}, deque([start])
        while queue:
            cell = queue.popleft()
            for dr, dp in MOVES.values():
                nxt = (cell[0] + dr, cell[1] + dp)
                if on_pyramid(nxt) and nxt not in dist:
                    dist[nxt] = dist[cell] + 1
                    queue.append(nxt)
        table[start] = dist
    return table


def on_pyramid(cell):
    r, p = cell
    return 0 <= r < ROWS and 0 <= p <= r


DIST = None


def distance(a, b):
    global DIST
    if DIST is None:
        DIST = _dist_table()
    return DIST[tuple(a)][tuple(b)]


def dest(cell, action):
    if action == "wait":
        return tuple(cell)
    dr, dp = MOVES[action]
    return cell[0] + dr, cell[1] + dp


def _j(value):
    return json.dumps(value, separators=(",", ":"))


class QbertEnv:
    """Ambiente por turnos. reset(seed) -> obs; step(action) -> obs, reward, terminated, truncated, info."""

    def __init__(self, level=1, lives=None, max_steps=250, stop_at_round_end=True, history_limit=8, ruleset="odyssey"):
        if level not in range(1, 10):
            raise ValueError("level deve ficar entre 1 e 9")
        if ruleset not in RULESETS:
            raise ValueError("ruleset deve ser 'odyssey' ou 'arcade'")
        self.ruleset, self.rs = ruleset, RULESETS[ruleset]
        self.points = self.rs["points"]
        self.start_level, self.start_lives = level, lives or self.rs["lives"]
        self.max_steps, self.stop_at_round_end, self.history_limit = max_steps, stop_at_round_end, history_limit

    # ------------------------------------------------------------ preparação
    def reset(self, seed):
        self.seed = seed
        self.rng = random.Random(seed)
        self.level, self.round, self.rounds_played = self.start_level, 1, 1
        self.lives, self.score, self.steps = self.start_lives, 0, 0
        self.next_extra_life = self.rs["extra_first"]
        self.terminated = self.success = False
        self.outcome = "in_progress"
        self.history = deque(maxlen=self.history_limit)
        self.rounds_cleared = 0
        self._new_round()
        return self.observe()

    def _new_round(self):
        self.colors = {cell: 0 for cell in CELLS}
        self.spoiled = set()  # cubos que o Manhoso deixou brancos (Odyssey); para o jogo valem como cor inicial
        self.q = (0, 0)
        self.colors[self.q] = TRANSITIONS[min(self.level, 5)][0]  # começa no topo já pintado (como na tela original)
        if self.rs["top_landing_points"]:
            self.score += self.points["color_change"]  # Odyssey: +1 ao pousar no topo (visto no vídeo)
        self.enemies, self.enemy_seq = [], 0
        self.frozen = 0
        self.spawn_count = 0
        self.next_spawn = self.steps + 3
        # níveis 1–4: visto no vídeo (2, 3, 4, 4); 5–9: criados aqui, menos discos = menos fugas
        n_discs = {1: 2, 2: 3, 7: 3, 8: 3, 9: 2}.get(self.level, 4)
        spots = [(d, -1) for d in range(1, 6)] + [(d, d + 1) for d in range(1, 6)]
        left = [s for s in spots if s[1] == -1]
        right = [s for s in spots if s[1] != -1]
        chosen = [self.rng.choice(left), self.rng.choice(right)]
        rest = [s for s in spots if s not in chosen]
        chosen += self.rng.sample(rest, n_discs - 2)
        self.discs = set(chosen)

    # --------------------------------------------------------------- regras
    def rule(self):
        return TRANSITIONS[min(self.level, 5)]

    def remaining_cubes(self):
        return sum(1 for c in CELLS if self.colors[c] != 2)

    def spawn_kinds(self):
        kinds = ["red_ball", "purple_ball"]
        if self.level > 1 or self.round >= 2:
            kinds.append("green_ball")
        if self.level > 1 or self.round >= 3:
            kinds.append("sam_or_slick")
        if self.level >= 2 or self.round >= 4:
            kinds.append("ugg_or_wrongway")
        return kinds

    def spawn_interval(self):
        if self.level >= 8:                 # níveis 8–9 (criados aqui): um inimigo novo a cada passo
            return 1
        if self.level >= 6:                 # níveis 6–7: a cada passo nas etapas 3–4
            return 1 if self.round >= 3 else 2
        return max(2, 6 - (self.level - 1) - (self.round - 1) // 2)

    def max_enemies(self):
        return 6 if self.level >= 7 else 2 + min(3, self.level)

    def _spawn(self):
        if len(self.enemies) >= self.max_enemies():
            self.next_spawn = self.steps + 1
            return None
        coilies = sum(e["type"] in ("coily", "purple_ball") for e in self.enemies)
        has_coily = coilies >= self.rs["max_coilies"]
        if self.spawn_count == 1 and coilies == 0:
            kind = "purple_ball"  # arcade: o Coily chega logo no começo da rodada
        else:
            kinds = [k for k in self.spawn_kinds() if not (k == "purple_ball" and has_coily)]
            weights = {"red_ball": 5, "purple_ball": 3, "green_ball": 1, "sam_or_slick": 2, "ugg_or_wrongway": 2}
            kind = self.rng.choices(kinds, [weights[k] for k in kinds])[0]
        if kind == "sam_or_slick":
            kind = self.rng.choice(["sam", "slick"])
        if kind == "ugg_or_wrongway":
            kind = self.rng.choice(["ugg", "wrongway"])
        pos = (6, 6) if kind == "ugg" else (6, 0) if kind == "wrongway" else (1, self.rng.randint(0, 1))
        self.enemy_seq += 1
        enemy = {"id": self.enemy_seq, "type": kind, "pos": pos, "age": 0}
        self.enemies.append(enemy)
        self.spawn_count += 1
        self.next_spawn = self.steps + self.spawn_interval()
        if kind in ("sam", "slick"):
            self._spoil(pos)
        return enemy

    def _spoil(self, cell):
        self.colors[cell] = 0
        if self.ruleset == "odyssey":
            self.spoiled.add(tuple(cell))

    def _moves_this_step(self, enemy):
        kind, t = enemy["type"], self.steps
        if kind == "coily":
            return self.level >= 2 or t % 3 != 2
        if kind in ("ugg", "wrongway"):
            return t % 2 == 0
        return True

    def enemy_options(self, enemy):
        """Destinos possíveis de um inimigo no próximo movimento (None = sai da pirâmide)."""
        r, p = enemy["pos"]
        kind = enemy["type"]
        if kind in ("red_ball", "green_ball", "sam", "slick", "purple_ball"):
            if kind == "purple_ball" and r == ROWS - 1:
                return [(r, p)]  # choca e vira Coily
            return [(r + 1, p), (r + 1, p + 1)]
        if kind == "ugg":
            return [(r, p - 1), (r - 1, p - 1)]
        if kind == "wrongway":
            return [(r, p + 1), (r - 1, p)]
        if kind == "coily":
            options = [dest((r, p), a) for a in MOVES]
            return [c for c in options if on_pyramid(c)]
        return []

    def _move_enemy(self, enemy):
        kind = enemy["type"]
        enemy["age"] += 1
        if kind == "purple_ball" and enemy["pos"][0] == ROWS - 1:
            enemy["type"] = "coily"
            return "hatched"
        options = self.enemy_options(enemy)
        if kind == "coily":
            best = min(distance(c, self.q) for c in options)
            options = [c for c in options if distance(c, self.q) == best]
        nxt = self.rng.choice(options)
        if not on_pyramid(nxt):
            return "left_pyramid"
        enemy["pos"] = nxt
        if kind in ("sam", "slick"):
            self._spoil(nxt)
        return "moved"

    # ------------------------------------------------------------- um passo
    def step(self, action):
        if self.terminated:
            raise RuntimeError("partida terminada")
        if action not in ACTIONS:
            raise ValueError(f"ação inválida: {action}")
        events = []
        before = self.q
        self.steps += 1
        target = dest(self.q, action)

        if action != "wait" and not on_pyramid(target):
            if target in self.discs:
                self.discs.discard(target)
                if self.ruleset == "odyssey":
                    # Vídeo: só a Serpente que vem logo atrás segue o Q*bert e cai; os demais inimigos ficam.
                    lured = [e for e in self.enemies if e["type"] == "coily" and distance(e["pos"], before) <= 2]
                    self.enemies = [e for e in self.enemies if e not in lured]
                else:
                    lured = [e for e in self.enemies if e["type"] == "coily"]
                    self.enemies.clear()
                    self.next_spawn = self.steps + 3
                for _ in lured:
                    self._add(events, "coily_lured", self.points["coily_lured"])
                self.q = (0, 0)
                events.append({"event": "rode_disc", "from": list(before), "disc": list(target)})
                self._land(events)
                self._touch(events, self.q, moved_enemies=False)
            else:
                self._lose_life(events, "fell_off", fell=True)
        else:
            self.q = target
            if action != "wait":
                self._land(events)
            self._touch(events, before, moved_enemies=False)

        if not self.terminated and self.remaining_cubes() == 0:
            self._round_cleared(events)

        if not self.terminated and not events_has(events, "round_cleared"):
            if self.frozen > 0:
                self.frozen -= 1
            else:
                prev = {e["id"]: e["pos"] for e in self.enemies}
                for enemy in list(self.enemies):
                    if self._moves_this_step(enemy):
                        result = self._move_enemy(enemy)
                        if result == "left_pyramid":
                            self.enemies.remove(enemy)
                        elif result == "hatched":
                            events.append({"event": "coily_hatched", "at": list(enemy["pos"])})
                self._touch(events, before, moved_enemies=True, prev=prev)
            if not self.terminated and self.steps >= self.next_spawn:
                enemy = self._spawn()
                if enemy:
                    events.append({"event": "enemy_arrived", "type": enemy["type"], "at": list(enemy["pos"])})
                    self._touch(events, self.q, moved_enemies=False)
            if not self.terminated and self.remaining_cubes() == 0:  # (Sam pode desfazer; checagem simétrica)
                self._round_cleared(events)

        if not self.terminated and self.steps >= self.max_steps:
            self._finish("deadline", False)

        while self.score >= self.next_extra_life:
            self.lives += 1
            self.next_extra_life += self.rs["extra_every"]
            events.append({"event": "extra_life"})

        record = {"step": self.steps, "action": action, "from": list(before), "to": list(self.q),
                  "events": [e["event"] for e in events], "terminated": self.terminated, "success": self.success}
        self.history.append(record)
        reward = 1.0 if self.success else 0.0
        return self.observe(), reward, self.terminated, False, {"events": events, "outcome": self.outcome}

    def _add(self, events, name, points):
        self.score += points
        events.append({"event": name, "points": points})

    def _land(self, events):
        self.spoiled.discard(self.q)
        old = self.colors[self.q]
        new = self.rule()[old]
        if new != old:
            self.colors[self.q] = new
            self._add(events, "color_change", self.points["color_change"])

    def _touch(self, events, before, moved_enemies, prev=None):
        for enemy in list(self.enemies):
            same = enemy["pos"] == self.q
            swapped = moved_enemies and prev and prev.get(enemy["id"]) == self.q and enemy["pos"] == before and before != self.q
            if not (same or swapped):
                continue
            kind = enemy["type"]
            if kind in DEADLY:
                self._lose_life(events, f"caught_by_{kind}")
                return
            self.enemies.remove(enemy)
            if kind == "green_ball":
                self.frozen = FREEZE_STEPS
                self._add(events, "caught_green_ball", self.points["green_ball"])
            else:
                self._add(events, f"caught_{kind}", self.points[kind])

    def _lose_life(self, events, reason, fell=False):
        self.lives -= 1
        events.append({"event": "lost_life", "reason": reason})
        self.enemies.clear()
        self.frozen = 0
        self.next_spawn = self.steps + 3
        if fell:
            self.q = (0, 0)
        if self.lives <= 0:
            self._finish("game_over", False)

    def _round_cleared(self, events):
        bonus = self.rs["stage_bonus"](self.rounds_played) + self.points["unused_disc"] * len(self.discs)
        self._add(events, "round_cleared", bonus)
        self.rounds_cleared += 1
        if self.stop_at_round_end:
            self._finish("round_cleared", True)
            return
        if self.rs["max_level"] and self.level == self.rs["max_level"] and self.round == 4:
            self._finish("game_completed", True)  # Odyssey: 9 níveis × 4 etapas
            return
        self.rounds_played += 1
        self.round += 1
        if self.round > 4:
            self.level, self.round = self.level + 1, 1
            events.append({"event": "new_level", "level": self.level})
        self._new_round()

    def _finish(self, outcome, success):
        self.terminated, self.success, self.outcome = True, success, outcome

    # ------------------------------------------------------------ observação
    def candidates(self):
        if self.terminated:
            return {}
        out = {}
        for action in ACTIONS:
            if action == "wait":
                out[action] = f"Stay on {_j(list(self.q))} for one step."
            else:
                name = action.replace("_", "-")
                out[action] = f"Hop {name} to {_j(list(dest(self.q, action)))}."
        return out

    def observe(self):
        rows = []
        for r in range(ROWS):
            rows.append(f"{r}:" + "".join(str(self.colors[(r, p)]) for p in range(r + 1)))
        enemies = [{"type": e["type"], "position": list(e["pos"])} for e in self.enemies]
        discs = sorted(self.discs)
        disc_text = ", ".join(
            f"{_j(list(d))} (reached by up_left from {_j([d[0] + 1, 0])})" if d[1] == -1
            else f"{_j(list(d))} (reached by up_right from {_j([d[0] + 1, d[0] + 1])})" for d in discs) or "none"
        text = (
            "Q*bert on a pyramid of 28 cubes in 7 rows. Coordinates are zero-based [row,position]; row 0 is the top cube "
            "and row r has positions 0..r. Hops: up_right to [row-1,position], up_left to [row-1,position-1], "
            "down_right to [row+1,position+1], down_left to [row+1,position]; wait stays in place. "
            "Hopping off the pyramid loses a life unless the destination is a disc; a disc carries Q*bert to [0,0] "
            + ("and a coily within 2 hops of the take-off cube follows and falls; other enemies stay. " if self.ruleset == "odyssey"
               else "removes all enemies and lures Coily to fall. ")
            + f"Level {self.level}, round {self.round}. Color rule: {RULE_TEXT[min(self.level, 5)]}. "
            "Cube colors by row, one digit per position (0=starting, 1=intermediate, 2=target):\n"
            + "\n".join(rows) + "\n"
            f"Cubes not yet target: {self.remaining_cubes()}. Q*bert at {_j(list(self.q))}. Lives: {self.lives}. "
            f"Score: {self.score}. Discs available: {disc_text}. "
            f"Enemies: {_j(enemies)}. Enemies frozen for {self.frozen} more steps. "
            "red_ball, purple_ball, coily, ugg and wrongway cost a life on contact (same cube, or swapping cubes); "
            "red_ball, purple_ball, green_ball, sam and slick move down one row each step and leave at the bottom; "
            "purple_ball becomes coily at the bottom row; coily moves toward Q*bert; ugg moves left or up_left and wrongway "
            "moves right or up_right every second step; sam and slick reset cubes they land on to the starting color; "
            "catching green_ball freezes enemies, catching sam or slick removes them. "
            f"Scoring: {self.points['color_change']} per cube color change, {self.points['coily_lured']} for luring coily "
            f"off with a disc, {self.rs['stage_bonus'](self.rounds_played)} for clearing the round. "
            f"Task: turn every cube to the target color before {self.max_steps} steps expire without losing all lives. "
            f"Used: {self.steps}. Remaining: {self.max_steps - self.steps}. Outcome: {self.outcome}. "
            f"Recent steps: {_j(list(self.history))}."
        )
        return {"state": text, "candidates": self.candidates()}

    def view(self):
        return {
            "colors": [[self.colors[(r, p)] for p in range(r + 1)] for r in range(ROWS)],
            "q": list(self.q), "enemies": [{"id": e["id"], "type": e["type"], "pos": list(e["pos"])} for e in self.enemies],
            "discs": [list(d) for d in sorted(self.discs)], "lives": self.lives, "score": self.score,
            "level": self.level, "round": self.round, "steps": self.steps, "max_steps": self.max_steps,
            "frozen": self.frozen, "remaining": self.remaining_cubes(), "rule": RULE_TEXT[min(self.level, 5)],
            "terminated": self.terminated, "success": self.success, "outcome": self.outcome,
            "rounds_cleared": self.rounds_cleared, "ruleset": self.ruleset,
            "spoiled": [list(c) for c in sorted(self.spoiled)],
        }


def events_has(events, name):
    return any(e["event"] == name for e in events)


# ------------------------------------------------------------------ robô de código
def bot_scores(env):
    """Notas de um jogador simples feito em código (para comparar com o modelo)."""
    scores = {}
    deadly = [e for e in env.enemies if e["type"] in DEADLY]
    coily_near = any(e["type"] == "coily" and distance(e["pos"], env.q) <= 2 for e in env.enemies)
    todo = [c for c in CELLS if env.colors[c] != 2]
    for action in ACTIONS:
        d = dest(env.q, action)
        if action != "wait" and not on_pyramid(d):
            scores[action] = (40.0 if coily_near else -5.0) if d in env.discs else -100.0
            continue
        s = 0.0
        if any(e["pos"] == d for e in deadly):
            s -= 90
        if env.frozen <= 1:
            for e in deadly:
                if d in env.enemy_options(e) or (e["type"] == "coily" and distance(e["pos"], d) <= 1):
                    s -= 60
                    break
        if any(e["pos"] == d and e["type"] in FRIENDLY for e in env.enemies):
            s += 15
        if action == "wait":
            s -= 3
        else:
            old = env.colors[d]
            new = env.rule()[old]
            s += 10 if new == 2 and old != 2 else 6 if new > old else -12 if new < old else 0
        if todo:
            s -= 1.5 * min(distance(d, c) for c in todo if True) if on_pyramid(d) else 0
        scores[action] = s
    return scores
