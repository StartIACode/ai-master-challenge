# Dados usados no protótipo

Os dois datasets são públicos no Kaggle sob licença **CC0 (domínio público)** e foram baixados em **2026-09-16** direto da API pública do Kaggle. Os ZIPs originais estão versionados aqui; `make data` extrai os CSVs e confere os hashes em `SHA256SUMS`.

| Arquivo | Fonte | Linhas | SHA-256 do CSV |
|---|---|---|---|
| `ds1.zip` → `customer_support_tickets.csv` | https://www.kaggle.com/datasets/suraj520/customer-support-ticket-dataset | 8.469 | `b06a9cde84da65db388bd964d75f88ee1eed96607cf75d0c35f09c3f11bf8bea` |
| `ds2.zip` → `all_tickets_processed_improved_v3.csv` | https://www.kaggle.com/datasets/adisongoh/it-service-ticket-classification-dataset | 47.837 | `044fdace33fa564e1e60453f2941dafc95539c99878b0d32746950394b9dd4d4` |

Observação: o brief do desafio descreve o Dataset 1 como "~30.000 registros"; o arquivo publicado tem 8.469 linhas. A contagem e os hashes acima permitem ao avaliador conferir a versão usada.

## Dado derivado: `ds2_pt.csv.gz`

Tradução automática do texto do Dataset 2 para pt-BR, feita uma única vez em 16/09/2026 com o tradutor offline Argos Translate (pacote `en_pt` 1.9, motor CTranslate2, beam 2), pelo script `scripts/traduzir_ds2.py`. Colunas: `row_id` (índice da linha no CSV original), `Document` (texto traduzido), `Topic_group` (rótulo original, inalterado). Metadados em `ds2_pt.meta.json`. Motivo: decisão de trabalhar em português (modelo treinado em pt-BR). A licença do dado derivado segue a do original (CC0). O texto-fonte já vinha pré-processado (sem pontuação, sem stopwords, sem nomes), portanto a tradução é telegráfica; termos de produto (Windows, Outlook, VPN, PO…) foram preservados.
