# Changelog

## 0.1.1

- Substituição do servidor Flask de desenvolvimento por Gunicorn.
- Um único processo Gunicorn com múltiplas threads, evitando duplicidade do watcher e da fila.
- Logs operacionais detalhados por análise.
- Publicação de sensores adicionais:
  - `sensor.seiden_vision_queue`
  - `sensor.seiden_vision_provider`
  - `sensor.seiden_vision_version`
  - `sensor.seiden_vision_uptime`
  - `sensor.seiden_vision_last_processing`
- Publicação periódica do estado operacional no Home Assistant.
- Melhorias no encerramento do serviço.
- Mantida compatibilidade com AMD64 e AArch64.

## 0.1.0

- Fundação inicial do Seiden Vision.
- Add-on HAOS para AMD64 e AArch64.
- Interface por Ingress.
- Configuração pela interface do add-on.
- API REST para envio de imagens.
- Download HTTP de imagens.
- Fila de processamento.
- Deduplicação por SHA-256.
- Persistência SQLite.
- Mock Vision Provider.
- Publicação de sensores no Home Assistant.
- Observação opcional de entidade do Home Assistant.
