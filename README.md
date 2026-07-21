# Seiden Vision

Plataforma local de orquestração e análise de imagens para Home Assistant OS.

A versão **0.1.0** estabelece a fundação do produto:

- add-on para Home Assistant OS;
- suporte a `amd64` e `aarch64`;
- configuração integral pela interface do add-on;
- interface web via Ingress;
- API REST;
- fila assíncrona de processamento;
- banco SQLite persistente;
- deduplicação por SHA-256;
- Mock Vision Provider;
- publicação de sensores no Home Assistant;
- observação opcional de uma entidade do Home Assistant.

## Estrutura

```text
Seiden_Vision/
├── repository.yaml
└── seiden_vision/
    ├── config.yaml
    ├── build.yaml
    ├── Dockerfile
    ├── run.sh
    └── app/
```

## Instalação

1. Publique este conteúdo na raiz do repositório `Seiden_Vision`.
2. No Home Assistant, abra **Configurações → Aplicativos → Loja**.
3. Adicione a URL do repositório.
4. Instale o **Seiden Vision**.
5. Abra a aba **Configuração**, ajuste os parâmetros e inicie o add-on.
6. Abra **Interface Web**.

## Teste inicial

Na interface web, informe uma URL de imagem acessível pelo Raspberry Pi ou pelo mini PC e clique em **Analisar**.

A versão 0.1.0 utiliza um provedor simulado. A integração real com AWS Rekognition será adicionada na próxima fase.
