#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Iniciando Seiden Vision 0.2.0..."
bashio::log.info "Arquitetura: $(uname -m)"
bashio::log.info "Servidor web: Gunicorn (1 worker, 4 threads)"

cd /app

exec gunicorn \
  --bind 0.0.0.0:8099 \
  --workers 1 \
  --threads 4 \
  --timeout 60 \
  --graceful-timeout 20 \
  --access-logfile - \
  --error-logfile - \
  --log-level info \
  main:app
