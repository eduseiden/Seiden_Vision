# Seiden Vision 0.7.1

Camada de percepção do Seiden One. Transforma dados brutos em evidências enriquecidas.

## Arquitetura unificada

O Vision consome exclusivamente `seiden_bridge_event`. Não há mais leitura de `sensor.seiden_last_person`, polling de entidade ou modo híbrido.

Processa eventos `person_authenticated` do conector EVO que contenham `operation.photo_url`. A saída enriquecida preserva o `event_id` do Bridge em `source_event_id` e é publicada como `vision.analysis_completed`.

O Vision enriquece uma evidência; não correlaciona o conjunto nem conclui o que ocorreu na operação.

## Environmental Analyzer

O Vision reconhece eventos `mqtt.message_received` originados no Seiden Bridge quando `data.temperature` e `data.humidity` estão presentes. O resultado é publicado como evento Home Assistant `environment.observation`, preservando o `source_event_id` original.

A versão 0.7.1 consolida a numeração do add-on, do runtime e da documentação, sem alterar os contratos de eventos existentes.
