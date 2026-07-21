# Seiden Vision 0.1.1

## Finalidade

Esta versão valida a arquitetura local do produto antes da integração com AWS Rekognition.

## Configuração

Todos os parâmetros são informados na aba **Configuração** do add-on.

### Fonte Home Assistant

Quando `source_enabled` estiver ativo, o add-on consulta a entidade configurada em
`source_entity_id` e observa o atributo indicado em `source_photo_attribute`.

Exemplo:

- entidade: `sensor.seiden_evo_last_person`
- atributo: `photo_url`

Ao detectar uma URL nova, o add-on coloca a imagem na fila.

## Interface Web

A interface oferece:

- estado do serviço;
- teste manual de URL;
- histórico das análises;
- estatísticas;
- limpeza do histórico;
- teste de publicação no Home Assistant.

## API

### Saúde

`GET /api/v1/health`

### Estatísticas

`GET /api/v1/stats`

### Histórico

`GET /api/v1/analyses`

### Enviar imagem

`POST /api/v1/analyze`

```json
{
  "source": "Entrada Principal",
  "image_url": "http://192.168.1.100/foto.jpg",
  "person": "Nome opcional",
  "captured_at": "2026-07-21T15:30:00-03:00"
}
```

## Observação

O provedor `mock` gera resultados determinísticos a partir do hash da imagem. Ele não realiza
análise facial real. Sua finalidade é validar a infraestrutura completa sem consumo de serviços externos.


## Sensores operacionais da versão 0.1.1

- `sensor.seiden_vision_status`
- `sensor.seiden_vision_queue`
- `sensor.seiden_vision_provider`
- `sensor.seiden_vision_version`
- `sensor.seiden_vision_uptime`
- `sensor.seiden_vision_last_processing`
- `sensor.seiden_vision_last_result`
- `sensor.seiden_vision_analyses_today`

O servidor web agora utiliza Gunicorn com um único processo e múltiplas threads. O único processo é intencional: evita que várias instâncias do watcher processem a mesma fotografia.
