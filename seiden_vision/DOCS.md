# Seiden Vision 0.8.0

Camada de percepção do Seiden One. Transforma dados brutos em evidências enriquecidas.

## Arquitetura unificada

O Vision consome exclusivamente `seiden_bridge_event`. Não há mais leitura de `sensor.seiden_last_person`, polling de entidade ou modo híbrido.

Processa eventos `person_authenticated` do conector EVO que contenham `operation.photo_url`. A saída enriquecida preserva o `event_id` do Bridge em `source_event_id` e é publicada como `vision.analysis_completed`.

O Vision enriquece uma evidência; não correlaciona o conjunto nem conclui o que ocorreu na operação.

## Environmental Analyzer

O Vision reconhece eventos `mqtt.message_received` originados no Seiden Bridge quando `data.temperature` e `data.humidity` estão presentes. O resultado é publicado como evento Home Assistant `environment.observation`, preservando o `source_event_id` original.

A versão 0.8.0 preserva a identidade definida no Environmental Source Registry do Bridge. `source_name`, `location_name`, `asset_*`, `profile_id` e `description` passam a ter prioridade sobre nomes derivados do tópico MQTT. Eventos legados continuam usando o tópico como fallback.

## Perfis ambientais configuráveis

A versão 0.8.2 usa um único arquivo persistente como fonte dos parâmetros ambientais:

```text
/config/environmental_profiles.json
```

No Home Assistant, ele fica visível em:

```text
/addon_configs/<id>_seiden_vision/environmental_profiles.json
```

Na primeira inicialização, o Vision cria automaticamente esse arquivo com todos os perfis padrão. Depois disso, basta editar os valores e reiniciar o add-on. Atualizações não sobrescrevem o arquivo persistente.

O arquivo distribuído com a imagem existe apenas como modelo de instalação inicial:

```text
/app/profiles/environmental_profiles.default.json
```

Não há uma segunda cópia das faixas no código Python. O JSON persistente é autoritativo.

A ordem das faixas deve ser:

```text
critical.min <= attention.min <= optimal.min <= optimal.max <= attention.max <= critical.max
```

O evento `environment.observation` informa as faixas efetivamente usadas em `analysis.applied_ranges`. A origem será `persistent_file` ou `source_override`.

Overrides individuais enviados pela Bridge continuam tendo prioridade sobre o arquivo persistente.

## Perfis ambientais configuráveis

A versão 0.8.1 mantém os perfis padrão em:

```text
/app/profiles/environmental_profiles.json
```

Para alterar faixas padrão ou criar perfis próprios sem modificar o código, crie:

```text
/config/environmental_profiles.json
```

O arquivo customizado é mesclado com a biblioteca padrão. Portanto, é possível sobrescrever apenas os campos necessários:

```json
{
  "profiles": {
    "human_indoor": {
      "temperature": {
        "optimal": {"min": 22.0, "max": 24.0}
      }
    }
  }
}
```

Também é possível criar um perfil completo, como `server_room`. Um exemplo está em:

```text
/app/profiles/environmental_profiles.example.json
```

### Override por fonte

Quando a Bridge enviar `environment.profile_override`, o Vision aplica esse conteúdo sobre o perfil resolvido. Exemplo:

```json
{
  "profile_id": "wine_cellar",
  "profile_override": {
    "temperature": {
      "optimal": {"min": 13.0, "max": 15.0}
    }
  }
}
```

O evento `environment.observation` informa as faixas efetivamente usadas em `analysis.applied_ranges` e a origem em `analysis.ruleset_source`.
