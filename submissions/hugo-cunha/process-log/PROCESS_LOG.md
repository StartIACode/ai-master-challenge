# Process log — como a IA foi usada (e onde errou)

Candidato: Hugo Cunha · Ferramenta: Claude Code (modelo Claude Fable 5.1) no desktop, sessão única iniciada em 16/09/2026 às 17:08 (BRT). Prompts literais em [`prompts.md`](prompts.md); PDF em [`evidencias.pdf`](evidencias.pdf); histórico git no branch `submission/hugo-cunha`.

## 1. Regra do trabalho

Tudo foi feito com IA, inclusive este texto. O meu papel foi decidir: o que pedir, quando desconfiar, o que cortar e o que só quem opera sabe. Cada decisão minha está marcada como **[Hugo]** abaixo; cada erro da IA que precisou de correção está em §4.

## 2. Linha do tempo (horas reais)

| Hora (BRT) | Etapa | Prompt | O que aconteceu |
|---|---|---|---|
| 17:08–17:30 | Entender o desafio e os dados | P01 | Clone do repositório, leitura integral do brief, download dos dois datasets direto do Kaggle com SHA-256, profilagem por código. Achado: Dataset 1 tem 8.469 linhas (não ~30 mil) e é sintético. |
| 17:30–18:10 | Avaliar o desafio por várias cabeças | (IA) | Painel multiagente: 5 lentes (avaliador do G4, gerente de operações, arquiteto, cientista cético, comunicação) + 3 críticos hostis + síntese. |
| 17:35 | Minha proposta de solução | P02 | **[Hugo]** Robô N1-IA que cruza com o histórico e responde se similaridade ≥ 90%; N2/N3 humanos; painel com % IA vs humano e TMA por nível; protótipo na minha VPS; API × modelo próprio com custo. |
| 17:50–18:10 | Cruzar minha proposta com os fatos | (IA) | Segundo painel (4 lentes + 2 críticos): manteve N1/N2/N3, filas, VPS e API; corrigiu similaridade, "dados fake", TMA e stack. Preços de API lidos na hora. |
| 18:10–18:40 | Avaliação entregue + decisões | P03 | **[Hugo]** Conta GitHub, stack Python, VPS por último, LLM desligado, tom sobre o Dataset 1. **[Hugo]** Nova ideia: template de fechamento obrigatório + retro-padronização da base como passo anterior à similaridade. |
| 18:45–19:20 | Especificação, plano, fork, esqueleto | (IA) | Spec e plano com contratos de API fixos; fork; primeiro commit (com um tropeço no `.gitignore`, §4). |
| 19:20–19:45 | Construção, onda 1 | (IA) | Agentes em paralelo: normalização + política + rascunhos (34 testes), diagnóstico do Dataset 1, treino do modelo (86,5% no hold-out, artefatos e figuras). |
| 19:45–20:10 | Construção, onda 2 | (IA) | Backend (modelo em runtime, replay, board SQLite, template de fechamento, API; 104 testes) + revisor independente; documentos de diagnóstico e proposta escritos a partir dos JSONs. |
| 20:10–21:05 | Construção, onda 3 | (IA) | Página única (7 abas), verificação no navegador com 16 screenshots, revisor achou 1 problema alto (reset do formulário), corrigido e reaprovado; correções leves do revisor do backend aplicadas. |
| 21:00 | Pedido de status | P04 | **[Hugo]** Cobrou status; recebeu o quadro do que estava feito, em andamento e pendente. |
| 21:05–21:40 | Prova de setup, deploy, documentação | (IA) | Clone limpo do fork cronometrado (2 min 00 s até 105 testes verdes); deploy na VPS falhou na primeira tentativa (Python do uv dentro de `/root`, inacessível ao `www-data`), script corrigido e reexecutado; README no template; este log; PDF de evidências. |
| 22:10 | Revisão do Hugo sobre o protótipo publicado | P05 | **[Hugo]** Com um print do Painel: tirar 3 abas técnicas e 4 cards, trabalhar em português (modelo treinado em pt-BR), medir o TMA por nível pelo tempo do card em cada coluna, renomear contadores confusos, arrumar os botões do fechamento. |
| 22:15–23:10 | Segunda rodada de construção | (IA) | Tradução offline do Dataset 2 para pt-BR (tradutor Argos/CTranslate2; 1ª tentativa a 3 tickets/s, reescrita para lotes a 33 tickets/s) e retreino; backend com TMA por nível (relógio por coluna, 8 testes novos); interface com 4 abas, painel do gestor, rótulos pt-BR; revisor independente; redeploy. |
| 00:30 (17/09) | PR | P07 | **[Hugo]** "pode abrir o pr". PR aberto: https://github.com/Gestao-Quatro-Ponto-Zero/ai-master-challenge/pull/134 (só `submissions/hugo-cunha/`). |

## 3. Como decompus o problema antes de promptar

1. **Auditar antes de analisar.** Baixar os arquivos reais e medir (linhas, hashes, distribuições, testes de associação) antes de qualquer proposta. Foi isso que mudou tudo: o brief pedia gargalos "com dados" e o Dataset 1 não sustenta nenhum.
2. **Lentes, não um prompt.** Em vez de pedir "resolva o desafio", pedi que o desafio fosse avaliado por papéis distintos e depois atacado por críticos. A síntese virou a avaliação que eu li e decidi.
3. **Minha proposta como hipótese.** A visão N1-IA → N2 → N3 é minha; a IA testou cada parte contra os dados e devolveu o que sobrevive e o que muda.
4. **Contratos antes de código.** Especificação e plano com contratos de API fixos, para que agentes construíssem partes em paralelo e um revisor independente checasse cada etapa.
5. **Um só lugar para os números.** Todo número dos documentos vem de `metrics.json` e `ds1_metrics.json`, gerados por `make train`.

## 4. Onde a IA errou e como corrigi (com o par prompt → saída)

| # | O que a IA fez | Como foi pego | Correção |
|---|---|---|---|
| 1 | Aceitaria o brief ("~30.000 registros com texto real") sem conferir. | Profilagem por código logo no P01. | 8.469 linhas, placeholder em 100% das descrições, tempos numa janela de 27 h: o Dataset 1 virou controle negativo, não fonte de gargalos. |
| 2 | Minha proposta P02 dizia "responde com a tratativa anterior se similaridade ≥ 90%". A IA poderia ter simplesmente construído isso. | Painel 2 mediu: cosseno ≥ 0,90 cobre 5,1% dos tickets e o vizinho acerta 70,2% contra 86,5% do classificador; não há campo de resolução em nenhum dataset. | A decisão passou a ser a confiança do classificador; a similaridade virou evidência ao N2. **[Hugo]** Respondi com o template de fechamento obrigatório, que cria a base que faltava. |
| 3 | O primeiro `git add -f` (necessário porque o `.gitignore` do G4 ignora `submissions/`) arrastou o `.venv/` com 8.841 arquivos e os CSVs. | Contagem de arquivos rastreados no commit. | `git rm --cached`, script `tools/git-add-safe.sh` com exclusões explícitas, commit corrigido (15 arquivos). |
| 4 | O plano de implementação trazia uma lista de stopwords com "hello" e, ao mesmo tempo, um teste que exigia "hello" no resultado. | O agente da tarefa rodou o teste e ele falhou. | O agente tratou o teste como contrato e documentou a inconsistência do plano. |
| 5 | Primeira versão da busca de similares usava blocos de 2.000 linhas e chegou a 3,3 GB de pico de RAM num Mac de 8 GB. | Medição de RSS durante o treino. | Blocos de 125 linhas; pico 1,3 GB; documentado no script. |
| 6 | Figura do Dataset 1 saiu com anotações sobrepostas e ponto decimal em vez de vírgula. | O agente abriu o PNG antes de entregar. | Eixo com folga, subtítulo separado, formatação pt-BR. |
| 7 | Os 3 exemplos fixos da demo (seed 7) caíam em um Administrative rights com p = 0,54 e dois Miscellaneous: nenhum caso de auto-roteio para mostrar. | Revisor independente do backend. | Seleção determinística de um trio representativo (auto-roteio, sugerir, baixa confiança). |
| 8 | Motivos exibidos ao analista com ponto decimal e "1.00" por arredondamento. | Revisor independente. | Vírgula decimal e "0,99+" acima de 0,995; teste atualizado. |
| 9 | Os documentos citaram 65,3% e 90,8% onde o exato era 65,2% e 90,7%. | Verificador de formatação do próprio agente de documentos. | Corrigido para os valores exatos dos JSONs. |
| 10 | O botão "Preencher exemplo válido" e o fluxo "Resolver → Registrar fechamento" chamavam `form.reset()` e depois preenchiam os campos; o listener de reset limpava o que tinha acabado de ser preenchido (subcategorias dependentes vazias). | Revisor independente da interface reproduziu no navegador. | Reset programático sem disparar o listener; screenshot refeito; segunda revisão aprovada. |
| 11 | Na verificação da interface, o agente navegou para outra aba por `#fragmento` achando que era recarga de página: o CSS editado não foi recarregado e ele quase deu por corrigido um erro que continuava. | O console ainda mostrava o 404 antigo. | Recarga completa forçada e nova verificação em sessão limpa. |
| 12 | A tabela de política em 375 px saiu com linhas de até 161 px de altura porque uma regra de largura mínima espremia a coluna Motivo. | Screenshot em mobile. | Regra removida, largura mínima só na última coluna, screenshot refeito. |
| 13 | A política dizia que Storage tinha "a melhor precisão entre as classes"; o JSON mostra Purchase acima (0,96 contra 0,94). | Agente dos documentos cruzou o texto com `per_class`. | Motivo corrigido para "entre as classes auto-roteáveis"; `policy.json` e a proposta regenerados. |
| 14 | O deploy na VPS instalou o Python gerenciado pelo `uv` em `/root/.local`, e o serviço roda como `www-data`: `Permission denied` em loop de reinício. O script seguiu como se tivesse dado certo porque a verificação era um `sleep 3` e um `curl`. | `systemctl status` e `journalctl` na VPS. | Python instalado em `/opt/uv-python`, venv recriado, espera ativa de até 90 s pelo `/api/health`; deploy refeito. |
| 15 | O tradutor offline verteu "windows update" para "atualização das janelas" no primeiro teste. | Leitura da amostra antes de rodar os 47 mil. | Lista de termos de produto protegidos (Windows, Outlook, VPN, PO…) preservada na tradução. |
| 16 | A primeira rodada de tradução usou o pipeline completo do Argos (segmentação por stanza) e rendia 3 tickets/s: mais de 4 horas. | Medição de ritmo no primeiro minuto. | Script reescrito para chamar o motor CTranslate2 direto, em lotes de 64 e pedaços de 20 palavras: 33 tickets/s, ~25 min. |
| 17 | Na verificação da nova interface, o agente "recarregou" a página mudando só o fragmento da URL e validou plural errado nos contadores com o JavaScript antigo. | O texto dos KPIs não mudava. | Recarga com query string e verificação refeita; helper de plural. |
| 18 | Com a API fora do ar, o Painel continuava tentando atualizar a cada 5 s e repetia o aviso. | Revisor independente reproduziu com fetch rejeitado. | O relógio de atualização para quando a API falha e volta ao trocar de aba ou clicar em Atualizar. |
| 19 | O script de tradução gravou o CSV, mas falhou ao gravar os metadados por chamar um atributo de versão que a biblioteca não tem. | Saída do treino encadeado. | Metadados gravados à mão com a mesma informação; script corrigido para ler a versão pelo `importlib.metadata`. |

## 5. O que eu adicionei que a IA sozinha não faria **[Hugo]**

- **A arquitetura em três níveis com a IA na frente e humanos atrás** (N1-IA → N2 → N3), com o N2 definido por "resolve sem olhar código nem acionar outras áreas" e o N3 por "envolve outras áreas". A IA transformou isso em gate e política por classe, mas o desenho operacional é meu.
- **O template de fechamento obrigatório e a retro-padronização da base.** Quando os dados mostraram que não existe "como foi resolvido", a resposta não foi desistir da similaridade, foi criar o processo que gera a base: fechar o ticket na ferramenta atual só com os campos padronizados, e reclassificar o histórico com IA para alimentar a base.
- **Recomendar API em vez de modelo próprio** e pedir a conta: dezenas de dólares por mês contra R$ 13 a 17 mil por ano de GPU própria.
- **As decisões de escopo**: um só runtime Python (em vez de PHP + React), LLM desligado na demo, VPS como último passo, tom de um parágrafo sobre o Dataset 1 em vez de manchete.
- **A postura de time**: arquiteto de software e gerente de operações na mesma mesa. O arquiteto exigiu contratos, testes e reprodutibilidade; o gerente exigiu que a IA nunca responda ao cliente nem feche ticket, e que o painel mostre erros na tela.
- **A revisão de produto sobre o protótipo publicado (P05):** tirar o que era técnico demais para um Diretor (ponto de operação, política por classe, similaridade, cards de modelo e controle negativo), exigir português de ponta a ponta, e definir o TMA como o tempo que o card fica em cada coluna do board, medido, em vez de "não mensurável". A IA tinha entregado um painel para avaliador; o gestor pediu um painel para operação.

## 6. Iterações

- Prompts meus: P01 a P05 (avaliar, propor, decidir, cobrar status e revisar o produto) e 4 workflows multiagente: avaliação (9 agentes), reconciliação da minha proposta (7 agentes) e construção com revisores (10 agentes, 2 rodadas de revisão na interface) e segunda rodada após a revisão do Hugo (3 agentes).
- Commits no branch, um por etapa fechada e testada (34 → 104 → 105 testes); histórico completo em `git log`.
- Revisão independente do backend (aprovada, 5 observações leves aplicadas) e da interface (1 problema alto corrigido, segunda revisão aprovada com 4 observações leves aplicadas).
