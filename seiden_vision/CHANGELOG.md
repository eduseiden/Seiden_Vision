# Changelog

## 0.8.0 — Environmental Profiles

- adiciona interpretação ambiental por `profile_id` recebido da Seiden Bridge;
- inclui os perfis fixos `human_indoor`, `human_outdoor`, `refrigerator`, `freezer`, `wine_cellar` e `beer_cooler`;
- adiciona `analysis_type`, `environmental_score`, `operational_state`, `metric_scores` e `reason_codes`;
- preserva `comfort_score` e `condition` para compatibilidade com o FLOW atual;
- aceita sensores somente de temperatura quando o perfil não utiliza umidade;
- perfis desconhecidos usam `human_indoor` como fallback explícito e rastreável;
- mantém o contrato canônico 2.0 e não exige migração de banco.

## 0.7.1 — Preservação da identidade ambiental

- prioriza nomes amigáveis, local, ativo, descrição e perfil recebidos do Bridge 0.12.0;
- usa o tópico MQTT apenas como fallback para eventos legados;
- prioriza medições canônicas `temperature_c`, `humidity_pct` e `battery_pct`;
- inclui `identity_source` e `profile_id` no evento enriquecido;
- mantém compatibilidade com o schema 2.0 e com eventos ambientais anteriores.

## 0.7.0 — Consolidação de versão e documentação

- Alinha a versão exibida no add-on, no runtime, no log de inicialização e na documentação.
- Atualiza o User-Agent do publicador webhook para a versão atual.
- Consolida a documentação do Environmental Analyzer e dos eventos `vision.analysis_completed` e `environment.observation`.
- Remove artefatos locais de cache Python do pacote de distribuição.
- Nenhuma alteração funcional nos analyzers ou no schema canônico 2.0.

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

## 0.6.1

- Introduz a arquitetura extensível de Analyzers no Seiden Vision.
- Adiciona o Environmental Analyzer para eventos MQTT com temperatura e umidade.
- Publica evidências canônicas `environment.observation` no Home Assistant e no webhook configurado.
- Normaliza temperatura para Celsius e umidade para percentual.
- Classifica cada observação como `comfortable`, `attention` ou `uncomfortable`.
- Calcula `comfort_score` determinístico de 0 a 100 com regras transparentes.
- Preserva `correlation.source_event_id` e evita reprocessamento em memória.
- Expõe os analyzers ativos no endpoint de saúde.

## 0.8.1

- Move os perfis ambientais padrão para `app/profiles/environmental_profiles.json`.
- Permite customizar ou criar perfis por meio de `/config/environmental_profiles.json`.
- Aceita `profile_override` por fonte, recebido no evento da Seiden Bridge.
- Valida coerência das faixas e pesos antes de aplicar o ruleset.
- Publica `ruleset_source`, `profile_customized` e `applied_ranges` no evento enriquecido.
- Mantém fallback seguro para `human_indoor` quando o perfil solicitado não existe.
