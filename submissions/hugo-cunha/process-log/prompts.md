# Registro de prompts — Hugo Cunha × Claude Code (Fable 5.1)

**Desafio:** G4 AI Master Challenge — 002 Redesign de Suporte  
**Formato:** cada entrada = data/hora, prompt literal do Hugo, resumo do que a IA fez em resposta.

---

## P01 — 2026-09-16 17:08 (BRT)

**Prompt do Hugo (literal):**

> Estou participando de um processo seletivo onde a vaga é para IA Master, uma empresa chamada G4. É, temos um desafio que vou precisar da sua ajuda e este desafio precisa ser concluído 100% com IA. Para este desafio, eu tenho que evidenciar todos os comandos que estou dando para IA. Então, no final do desafio, monta um documento em PDF com as evidências dos meus prompts que pedi para você. Nós precisamos de um diferencial, precisamos pensar com a cabeça de um arquiteto de software junto com um gerente de operações. Nós somos um time. Vou te enviar o GitHub para você avaliar o desafio que eu escolhi e, na sequência, vamos iniciar a solução.
>
> https://github.com/Gestao-Quatro-Ponto-Zero/ai-master-challenge
>
> Eu escolhi o desafio 002

**O que a IA fez:**
- Clonou o repositório em `~/Desktop/G4/ai-master-challenge` e leu por inteiro: README raiz, índice de challenges, README do 002, submission-guide, template de submissão e CONTRIBUTING.
- Abriu este registro de evidências (`~/Desktop/G4/evidencias/prompts.md`) a partir do primeiro prompt.
- Verificou o ambiente local (Python, Kaggle CLI, gh) antes de propor o plano.

**Achados desta etapa (verificados por código, não por leitura):**
- Kaggle liberou download anônimo; os dois datasets oficiais foram baixados e conferidos por SHA-256.
- Dataset 1 tem 8.469 tickets (o brief diz ~30 mil) e é sintético: placeholder `{product_purchased}` em 100% das descrições, resoluções aleatórias, tempos são timestamps numa janela de 27 h (49% "resolvidos" antes da 1ª resposta), satisfação uniforme e sem associação com nenhuma variável (p>0,14). Detalhes em `notas/fatos-datasets.md`.
- Dataset 2 é real (47.837 tickets, 8 classes). Classificador-base TF-IDF+SVM: 86,7% (5-fold). Com gate de confiança ≥0,90: 54% dos tickets roteados com 98,2% de acerto.
- Ferramentas: Claude Code (Fable 5.1) com painel de 5 lentes + 3 críticos adversariais + síntese (workflow multiagente) para avaliar o desafio antes de propor o plano.

---

## P02 — 2026-09-16 ~17:35 (BRT) — proposta de solução do Hugo (transcrição de voz, literal)

**Prompt do Hugo (literal):**

> A minha proposta é criar um sistema de monitoramento de ticket que vai classificar o ticket e identificar se Já ocorreu um problema parecido na nossa, base de dados, ou seja, olhar o passado. e ver como foi resolvido. Basicamente, é um robô de monitoramento, onde ele identifica o ticket aberto, cruza os dados com a nossa base, verifica se já houve tratativa para aquele problema e como foi tratado. E já responde de imediato com aquela tratativa. Se tiver um nível de similaridade acima de 90%. Caso não tenha, O robô vai delegar o ticket para o N2, que é onde entra o atendimento humano. Este atendimento humano é o time técnico que analisa o ticket com os dados já pré-filtrados pela IA. Para isso, nós vamos criar um painel de monitoramento, onde nós vamos medir qual o percentual de tickets atendido pela IA, qual o percentual de tickets delegado para o suporte humano. E nós vamos também classificar o TMA, que é o tempo médio de atendimento de cada nível, de trabalho. Por exemplo, a IA vai fazer o N1, e o time de atendimento humano vai fazer o N2. Neste N2, nós teremos analistas que conseguem identificar o problema sem olhar código, sem acionar outras áreas e responder de bate-pronto, de forma rápida. Caso esse analista não consiga resolver o problema sozinho, sem falar com outras áreas, ele direciona para o time de N3. Que é um analista especialista em chamados envolver outras áreas, envolver tecnicamente aquele problema. Então, é, temos que medir essas três filas de atendimento. E a minha sugestão é usar uma ferramenta Kanban, pode ser o Jira, ou o Trello, ou podemos até mesmo criar uma, que seja institucional. Onde a gente acompanha essas filas e o responsável por cada chamado em tempo real. Então, vamos montar um, protótipo navegável com a identidade da empresa G4, com essas filas de monitoramento que vai gerar também indicadores de medições em tempo real. dos tickets. Você pode montar esse protótipo e subir na minha VPS da Hostinger, só para eu conseguir enviar para eles a acessarem via internet e olharem esse protótipo. Pode ser em PHP, com front-end em React, cem por cento responsivo. É... Não precisa botar autenticação, porque vai ser apenas um protótipo com dados fakes. para a gente navegar e identificar os problemas. Mas basicamente a proposta é ter esse, essa IA que vai fazer essa esse cruzamento de dados e identificar se o problema já foi resolvido anteriormente. E a Arquiteturalmente, nós temos duas saídas. Usar via API com créditos ou fazer um treinamento de uma IA e instalar ela num servidor próprio da empresa carregar a base de dados para a IA utilizar RAG e responder os chamados. [...trecho repetido na transcrição...] Neste caso, mas neste caso eu indico usar por API e também faz uma estimativa de custo dessa utilização.

**O que a IA fez:** cruzou a proposta com os fatos medidos dos datasets e com os critérios do G4 (protótipo "com dados reais, não cherry-picked"; "automatizar 100% é red flag"); rodou um painel adversarial sobre a proposta antes de responder.

**Resultado desta etapa (painéis multiagente, 16 agentes, ~1,65 M tokens):**
- Painel 1 (5 lentes + 3 críticos + síntese) avaliou o desafio: ele testa julgamento, não modelagem; a armadilha central é o Dataset 1 sintético; o baseline de IA provavelmente reporta "tempo médio de resolução" e "gargalos" que são ruído. Opção recomendada: triagem com gate por precisão-alvo + auditoria enxuta do Dataset 1 + protótipo rodando sobre TODO o hold-out.
- Painel 2 (4 lentes + 2 críticos + síntese) cruzou a proposta do Hugo com os fatos: manteve N1-IA → N2 → N3, filas medidas, VPS e recomendação de API; corrigiu (a) "responde com a tratativa anterior se similaridade ≥ 90%" — não existe resolução real nos datasets e cosseno ≥ 0,90 cobre só ~6% dos tickets (1-NN acerta 70,7% vs 86,7% do classificador); (b) "dados fake" — cards devem ser tickets reais do hold-out; (c) TMA por nível — imensurável nos datasets, entra rotulado como simulação; (d) PHP + React — o modelo é Python; recomendação de um só runtime. Estimativa de custo de API com preços lidos em 16/09/2026.
- Riscos práticos confirmados por código: `.gitignore` do repo do G4 ignora `submissions/` (PR sairia vazio sem `git add -f`); `gh` está logado na conta StartIACode, não na pessoal do Hugo.
- Síntese entregue ao Hugo com as decisões que só ele pode tomar. Nenhuma implementação iniciada antes da aprovação (roteiro de brainstorming: gate de aprovação).

---

## P03 — 2026-09-16 ~18:40 (BRT) — decisões do Hugo + nova proposta (template de fechamento)

**Prompt do Hugo (literal):**

> Sobre a similaridade, não temos dados reais nem a base de dados deles, entendo que no desafio eles colocaram dados descaracterizados. Então vamos usar sim, mas cria uma tela de exemplo de como ficaria após padronização. E aí que entra minha nova proposta que fica um passo antes: criar um template de fechamento de ticket. Quando o ticket é fechado hoje manualmente pelo time, temos que obrigar a preencher os dados no padrão para alimentarmos a base para o RAG da IA. Ou seja, pegar a base atual de produção e reclassificar o fechamento, pois aí sim teremos similaridade acima de 90%
>
> Então cria um formulário de exemplo,só pra ilustrar mesmo. Porque na verdade eles vão fechar na ferramenta atual que eles usam (não sei qual)
>
> 1 pode usar minha conta da StartIA
> 2 ok
> 3 ok
> 4 seja mais claro
> 5 ok desligado
> 6 ok

**Decisões tomadas pelo Hugo:** conta GitHub StartIACode para fork/PR; stack Python FastAPI + página única; deploy na VPS como último passo; LLM desligado na demo; tom sobre o Dataset 1 em um parágrafo com tabela.
**Pedido de esclarecimento:** o que significa o limiar padrão do gate (item 4).
**Adição do Hugo (julgamento humano que a IA não trouxe sozinha):** o template de fechamento obrigatório como passo anterior à similaridade: padronizar o fechamento na ferramenta atual e retro-padronizar a base de produção para alimentar a base de conhecimento (RAG). A similaridade continua no desenho, com uma tela de exemplo "como ficaria após a padronização", rotulada como ilustrativa.

**O que a IA fez:** explicou o limiar; escreveu a especificação do desenho aprovado; preparou fork/branch; iniciou a construção.

**Execução após o P03 (registro do que a IA fez, com os tropeços):**
- Escreveu a especificação aprovada em `submissions/hugo-cunha/docs/2026-09-16-desenho-solucao.md` (inclui a explicação do limiar pedida no item 4) e o plano em `docs/2026-09-16-plano-implementacao.md` (13 tarefas com contratos de API fixos).
- Fork criado em `StartIACode/ai-master-challenge`; branch `submission/hugo-cunha`; identidade git local "Hugo Cunha <startia.develop@gmail.com>".
- Erro da IA, corrigido: o primeiro `git add -f` (necessário porque o `.gitignore` do G4 ignora `submissions/`) arrastou o `.venv/` com 8.841 arquivos e os CSVs extraídos. Correção: `git rm --cached`, script `tools/git-add-safe.sh` com exclusões explícitas e commit corrigido (15 arquivos rastreados).
- Workflow multiagente de construção iniciado (agentes por tarefa + revisores com correção), sem commits pelos agentes.

---

## P04 — 2026-09-16 ~21:00 (BRT)

**Prompt do Hugo (literal):**

> me passa um status da construcao

**O que a IA fez:** respondeu com o status por etapa (concluído / em andamento / pendente), pediu o LinkedIn para o template e reexplicou o limiar do gate em linguagem de gestor.

**Fechamento da construção (após o P04):**
- Interface aprovada em segunda revisão; 4 observações leves aplicadas; 105 testes verdes.
- Prova de setup em clone limpo do fork: `git clone` + `make setup` + `make train` + `make test` em 2 min 00 s.
- Deploy na VPS: primeira tentativa falhou (Python do `uv` em `/root`, inacessível ao `www-data`); script corrigido; segunda tentativa no ar em https://g4-triagem.187-77-249-237.sslip.io com Let's Encrypt e vhost padrão intacto. Replay testado no site público pelo navegador, sem erros de console.
- README no template do G4, process log, prompts literais e `evidencias.pdf` comitados e publicados no fork (branch `submission/hugo-cunha`, 71 arquivos, todos dentro de `submissions/hugo-cunha/`).
- PR **não** aberto ainda: aguarda o LinkedIn e o OK do Hugo.

---

## P05 — 2026-09-16 ~22:10 (BRT) — revisão do Hugo sobre o protótipo publicado (com print do Painel)

**Prompt do Hugo (literal):**

> Deleta as abas
>
> Similaridade apos padronizacao
> vamos trabalhar em portugues, o modelo tem que ser treinado em portugues
> ajusta o layout dos botoes da aba fechamento padronizado
> remove a aba politica por classe
> remove pontos de operacao
> e vamos falar sobre o painel
>
> Nao entendi tickets no replay
> N1 auto roteado é o que a IA escalou para N2?
> TEM que medir o TMA por fase, de acordo com o tempo que o card ficou no board
> Remove esses 4 cards: Modelo Dataset2, GATE no lmiar atual, Controle negativo e TMA

(Acompanhado de um print do Painel do protótipo público.)

**Decisões do Hugo (julgamento humano):** simplificar o protótipo para o que um gestor usa (sem abas técnicas), trabalhar em português (modelo treinado em pt-BR), medir o TMA por nível pelo tempo que o card fica em cada coluna do board, e trocar o painel técnico por indicadores operacionais.

**O que a IA fez:** traduziu o Dataset 2 para pt-BR com tradutor offline e retreinou; removeu 3 abas e 4 cards; renomeou os contadores; implementou o TMA por nível medido no board; ajustou os botões do fechamento; atualizou documentos, testes, deploy e evidências.

---

## P06 — 2026-09-16 ~23:20 (BRT)

**Prompt do Hugo (literal):**

> [www.linkedin.com/in/hugo-cunha-1138b540](https://www.linkedin.com/in/hugo-cunha-1138b540)
>
> meu linkedin

**O que a IA fez:** preencheu o LinkedIn no README da submissão (no lugar do marcador) e seguiu a rodada 2.

**Execução da rodada 2 (após P05 e P06):**
- Tradução do Dataset 2 para pt-BR com tradutor offline (Argos Translate / CTranslate2). Erros da IA corrigidos no caminho: "windows" virou "janelas" (lista de termos protegidos); primeira versão a 3 tickets/s (reescrita para lotes: 33 tickets/s, 25 min); o script falhou ao gravar os metadados por um atributo de versão inexistente (metadados gravados e script corrigido).
- Retreino em português: acurácia 84,5% (inglês: 86,5%), macro-F1 0,849, ECE 0,035; limiar 0,90 cobre 49,3% com 98,1% de acerto, cobertura útil 24,8% com 98,0%. Pisos dos testes de regressão rebaixados de 0,85/0,25 para 0,84/0,24 com o motivo registrado no código.
- Backend: TMA por nível medido pelo tempo do card em cada coluna (relógio injetável, 8 testes novos, 113 no total). Interface: 4 abas, painel do gestor, rótulos em português, seletor de limiar no board, botões do fechamento espaçados; revisor independente aprovou com um ajuste médio (polling com API fora) e leves, aplicados.
- Erro de processo da IA, corrigido: o arquivo de checkpoint da tradução (7,3 MB) entrou num commit intermediário; os dois commits da rodada foram reescritos num só, sem o arquivo, e a branch do fork foi atualizada com force-with-lease (PR ainda não aberto, sem impacto externo).
- Redeploy na VPS: OK na primeira tentativa desta rodada (https://g4-triagem.187-77-249-237.sslip.io com o modelo em português). Verificação local e pública no navegador sem erros de console.
- Documentos (README, diagnóstico, proposta, adendo na especificação) atualizados com os números novos por agente redator, com verificador automático de números contra o metrics.json.

---

## P07 — 2026-09-17 ~00:30 (BRT)

**Prompt do Hugo (literal):**

> pode abrir o pr

**O que a IA fez:** conferiu o branch (local = fork, sem pendências, nenhum PR existente), abriu o PR `[Submission] Hugo Cunha — Challenge 002` do fork `StartIACode` para `Gestao-Quatro-Ponto-Zero/ai-master-challenge`, registrou a URL no process log e regenerou o PDF de evidências (push na mesma branch atualiza o PR).

**Resultado:** PR #134 aberto em 17/09/2026 ~00:30 — https://github.com/Gestao-Quatro-Ponto-Zero/ai-master-challenge/pull/134 — 65 arquivos, todos em `submissions/hugo-cunha/`.

