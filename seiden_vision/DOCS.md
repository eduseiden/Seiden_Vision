# Seiden Vision 0.3.0

A versão 0.3.0 acrescenta uma camada de inteligência operacional independente do provedor. A resposta normalizada continua armazenada integralmente em `result_json`, agora com o bloco `operational`.

## Novas opções

- `quality_min_brightness`: luminosidade mínima aceitável.
- `quality_min_sharpness`: nitidez mínima aceitável.
- `aws_price_per_1000_images`: preço usado apenas para estimativa local de custo.

## Novas entidades

- `sensor.seiden_vision_last_quality`
- `sensor.seiden_vision_last_alert`
- `sensor.seiden_vision_last_total_time`

O sensor `sensor.seiden_vision_last_result` passa a publicar também emoções completas, pose, óculos, óculos escuros, barba, bigode, boca aberta, bounding box e bloco operacional.
