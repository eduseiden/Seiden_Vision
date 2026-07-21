#!/usr/bin/with-contenv bashio
set -euo pipefail

bashio::log.info "Iniciando Seiden Vision 0.1.0..."
bashio::log.info "Arquitetura: $(uname -m)"

exec python3 /app/main.py
