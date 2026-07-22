# Changelog

## 0.3.2 — Reliability & Cost Management

- Saúde operacional consolidada, taxa de sucesso, último sucesso e último erro.
- Erros categorizados por origem e trilha de auditoria.
- Identificador único por análise (`event_id`).
- Consolidação de capturas em eventos operacionais com cooldown por pessoa e fonte.
- Tempos de download, provider, banco, publicação no HA, total, P50 e P95.
- Retenção automática de imagens por idade e quantidade máxima.
- Chamadas e custos estimados diário, semanal e mensal.
- Projeção mensal, budget local e status de consumo.
- Exportações CSV de eventos e tendência diária.
- Novos sensores gerenciais e dashboard unificado atualizado.
- Migração automática e compatibilidade com o banco 0.3.1.


## 0.3.1

- Camada de BI gerencial para o POC.
- Indicadores de eventos, pessoas distintas, alertas, qualidade, latência e custo.
- Comparação de hoje com ontem e média dos últimos sete dias.
- Tendências diárias e distribuição horária.
- Rankings por pessoa e por fonte.
- Novas APIs `/api/v1/management/*`.
- Novos sensores gerenciais no Home Assistant.
- Fuso horário gerencial configurável.
- Compatibilidade preservada com o banco da 0.3.0.
