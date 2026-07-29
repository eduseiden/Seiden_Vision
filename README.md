# Seiden Vision 0.8.3

Camada de percepção e enriquecimento de evidências do Seiden One.

## Arquitetura

O Vision consome eventos unificados da Seiden Bridge, interpreta as evidências recebidas e publica resultados canônicos para o Home Assistant, webhooks e Seiden FLOW.

Principais saídas:

- `vision.analysis_completed` para análises de imagem;
- `environment.observation` para interpretação ambiental por perfil.

O Vision enriquece evidências. A correlação operacional e a apresentação consolidada pertencem às demais camadas do Seiden One.

## Perfis ambientais

A versão 0.8.3 mantém todos os parâmetros ambientais em um arquivo JSON autoritativo e editável pelo usuário:

```text
/config/seiden_vision/environmental_profiles.json
```

Esse é o caminho visto pelo **File Editor** do Home Assistant. Dentro do contêiner do add-on, o mesmo arquivo é acessado em:

```text
/homeassistant/seiden_vision/environmental_profiles.json
```

Na primeira inicialização, o Vision cria o arquivo com os perfis padrão. Ao atualizar da 0.8.2, o arquivo existente em `addon_configs` é migrado automaticamente, preservando todas as personalizações.

Perfis distribuídos:

- `human_indoor`
- `human_outdoor`
- `refrigerator`
- `freezer`
- `wine_cellar`
- `beer_cooler`

Após editar o JSON, reinicie o add-on para aplicar as novas faixas. Overrides enviados por uma fonte da Bridge continuam tendo prioridade sobre o perfil base.

## Persistência

O banco de dados e as imagens permanecem na área própria do add-on. Somente o arquivo destinado à edição manual é mantido em `/config/seiden_vision`, para aparecer naturalmente no File Editor.
