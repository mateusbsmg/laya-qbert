# NanoJev x Laya: duas IAs, o mesmo Q*bert, resultados opostos.
Depois de treinar o NanoJev no Q*bert, veio a pergunta inevitável.
E se eu testasse outra IA do mesmo tipo?
Encontrei o Laya, também open source (Apache-2.0).
Mesmo PC, mesmo jogo, mesmo professor.
Só a IA mudou.
A pergunta era simples: qual das duas aprende melhor?

**Dois jeitos de decidir**
Nenhum dos dois escreve texto: recebem uma situação e opções, e dão a chance de cada uma.
O NanoJev usa o Qwen3-0.6B, com 600 milhões de parâmetros.
Ele lê cada opção num texto separado, junto com a situação inteira.
O Laya usa o ModernBERT, com 421 milhões de parâmetros.
Ele lê a situação e todas as opções num texto só, e compara tudo de uma vez.
Foi feito para triagem: escolher o setor de um e-mail ou chamado.

**Antes do treino: dois erros diferentes**
Sem treino, o NanoJev ficava parado até ser pego.
O Laya fazia pior: pulava para fora da pirâmide em toda jogada.
Investigando, entendi o motivo.
O Laya escolhe a opção que mais combina com o texto, não a que dá certo.
Se a situação diz "andar para frente faz cair no buraco", ele escolhe andar para frente.
Para triagem, isso é perfeito. Para jogar, é um desastre.

**O treino: mesmo professor, esforço bem diferente**
Os dois aprenderam com o mesmo professor e os mesmos 30 mil exemplos.
No NanoJev, cada decisão virava cerca de 4.300 tokens de texto.
Foram dois treinos e umas 15 horas de placa de vídeo.
No Laya, usei uma situação enxuta: só o que muda a cada jogada, uns 190 tokens.
O segredo não foi a placa: foi tirar do texto as regras que se repetiam em toda jogada.
Cada passo de treino caiu de 30 segundos para menos de 1.
Em 1 hora, viu 4 vezes mais exemplos que o NanoJev.

**O resultado**
Nas mesmas 20 fases de teste, inéditas para os dois:
✅ Nível 1: NanoJev completou 2. Laya completou 20, empatando com o professor.
✅ Nível 2: NanoJev completou 0. Laya completou 11, acima do robô de regras fixas.
✅ Concordância com o professor: 55% no NanoJev, 77% no Laya.
✅ Tempo por decisão: 0,3 segundo contra 0,04.

**O que fica**
Seria fácil concluir que o Laya é mais inteligente. Não é bem isso.
A maior diferença veio de como apresentei o problema: um texto curto e direto.
Com o texto enxuto, o NanoJev também deve melhorar.
Três lições.
Primeira: cada IA nasce para uma tarefa. Fora dela, precisa ser ensinada.
Segunda: o formato da entrada vale tanto quanto o modelo.
Terceira: velocidade de treino é poder. Quem testa mais, aprende mais.
O professor ainda é o teto: o próximo desafio é fugir dos inimigos nos níveis difíceis.
Você já comparou duas IAs na mesma tarefa?

Ah, e criei um modo turbo: sem as pausas feitas para olhos humanos.

#InteligenciaArtificial #MachineLearning #FineTuning #RetroGaming #Laya #NanoJev
