# Contribua com o Memoraio / Contributing

[Português](#português) · [English](#english)

## Português

Bem-vindo! O Memoraio aceita contribuições de código, testes, documentação, acessibilidade e relatos de uso. Você não precisa programar para ajudar.

### Escolha um primeiro passo

- **Uso Windows/WSL:** siga o guia e relate em que etapa encontrou dificuldade.
- **Uso Mac:** teste instalação, reabertura, pastas, tema e acesso aos TXT.
- **Design e acessibilidade:** avalie teclado, foco, contraste e compreensão dos estados da fila.
- **Documentação:** revise instruções e traduções usando exemplos fictícios.
- **Código:** escolha uma tarefa marcada `good first issue` ou `help wanted` em [Issues](../../issues).

Veja as [cinco tarefas iniciais](docs/community/START-HERE.md) e o [roadmap](docs/ROADMAP.md). As tarefas são oportunidades abertas; comente na issue se quiser combinar o escopo. Se não puder terminar, explique o que descobriu para outra pessoa continuar. Mudanças pequenas e bem explicadas facilitam a revisão.

### Ambiente de desenvolvimento

Python 3.12, FFmpeg/ffprobe e Node.js 22 ou superior. O motor básico funciona em macOS e Linux/WSL; a interface nativa e o reconhecimento MLX exigem Apple Silicon. Você pode contribuir com o motor e a documentação sem ter um Mac.

```sh
python3.12 -m venv .venv
# macOS / Linux / terminal Ubuntu no WSL:
. .venv/bin/activate
python -m pip install -r requirements-acquisition.txt -r requirements-licensing.lock.txt -r requirements-dev.lock.txt
python -m unittest discover -s tests -q
python -m compileall -q memoria licensing windows scripts
node --check memoria/static/app.js
ruff check memoria licensing macos scripts tests windows
```

Os testes usam catálogos temporários. Não execute testes apontando para seu acervo real. Não é necessário baixar modelos de voz para esses testes. Consulte [desenvolvimento](docs/development.md), [testes](docs/testing.md) e a [demonstração sintética](docs/demo.md).

### Como enviar uma mudança

1. Crie um fork e uma branch para uma mudança limitada.
2. Use dados sintéticos e preserve IDs estáveis, objetos válidos e versões anteriores.
3. Rode os testes relacionados e explique o que foi verificado.
4. Abra um pull request com o problema, o comportamento resultante e as limitações. Para interface, inclua teclado, temas diurno/noturno e janela estreita.
5. Aguarde a revisão. Propostas grandes precisam de discussão prévia sobre escopo.

### Privacidade e convivência

Nunca anexe listas pessoais de canais, transcrições reais, bancos, cookies, tokens, URLs de mídia assinadas ou capturas do seu acervo. Use o endereço `noreply` do GitHub nos commits. Revise o diff e execute `python scripts/audit_public.py . --tracked --history` antes de enviar. A comparação com fontes privadas, quando necessária, deve acontecer somente na máquina do proprietário; sua lista não deve acompanhar a contribuição.

Respeite o [código de conduta](CODE_OF_CONDUCT.md), a [política de privacidade](docs/privacy.md) e as [orientações de segurança](SECURITY.md). Não contorne restrições de acesso nem responda a limites de uso com rotação de IP. Contribuições originais seguem a licença MIT; preserve avisos de terceiros.

## English

Welcome! Contributions include code, installation testing, accessibility, documentation, translations and clear bug reports. Programming experience is not required for every task.

Start with an issue labeled `good first issue` or `help wanted`, the [starter tasks](docs/community/START-HERE.md), or the [roadmap](docs/ROADMAP.md). Comment if you would like to coordinate scope. Small, focused changes are easier to review; discuss large changes first.

### Development setup

Use Python 3.12, FFmpeg/ffprobe and Node.js 22+. The basic engine runs on macOS and Linux/WSL. The native Mac shell and MLX speech recognition require Apple Silicon. You can work on the engine and documentation without a Mac.

The shell commands in the Portuguese section above create an isolated environment and run the test suite without downloading speech models. Tests must use disposable catalogs, never your personal library. See [development](docs/development.md), [testing](docs/testing.md) and the [synthetic demo](docs/demo.md).

### Sending a contribution

Fork the project, create a focused branch, preserve stable IDs and prior valid artifacts, and run relevant tests. Explain the trigger, resulting behavior, validation and untested limits in your pull request. UI changes should cover keyboard access, light/dark themes and narrow windows. If you cannot finish a task, leave your findings so another contributor can continue.

Never upload personal source lists, real transcripts, databases, cookies, tokens, signed media URLs or library screenshots. Use a GitHub `noreply` commit email, review your diff and run `python scripts/audit_public.py . --tracked --history`. Any comparison against a personal catalog stays on its owner's computer; the private list must never be published.

Follow the [code of conduct](CODE_OF_CONDUCT.md), [privacy policy](docs/privacy.md) and [security guidance](SECURITY.md). Respect source scope and access controls. Original contributions are MIT licensed; preserve third-party licenses and notices. No production payment credentials are needed.
