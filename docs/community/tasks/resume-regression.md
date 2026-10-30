# Ampliar teste isolado de interrupção e retomada sem duplicar TXT

## Contexto

O projeto já tem testes de leases, checkpoints, pausa e retomada. Queremos ampliar a cobertura com um cenário delimitado que ainda não esteja comprovado, preservando transcrições já válidas.

## Primeiro passo

Leia `tests/test_durability.py`, `test_sync_v2.py`, `test_workspace_v11.py` e `test_launcher.py`, além de `memoria/core.py` e `transcription.py`. Antes de codificar, descreva na issue a lacuna encontrada para evitar duplicar um teste existente.

## Entrega pequena

- Criar um catálogo temporário e um artefato inteiramente sintético.
- Interromper somente processos criados pelo próprio teste em um ponto controlado do cenário escolhido.
- Reiniciar o motor de teste e verificar o estado persistido.
- Demonstrar que o arquivo já válido mantém o hash, que o TXT não é contado duas vezes e que outra fila pausada não foi liberada inadvertidamente.
- Garantir limpeza dos processos, arquivos e portas temporárias.

## Conclusão

Um teste de regressão relevante que falhe para a lacuna identificada ou confirme explicitamente um contrato ainda sem cobertura. Se houver bug, uma correção pequena pode acompanhar o teste. Nunca aponte o teste para um serviço ou acervo de uso pessoal.

**English:** identify an uncovered recovery contract and add a disposable, deterministic regression test proving integrity, deduplication and preservation of independent pauses.

---
Leia o [guia de contribuição](https://github.com/raulafayette/memoraio/blob/main/CONTRIBUTING.md) e a [política de privacidade](https://github.com/raulafayette/memoraio/blob/main/docs/privacy.md). Comente se quiser combinar o escopo; relatos e testes também são contribuições.
