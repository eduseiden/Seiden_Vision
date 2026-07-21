# Seiden Vision

Plataforma local de orquestração e análise de imagens para Home Assistant e futuras integrações operacionais.

## Versão 0.2.0

- Mock Adapter para testes locais.
- AWS Rekognition `DetectFaces` para análise real.
- Arquitetura independente de provedor por meio de `vision_adapters`.
- Resultado normalizado em `VisionResult`.
- SQLite persistente no diretório próprio do add-on.
- Interface Ingress, API REST, fila, deduplicação e sensores no Home Assistant.
- Suporte AMD64 e AArch64.

Consulte `seiden_vision/DOCS.md` para instalação e configuração.
