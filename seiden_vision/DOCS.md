# Seiden Vision 0.2.0

## Finalidade

A versão 0.2.0 introduz análise facial real por meio do Amazon Rekognition, mantendo o Mock Adapter para testes sem custo.

## Configuração AWS

Selecione `aws_rekognition` e preencha:

- `aws_region`: normalmente `us-east-1`;
- `aws_access_key_id`;
- `aws_secret_access_key`;
- `aws_max_analyses_per_day`;
- timeouts e tentativas conforme necessário.

O usuário IAM deve possuir apenas `rekognition:DetectFaces`. As imagens são enviadas em memória como bytes JPEG ou PNG; não é necessário criar bucket S3.

As chaves são armazenadas nas opções privadas do add-on. O Seiden Vision não as grava nos logs, no banco de dados nem nos estados do Home Assistant.

## Teste do adaptador

Na interface do Seiden Vision, clique em **Testar adaptador**. O teste usa a URL preenchida no formulário. Se ela estiver vazia, usa a última imagem disponível na entidade configurada como fonte.

O teste realiza uma análise real e, portanto, pode gerar uma chamada faturável quando o adaptador AWS estiver selecionado.

## Resultado normalizado

Todos os adaptadores retornam o mesmo contrato `VisionResult`, com campos como:

- quantidade de faces;
- emoção dominante;
- confiança;
- brilho e nitidez;
- pose;
- faixa etária;
- gênero;
- sorriso, olhos abertos e oclusão;
- região, Request ID e tempo de processamento.

## Limite diário

`aws_max_analyses_per_day` impede novas análises automáticas depois que o número configurado de análises AWS concluídas no dia é alcançado. É uma proteção operacional adicional ao AWS Budget, não um limite de faturamento da própria AWS.

## API

- `GET /api/v1/health`
- `GET /api/v1/stats`
- `GET /api/v1/analyses`
- `POST /api/v1/analyze`
- `POST /api/v1/provider/test`
- `POST /api/v1/publish-test`
- `DELETE /api/v1/analyses`
