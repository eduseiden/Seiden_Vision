# Seiden Vision 0.3.2

## Novas opções

```yaml
person_event_cooldown_seconds: 10
image_retention_days: 30
max_stored_images: 5000
cleanup_interval_hours: 6
aws_monthly_budget_usd: 5.0
source_inactivity_minutes: 30
```

`person_event_cooldown_seconds` consolida capturas repetidas da mesma pessoa e fonte em um único evento operacional. As capturas continuam armazenadas para análise técnica.

## APIs adicionais

- `GET /api/v1/audit`
- `GET /api/v1/export/events.csv`
- `GET /api/v1/export/daily.csv`
- `GET /api/v1/management/summary`

## Custos

Os valores exibidos são estimativas do uso do Rekognition calculadas a partir das chamadas registradas e do preço configurado por mil imagens. Não substituem a fatura oficial da AWS.

## Migração

A inicialização adiciona automaticamente as novas colunas e a tabela de auditoria ao banco existente. Não é necessário apagar `seiden_vision.db`.
