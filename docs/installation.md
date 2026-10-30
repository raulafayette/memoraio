# Installation

Target: macOS 14+ on Apple Silicon, Python 3.12, FFmpeg/ffprobe, Node and Apple's command-line tools. The current native build was validated on a newer SDK; minimum-OS and clean-machine testing remain release requirements. Allow at least 10 GiB free before dependency/model setup, plus space for media and a 5 GiB operating reserve.

Install prerequisites through their official package sources. From a source checkout run Instalar.command. It creates engine, runtime and data under `~/Library/Application Support/Memoraio`, installs caption/media dependencies and registers a per-user launchd service. No speech models are downloaded by default. Internet is required for setup and source acquisition; configured models run locally.

Build with `python3 macos/build.py`; open Memoraio.app. The installed engine is independent of the source checkout. The app is copied to `~/Applications/Memoraio.app`. Existing installations are preserved rather than overwritten automatically. New public installations contain no preset personal sources. Add authorized sources in the UI, or provide a private data/bootstrap-sources.json containing name/URL pairs before bootstrap.

If setup fails, retain data and inspect the error; do not remove the database to retry. `python -m memoria doctor` reports tools and disk; `python -m memoria verify` checks catalog and referenced objects. Models, runtime and data are not inside the public app bundle.

Optional licensing tests use requirements-licensing.lock.txt; they do not enable payment processing. .env.example contains empty variables only and is not an invitation to store real secrets in Git.

For Windows see [the WSL preview](windows.md). Local MLX speech recognition remains an optional Apple Silicon feature; install the full model dependencies and configure models only when needed.

## Atualizar com segurança

O instalador de primeira instalação recusa sobrescrever um motor existente. Para atualizar, pause todos os trabalhos, aguarde não haver trabalhos em execução e encerre apenas o serviço do Memoraio. Faça backup do catálogo. Substitua somente `engine` por uma exportação limpa revisada e atualize as dependências do ambiente `runtime`, mantendo `data` intacto. Registre o serviço com o Python de `runtime` e `--data` apontando para o acervo permanente. Restaure a pausa anterior somente após verificar a integridade. Não use o instalador inicial para migrar um acervo ativo.
