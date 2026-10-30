# Windows — edição experimental com WSL 2

Esta edição usa o motor Linux dentro do Windows, com interface no navegador. Não é um executável nativo Windows. Ainda requer validação de ponta a ponta em um PC Windows; o CI Linux verifica o motor e a sintaxe do instalador. O reconhecimento MLX do Instagram e a janela de login nativa do Mac não estão disponíveis nesta edição. Downloads públicos MP3/MP4 e legendas são o escopo inicial.

1. Instale WSL 2 e Ubuntu 24.04 ou posterior conforme a [Microsoft](https://learn.microsoft.com/windows/wsl/install). Conclua a criação do usuário Ubuntu.
2. No Ubuntu instale Python 3.12+, python3-venv, FFmpeg: `sudo apt update` e `sudo apt install python3 python3-venv ffmpeg`. Instale também Node.js **22 ou superior para Linux dentro do Ubuntu**, pelo [distribuidor oficial](https://nodejs.org/en/download). A versão de Node dos repositórios de uma distribuição antiga pode ser insuficiente; o instalador confere a versão antes de copiar o motor. O requisito segue o [runtime JavaScript do yt-dlp](https://github.com/yt-dlp/yt-dlp/wiki/EJS).
3. Baixe e extraia o código completo do repositório. Execute `windows/Instalar.cmd`.
4. Abra `windows/Abrir.cmd` nas próximas utilizações. Escolha seus canais e dê play manualmente.

Motor, ambiente e acervo ficam em `~/.local/share/Memoraio` dentro do Ubuntu, fora da pasta extraída. Para acessar os TXT no Explorador use `\\wsl$\Ubuntu\home\<seu usuário>\.local\share\Memoraio\data`. O seletor nativo de pastas do Mac não existe no navegador; configure um caminho Linux absoluto nos ajustes. Mantenha catálogo e objetos no sistema de arquivos Linux para preservar as garantias de bloqueio e gravação. Não mova o catálogo para `/mnt/c`.

Fechar a aba mantém o serviço durante a sessão WSL. Desligar o Windows, encerrar WSL ou sair da conta interrompe os trabalhos; o próximo Abrir inicia o serviço e recupera os checkpoints. Não há tarefa de download automática no login. O programa não instala nem reconfigura WSL sem ação do usuário.

Atualizações: pause todos os trabalhos, aguarde os trabalhos em andamento pararem e encerre o serviço antes de substituir o motor. Preserve sempre `data` e `runtime`. O instalador recusa sobrescrever uma instalação existente.
