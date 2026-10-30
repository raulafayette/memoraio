# Diagnosticar e simplificar uma etapa da primeira instalação no Mac

## Contexto

A instalação pessoal usa motor, ambiente e dados fora da pasta do código. Ainda exige dependências e ferramentas de desenvolvimento. Queremos descobrir e reduzir uma dificuldade real da primeira utilização.

## Primeiro passo

Use uma conta de teste em Mac Apple Silicon e leia `docs/installation.md`, `Instalar.command` e `scripts/install_macos.py`. Não execute o instalador sobre um acervo de produção.

## Escopo

- Registrar os pré-requisitos efetivamente necessários, sem identidade ou caminhos pessoais.
- Conferir se dependências ausentes são informadas antes de criar uma instalação parcial.
- Confirmar que a instalação básica não baixa modelos de voz.
- Verificar abertura, fechamento e reabertura do aplicativo, e o funcionamento do serviço fora do checkout.
- Escolher uma etapa confusa e propor uma melhoria pequena: mensagem, checagem prévia ou instrução.

## Conclusão

Relatório de instalação limpa e/ou PR com uma melhoria delimitada e verificação. Não desative Gatekeeper, não remova quarentena e não transforme esta tarefa em uma promessa de distribuição notarizada. Assinatura/notarização para distribuição ampla permanece uma frente separada.

**English:** test first-time installation on an Apple Silicon test account, identify one concrete friction point and improve its preflight check, message or instructions without weakening platform protections.

---
Leia o [guia de contribuição](https://github.com/raulafayette/memoraio/blob/main/CONTRIBUTING.md) e a [política de privacidade](https://github.com/raulafayette/memoraio/blob/main/docs/privacy.md). Comente se quiser combinar o escopo; relatos e testes também são contribuições.
