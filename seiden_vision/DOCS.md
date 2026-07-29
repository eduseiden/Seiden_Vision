# Seiden Vision 0.8.3

Camada de percepção do Seiden One. Transforma dados brutos em evidências enriquecidas.

## Arquitetura unificada

O Vision consome exclusivamente `seiden_bridge_event`. Não há leitura de `sensor.seiden_last_person`, polling de entidade ou modo híbrido.

Eventos `person_authenticated` com `operation.photo_url` podem produzir `vision.analysis_completed`. Eventos ambientais originados na Bridge podem produzir `environment.observation`, preservando a correlação por `source_event_id`.

O Vision interpreta e enriquece uma evidência; não realiza a correlação operacional completa.

## Environmental Analyzer

O analisador ambiental preserva a identidade definida no Environmental Source Registry da Bridge. `source_name`, `location_name`, `asset_*`, `profile_id` e `description` têm prioridade sobre nomes derivados do tópico MQTT.

Cada evento é interpretado segundo o `profile_id` informado. O resultado inclui, entre outros campos:

- `analysis_type`;
- `environmental_score`;
- `comfort_score` para compatibilidade;
- `condition`;
- `operational_state`;
- `metric_scores`;
- `reason_codes`;
- `applied_ranges`;
- `ruleset_source`.

## Arquivo de perfis ambientais

O JSON autoritativo e editável fica, no File Editor do Home Assistant, em:

```text
/config/seiden_vision/environmental_profiles.json
```

Dentro do contêiner do Vision, o caminho correspondente é:

```text
/homeassistant/seiden_vision/environmental_profiles.json
```

Na primeira inicialização, o Vision cria o arquivo usando o modelo distribuído em:

```text
/app/profiles/environmental_profiles.default.json
```

As faixas não ficam duplicadas no código Python. Depois da criação, o JSON persistente passa a ser a fonte dos parâmetros. O Vision não o sobrescreve em atualizações.

### Migração da 0.8.2

Caso exista:

```text
/addon_configs/<id>_seiden_vision/environmental_profiles.json
```

a 0.8.3 copia o conteúdo para `/config/seiden_vision/environmental_profiles.json` antes de carregar os perfis. Após a cópia bem-sucedida, o arquivo antigo é preservado como:

```text
environmental_profiles.migrated-0.8.2.backup.json
```

Portanto, personalizações existentes não são perdidas. A partir da 0.8.3, somente o arquivo em `/config/seiden_vision` é autoritativo.

### Validação

Para cada métrica, a ordem obrigatória é:

```text
critical.min <= attention.min <= optimal.min <= optimal.max <= attention.max <= critical.max
```

O perfil `human_indoor` é obrigatório porque funciona como fallback para `profile_id` desconhecido. Pesos não podem ser negativos.

Depois de editar o arquivo, reinicie o add-on. Um JSON inválido ou faixas incoerentes impedem o carregamento dos perfis e produzem uma mensagem explícita no log.

### Override por fonte

Quando a Bridge envia `environment.profile_override`, o conteúdo é aplicado sobre o perfil resolvido. Nesse caso, o evento informa:

```yaml
ruleset_source: source_override
profile_customized: true
```

Sem override individual, a origem é:

```yaml
ruleset_source: persistent_file
profile_customized: false
```

## Persistência interna

O banco `seiden_vision.db` e a pasta `images` continuam na área própria do add-on (`addon_config`). Apenas o JSON destinado à edição humana foi movido para a configuração principal do Home Assistant.
