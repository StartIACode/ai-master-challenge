#!/usr/bin/env bash
# O .gitignore do repositório do G4 ignora `submissions/` inteiro, então `git add` precisa de -f.
# Mas -f também força o que o .gitignore do protótipo exclui (.venv, CSVs, modelos, bancos).
# Este script adiciona a submissão com -f e exclui explicitamente o que não deve ser versionado.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git add -f -- submissions/hugo-cunha \
  ':(exclude)submissions/hugo-cunha/solution/prototipo/.venv' \
  ':(exclude)submissions/hugo-cunha/solution/prototipo/models' \
  ':(exclude,glob)submissions/hugo-cunha/solution/prototipo/data/*.csv' \
  ':(exclude,glob)submissions/hugo-cunha/**/__pycache__/**' \
  ':(exclude,glob)submissions/hugo-cunha/**/*.pyc' \
  ':(exclude,glob)submissions/hugo-cunha/**/*.db' \
  ':(exclude,glob)submissions/hugo-cunha/**/*.db-wal' \
  ':(exclude,glob)submissions/hugo-cunha/**/*.db-shm' \
  ':(exclude,glob)submissions/hugo-cunha/**/.pytest_cache/**'
git ls-files submissions/hugo-cunha | wc -l | xargs echo "arquivos rastreados na submissão:"
