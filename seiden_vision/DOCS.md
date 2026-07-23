# Seiden Vision 0.4.0

## Papel arquitetural

O Seiden Vision é a camada de percepção da plataforma Seiden. Ele analisa imagens, registra telemetria técnica e publica eventos normalizados. Dados operacionais consolidados, correlações de negócio e dashboards corporativos pertencem ao futuro Seiden FLOW.

## Contrato canônico

Cada análise concluída produz um evento `vision.analysis_completed`, versão de esquema `1.0`, contendo correlação, origem, sujeito, análise, qualidade, mídia e tempos de processamento. O evento fica disponível no atributo `canonical_event` do sensor da última análise e pode ser enviado por webhook.

## API de análise

`POST /api/v1/analyze` continua aceitando o formato legado e agora também aceita:

```json
{
  "source_event_id": "bridge-event-123",
  "origin": {"source_id": "entrada", "source_type": "reader", "device_id": "recepcao"},
  "subject": {"person_id": "42", "person_name": "Eduardo"},
  "image": {"url": "https://.../foto.jpg"},
  "captured_at": "2026-07-23T18:00:00Z"
}
```

## Segurança

Quando `api_key` estiver preenchida, endpoints que alteram estado exigem `Authorization: Bearer <token>`.

## Webhook para o FLOW

Configure `webhook_enabled`, `webhook_url` e opcionalmente `webhook_api_key`. Falhas de webhook são registradas, mas não impedem o armazenamento técnico da análise.

## Compatibilidade

Sensores, APIs gerenciais e banco SQLite das versões 0.3.x foram mantidos. O campo legado `operational` continua existindo como alias temporário de `quality_evaluation`.
