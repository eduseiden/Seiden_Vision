# Seiden Vision 0.8.0

Camada de percepção do Seiden One. Transforma dados brutos em evidências enriquecidas.

## Arquitetura unificada

O Vision consome exclusivamente `seiden_bridge_event`. Não há mais leitura de `sensor.seiden_last_person`, polling de entidade ou modo híbrido.

Processa eventos `person_authenticated` do conector EVO que contenham `operation.photo_url`. A saída enriquecida preserva o `event_id` do Bridge em `source_event_id` e é publicada como `vision.analysis_completed`.

O Vision enriquece uma evidência; não correlaciona o conjunto nem conclui o que ocorreu na operação.

## Environmental Analyzer

O Vision reconhece eventos `mqtt.message_received` originados no Seiden Bridge quando `data.temperature` e `data.humidity` estão presentes. O resultado é publicado como evento Home Assistant `environment.observation`, preservando o `source_event_id` original.

A versão 0.8.0 preserva a identidade definida no Environmental Source Registry do Bridge. `source_name`, `location_name`, `asset_*`, `profile_id` e `description` passam a ter prioridade sobre nomes derivados do tópico MQTT. Eventos legados continuam usando o tópico como fallback.

## Perfis ambientais 0.8.0

O `profile_id` cadastrado na Seiden Bridge define como a medição é interpretada. Perfis disponíveis: `human_indoor`, `human_outdoor`, `refrigerator`, `freezer`, `wine_cellar` e `beer_cooler`.

A análise enriquecida inclui `analysis_type`, `environmental_score`, `operational_state`, scores por métrica e códigos de motivo. O campo `comfort_score` permanece como alias de compatibilidade durante a evolução do FLOW.

Os presets são referências operacionais iniciais e serão configuráveis em versão posterior. Um perfil desconhecido não interrompe o processamento: ele usa `human_indoor` como fallback e marca `profile_fallback: true`.
