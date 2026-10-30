# Validar a instalação Windows/WSL em um PC limpo

## Contexto

A edição atual Windows usa WSL 2 com Ubuntu e interface no navegador. O CI Linux testa o motor, mas não substitui uma instalação real em Windows. Precisamos de um relatório reproduzível de primeira utilização. Esta tarefa não pede a construção de um aplicativo Windows nativo.

## Primeiro passo

Leia `docs/windows.md` e `windows/Instalar.cmd`, em uma conta ou máquina de teste. Use Python 3.12+, FFmpeg e Node 22+ dentro do Ubuntu. Não use seu catálogo pessoal.

## Entrega pequena

- Registrar versão do Windows, Ubuntu e dependências, sem nome de usuário nem caminhos pessoais.
- Seguir instalação e abertura exatamente como documentadas.
- Confirmar que a interface abre no navegador e que o novo catálogo começa vazio.
- Conferir que reabrir não cria outra biblioteca e que uma segunda execução do instalador preserva a instalação existente.
- Se houver problema, descrever passos, resultado esperado e mensagem revisada. Uma correção pequena na documentação pode acompanhar o relato.

## Conclusão

Um relatório na issue ou um PR com instruções corrigidas e os limites que não puderam ser testados. Nenhum vídeo ou transcrição real precisa ser anexado. Não execute operações de coleta sem autorização sobre a fonte usada.

**English:** validate the documented WSL preview on a clean Windows account and report reproducible installation/reopening results. A native Windows client is outside this task.

---
Leia o [guia de contribuição](https://github.com/raulafayette/memoraio/blob/main/CONTRIBUTING.md) e a [política de privacidade](https://github.com/raulafayette/memoraio/blob/main/docs/privacy.md). Comente se quiser combinar o escopo; relatos e testes também são contribuições.
