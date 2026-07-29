# Changelog

## 0.6.0
- Adoção do Seiden One Platform Standard v1.0.
- Eventos de enriquecimento passam a emitir timestamps UTC canônicos com sufixo Z.
- Responsabilidade do módulo documentada como percepção e enriquecimento de evidências.

## 0.6.0 — Evento unificado sem fallback legado

- Remove `source_mode`, polling de entidade e `sensor.seiden_last_person`.
- Consome exclusivamente `seiden_bridge_event`.
- Preserva correlação por `source_event_id`.

# Changelog

## 0.4.1 — Bridge event integration

- Adicionado consumo direto do evento unificado `seiden_bridge_event` via WebSocket do Home Assistant.
- Eventos `person_authenticated` do conector EVO são convertidos em trabalhos de análise com correlação por `event_id`.
- Novo `source_mode`: `event`, `entity` ou `hybrid`.
- Modo padrão `hybrid` preserva a entidade `sensor.seiden_last_person` durante a transição e evita duplicidade pela URL da foto.
- Mantida a API `/api/v1/analyze` e o evento canônico `vision.analysis_completed`.
- O Vision não interpreta MQTT nem correlaciona eventos operacionais; apenas enriquece evidências que possuam mídia analisável.

## 0.4.0 — FLOW-ready perception layer

- Removidas referências padrão ao fabricante EVO.
- Versão centralizada em `version.py`.
- Novo evento canônico `vision.analysis_completed`, esquema 1.0.
- Correlação por `source_event_id` e `capture_id`.
- API aceita estruturas `origin`, `subject`, `image` e `correlation`.
- Publicação opcional por webhook com token Bearer.
- Autenticação opcional dos endpoints de alteração por API key.
- `intelligence.py` substituído conceitualmente por `quality_evaluator.py`.
- Banco, sensores e APIs 0.3.x preservados para compatibilidade.


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
