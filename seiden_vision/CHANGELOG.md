# Changelog

## 0.2.0

- Primeira integração real com Amazon Rekognition `DetectFaces`.
- Adaptadores selecionáveis: `mock` e `aws_rekognition`.
- Nova camada `vision_adapters` e modelo normalizado `VisionResult`.
- Envio da imagem diretamente em memória, sem Amazon S3.
- Região AWS configurável, com `us-east-1` como padrão.
- Campos de credenciais mascarados na configuração do add-on.
- Nenhuma credencial é escrita nos logs ou publicada no Home Assistant.
- Atributos completos de face via `Attributes=["ALL"]`.
- Normalização de emoção, qualidade, pose, idade, gênero, sorriso, olhos, oclusão e outros atributos.
- Timeout, retries e mensagens de erro específicas da AWS.
- Limite diário configurável para chamadas AWS.
- Armazenamento opcional do retorno bruto da AWS no SQLite.
- Endpoint e botão para testar o adaptador usando uma imagem real.
- Métricas separadas de download e processamento.
- Novo sensor `sensor.seiden_vision_region`.
- Mantida compatibilidade com AMD64 e AArch64.

## 0.1.1

- Substituição do servidor Flask de desenvolvimento por Gunicorn.
- Um único processo Gunicorn com múltiplas threads, evitando duplicidade do watcher e da fila.
- Logs operacionais detalhados por análise.
- Publicação de sensores operacionais adicionais.
