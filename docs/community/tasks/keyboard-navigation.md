# Auditar e melhorar navegação por teclado nos canais e downloads

## Contexto

Controles compactos precisam continuar compreensíveis e acessíveis sem mouse. Queremos identificar uma barreira concreta de foco, nome acessível ou sequência de navegação e corrigi-la em uma mudança pequena.

## Primeiro passo

Use um catálogo temporário com fontes fictícias. Consulte `memoria/static/index.html`, `app.js`, `style.css` e `tests/ui_channels_v5.js`.

## Escopo

- Percorrer navegação lateral, controles dos cartões, filtros e lista de downloads com Tab e Shift+Tab.
- Conferir acionamento por Enter/Espaço e nomes compreensíveis para símbolos.
- Verificar foco visível nos temas claro e escuro, inclusive na abertura e fechamento do TXT.
- Escolher uma barreira reproduzida, descrever os passos e propor a menor correção útil. A existência de uma barreira específica ainda precisa ser demonstrada.

## Conclusão

Relato reproduzível e, se houver correção de código, verificação de regressão focada. Evite redesenhar toda a interface neste PR. Capturas devem usar apenas dados fictícios.

**English:** audit keyboard access, accessible names and focus visibility; reproduce one concrete barrier and submit a focused fix with verification.

---
Leia o [guia de contribuição](https://github.com/raulafayette/memoraio/blob/main/CONTRIBUTING.md) e a [política de privacidade](https://github.com/raulafayette/memoraio/blob/main/docs/privacy.md). Comente se quiser combinar o escopo; relatos e testes também são contribuições.
