# Diagnóstico — o que os dados permitem medir

Hugo Cunha · Challenge 002 · 2026-09-16 · Números: `prototipo/artifacts/ds1_metrics.json` e `prototipo/artifacts/metrics.json` (gerados por `make train`; a chave de origem vai entre parênteses).

## 1. O que os dois arquivos permitem medir

O brief pede "onde o suporte perde tempo". Auditei os datasets antes de propor, como faço com qualquer planilha que chega na minha mesa (já vi um DRE fabricar despesa copiando o mês anterior). O **Dataset 1** (8.469 tickets de suporte ao cliente, 17 colunas) tem o formato que o brief descreve, mas seus campos de tempo e satisfação não carregam sinal: a tabela pedida está abaixo, com o veredito. O **Dataset 2** (47.837 tickets reais de TI, 8 categorias) não tem tempos nem resolução, mas tem texto real e rótulo humano: nele se mede o que este trabalho automatiza, a **triagem**.

## 2. Dataset 1: a tabela que o brief pede, e o veredito

Por canal, prioridade e tipo (`naive_table`). CSAT = média de `Customer Satisfaction Rating`, só nos 2.769 fechados; Δ horas = média de `Time to Resolution − First Response Time` nesses tickets.

| Dimensão | Valor | n | n fechados | CSAT médio | Δ horas |
|---|---|---:|---:|---:|---:|
| Canal | Chat | 2.073 | 674 | 3,08 | +0,20 |
| Canal | Email | 2.143 | 720 | 2,96 | +0,01 |
| Canal | Phone | 2.132 | 691 | 2,95 | −0,56 |
| Canal | Social media | 2.121 | 684 | 2,97 | +0,12 |
| Prioridade | Critical | 2.129 | 726 | 2,96 | −0,20 |
| Prioridade | High | 2.085 | 705 | 2,98 | −0,07 |
| Prioridade | Low | 2.063 | 644 | 3,05 | +0,39 |
| Prioridade | Medium | 2.192 | 694 | 2,98 | −0,31 |
| Tipo | Billing inquiry | 1.634 | 544 | 3,03 | −0,21 |
| Tipo | Cancellation request | 1.695 | 516 | 3,03 | −0,17 |
| Tipo | Product inquiry | 1.641 | 533 | 3,02 | −0,24 |
| Tipo | Refund request | 1.752 | 596 | 2,93 | +0,22 |
| Tipo | Technical issue | 1.747 | 580 | 2,96 | +0,07 |

**Veredito** (`verdict`): "As diferenças entre canais, prioridades e tipos cabem no ruído; tempo de resolução não é mensurável neste arquivo." CSAT entre 2,93 e 3,08, Δ entre −0,56 h e +0,39 h. Três evidências:

1. **Tempo.** Os dois campos são carimbos de hora, não durações; os 2.769 pares caem numa janela de 27,0 h. Em 49,3% dos fechados (1.365) a "resolução" precede a primeira resposta; Δ médio −0,06 h, desvio 9,56 h, de −23,2 h a +23,5 h (figura `prototipo/artifacts/figures/ds1_time_window.png`).
2. **Texto.** 100% das descrições contêm o marcador literal `{product_purchased}`; só 16 primeiras frases distintas (5.868 são "I'm having an issue with the {product_purchased}"); 2.769 resoluções, todas únicas, 5,5 palavras em média; 34,3% dos e-mails `@example.com`.
3. **Satisfação.** Média 2,99, desvio 1,41: um sorteio uniforme de 1 a 5 (3,00 e 1,41). Em 14 testes de associação (`association_tests`: canal, prioridade, tipo, gênero, 42 produtos, 16 assuntos, idade, hora da primeira resposta) todos dão p > 0,14, exceto a hora (ρ = −0,04, p = 0,034): 1 em 14 é o acaso.

**Controle negativo** (`negative_control`): o pipeline que classifica o Dataset 2, prevendo `Ticket Type` a partir de `Ticket Description` (5-fold, seed 42), acerta 19,7% ± 0,6 (folds entre 19,1% e 20,6%), abaixo da classe majoritária (Refund request, 20,7%): não há texto para aprender. No Dataset 2 o mesmo pipeline dá 86,2% (± 0,35 p.p.; `cv5`). O Dataset 1 ainda dá Refund, Cancellation e Billing como exemplos do que **não** automatizar.

## 3. Dataset 2: onde a triagem acerta, onde erra e quanto o erro custa

**Mix** (`class_counts`; 391 quase-duplicatas removidas; 37.956 tickets de treino, 9.490 de hold-out): Hardware 13.574 · HR Support 10.800 · Access 7.102 · Miscellaneous 7.025 · Storage 2.773 · Purchase 2.308 · Internal Project 2.105 · Administrative rights 1.759. **Modelo**: TF-IDF (144.526 termos) + regressão logística; acurácia 86,5%, macro-F1 0,866, ECE 0,032 (`prototipo/artifacts/figures/reliability.png`); treino em 74 s, 1,4 GB de pico.

**Onde erra** (`per_class`, `confusion`; `prototipo/artifacts/figures/confusion.png`): Hardware absorve as confusões (precisão 0,82, recall 0,90; 552 falsos em 3.007 (18,4%) previstos). Administrative rights é a classe que o modelo menos reconhece (recall 0,68, precisão 0,91): 88 de 352 (25,0%) viram Hardware, e é elevação de privilégio. HR Support → Hardware: 140 de 2.160 (6,5%); Miscellaneous → Hardware: 138 de 1.405 (9,8%). Purchase (precisão 0,96), Storage (0,94), Internal Project (0,93) e Access (0,93) são as classes mais limpas.

**Quanto custa o erro** (`thresholds`; `prototipo/artifacts/figures/coverage_accuracy.png`): com limiar 0,90 o modelo cobre 53,9% dos tickets com 98,3% de acerto (85 erros em 5.116); aplicada a política (só Access, Storage e Hardware auto-roteiam, nenhum ticket com sinal de risco), a **cobertura útil é 26,5% com 98,2% de acerto: 45 erros em 2.511 tickets**, cada um devolvido pelo botão "IA errou" ao custo de uma re-triagem. O outro lado pesa mais: os 33,8% do hold-out com confiança abaixo de 0,80 (3.211 tickets) acertam só 66,6% e vão sempre a uma pessoa. Miscellaneous com p ≥ 0,90 seria 6,7% do hold-out "roteado com confiança para lugar nenhum"; nunca conta como roteado.

**Similaridade** (`similarity`; `prototipo/artifacts/figures/similarity_curve.png`): o vizinho mais parecido do treino tem a mesma classe em 70,2% dos casos, contra 86,5% do classificador; ≥ 0,90 cobre 5,1% do hold-out (487 tickets, 94,3% de concordância), ≥ 0,99 cobre 0,1% (13 tickets: templates e alertas). "Responder com a tratativa do ticket 90% parecido" alcançaria 1 ticket em 20.

## 4. O que exportar do helpdesk para medir em duas semanas

Log de auditoria que o helpdesk já grava, mais uma amostra cronometrada: (1) **eventos de status com carimbo de hora** (aberto, primeira resposta, aguardando cliente, resolvido, fechado, reaberto); (2) **fila e cada reatribuição**: o re-roteamento humano atual é o baseline do gate; (3) **categoria inicial e final**, mais 200 tickets rotulados por 2 triadores com o kappa registrado; (4) **nível que resolveu** (N1/N2/N3); (5) **tempo de trabalho ativo**, cronometrado por 5 agentes por 2 semanas (carimbos medem espera, não esforço); (6) **fechamento padronizado** (categoria, causa raiz, ação, reutilizável?, reaberto?, CSAT por nível). Sem isso, "tempo perdido" é premissa, e está rotulado assim na proposta.
