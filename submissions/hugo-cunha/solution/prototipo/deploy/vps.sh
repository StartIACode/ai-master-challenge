#!/usr/bin/env bash
# Deploy idempotente do protótipo na VPS (Ubuntu + Apache já configurado).
# Uso (no Mac, a partir da pasta do protótipo, com o modelo já treinado):
#   ./deploy/vps.sh root@187.77.249.237
# Requer: models/index.pkl treinado localmente (a VPS tem 4 GB de RAM e não treina).
set -euo pipefail
HOST="${1:?uso: deploy/vps.sh user@host}"
DOMAIN="g4-triagem.187-77-249-237.sslip.io"
APP=/opt/g4-triagem
HERE="$(cd "$(dirname "$0")/.." && pwd)"
test -f "$HERE/models/index.pkl" || { echo "treine antes: make train"; exit 1; }

echo "== 1/6 sincronizando código e artefatos"
ssh "$HOST" "mkdir -p $APP"
rsync -az --delete \
  --exclude '.venv' --exclude 'data/*.csv' --exclude '__pycache__' --exclude '*.db*' --exclude '.pytest_cache' \
  "$HERE/" "$HOST:$APP/"
rsync -az "$HERE/models/index.pkl" "$HOST:$APP/models/index.pkl"

echo "== 2/6 ambiente Python na VPS (uv)"
ssh "$HOST" bash -s <<'REMOTE'
set -euo pipefail
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
cd /opt/g4-triagem
uv python install 3.13 >/dev/null 2>&1 || true
uv sync --no-dev
cd data && (test -f all_tickets_processed_improved_v3.csv || unzip -o -q ds2.zip) && (test -f customer_support_tickets.csv || unzip -o -q ds1.zip)
chown -R www-data:www-data /opt/g4-triagem
REMOTE

echo "== 3/6 serviço systemd"
ssh "$HOST" "cp $APP/deploy/g4-triagem.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now g4-triagem && sleep 3 && systemctl restart g4-triagem && sleep 3 && curl -fsS http://127.0.0.1:8010/api/health"

echo "== 4/6 vhost + certificado"
ssh "$HOST" bash -s <<REMOTE
set -euo pipefail
a2enmod proxy proxy_http ssl rewrite >/dev/null
cp $APP/deploy/zz-g4-triagem.conf /etc/apache2/sites-available/
# primeiro só :80 (sem SSL) para emitir o certificado
sed '/<IfModule mod_ssl.c>/,/<\/IfModule>/d' $APP/deploy/zz-g4-triagem.conf > /etc/apache2/sites-available/zz-g4-triagem.conf
a2ensite zz-g4-triagem >/dev/null && apache2ctl configtest && systemctl reload apache2
test -d /etc/letsencrypt/live/$DOMAIN || certbot certonly --webroot -w /var/www/html -d $DOMAIN --non-interactive --agree-tos --register-unsafely-without-email
cp $APP/deploy/zz-g4-triagem.conf /etc/apache2/sites-available/zz-g4-triagem.conf
apache2ctl configtest && systemctl reload apache2
REMOTE

echo "== 5/6 conferindo que o vhost default não mudou"
ssh "$HOST" "apache2ctl -S 2>/dev/null | grep -E 'port 443 namevhost' | head -2"

echo "== 6/6 smoke test público"
curl -fsS -I "https://$DOMAIN/api/health" | head -1
curl -fsS "https://$DOMAIN/api/health"; echo
echo "OK: https://$DOMAIN"
