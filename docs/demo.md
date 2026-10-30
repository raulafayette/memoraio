# Demonstração com dados fictícios

A demonstração mostra a interface real em um catálogo temporário criado do zero. Os nomes, textos e identificadores são fictícios. O progresso de processamento é simulado e identificado na imagem. Não são iniciados workers de provedores, downloads de mídia real nem reconhecimento de voz.

O roteiro mostra o resumo por canal, a abertura de um TXT, o início manual, o progresso ilustrativo, a pausa e a página de MP3/MP4. O vídeo não registra a Mesa, janelas de outros aplicativos, barra de endereço nem um perfil pessoal de navegador.

## Reproduzir

Instale as dependências básicas do guia de contribuição, FFmpeg e o Playwright em um ambiente Node de desenvolvimento. Instale o Chromium de testes com `npx playwright install chromium ffmpeg` nesse ambiente ou aponte `DEMO_BROWSER` para um executável de teste compatível. Se o Playwright estiver fora do projeto, configure `NODE_PATH` para seu diretório de módulos.

Da raiz do repositório:

```sh
python -m scripts.community.demo --output /tmp/memoraio-demo-output
```

O comando exige uma pasta de saída vazia. Cria vídeo MP4, gravação intermediária WebM, imagem PNG e um manifesto com hashes e origem sintética. Esses artefatos são destinados a uma release de demonstração revisada; não devem ser adicionados ao histórico de código.

Antes de publicar, assista ao vídeo, confira a imagem e compare os nomes com as fontes privadas localmente. O rótulo de demonstração deve permanecer visível. O vídeo ilustra o fluxo da interface; não certifica acesso a plataformas, velocidade real de processamento nem funcionamento em todos os computadores.

## Demonstração publicada

[Vídeo MP4](https://github.com/raulafayette/memoraio/releases/download/v0.3.0-community-preview/memoraio-demo-sintetica.mp4) · [Imagem](https://github.com/raulafayette/memoraio/releases/download/v0.3.0-community-preview/memoraio-demo-sintetica.png) · [Manifesto de origem e hashes](https://github.com/raulafayette/memoraio/releases/download/v0.3.0-community-preview/demo-provenance.json).
