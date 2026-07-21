# Seiden Vision 0.3.1

## Indicadores gerenciais

A versão publica sensores agregados para dashboards de POC no Home Assistant e fornece APIs independentes para evolução futura em Grafana.

### APIs

- `/api/v1/management/summary`
- `/api/v1/management/daily`
- `/api/v1/management/hourly`
- `/api/v1/management/people`
- `/api/v1/management/sources`

### Segurança

O dashboard gerencial no Home Assistant é apenas para POC local. Em produção, o Grafana deverá consumir um banco ou API próprios, sem expor o Home Assistant.
