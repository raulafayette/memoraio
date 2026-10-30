<div align="center">

# Memoraio

**Transforme conteúdo que você acompanha em uma memória que você consegue consultar.**

Um aplicativo aberto para organizar transcrições e downloads, acompanhar novidades por canal e construir um acervo local sob seu controle.

[Por que existe](#por-que-o-memoraio-existe) · [Como funciona](#como-funciona) · [Instalação](#instalação) · [Como contribuir](#vamos-construir-juntos)

</div>

![Visão conceitual do Memoraio: escolher fontes, acompanhar a fila e consultar o acervo. Nenhum dado real é exibido.](assets/overview.svg)

> **Projeto em desenvolvimento.** A versão principal usa um aplicativo nativo para macOS Apple Silicon. A edição Windows é uma prévia experimental com WSL 2 e navegador. O repositório compartilha o software e a proposta do projeto; cada instalação começa com o acervo vazio.

## Por que o Memoraio existe

Um vídeo pode guardar uma explicação importante. Uma conversa pode trazer uma ideia que vale pesquisar depois. Ao acompanhar vários canais ao longo do tempo, esse material se dispersa entre plataformas, links salvos e pastas difíceis de entender.

O problema reaparece a cada visita: o que já foi guardado? O que chegou de novo? Qual download ficou pela metade? Onde está a transcrição daquela conversa? Baixar tudo novamente desperdiça tempo, conexão e espaço. Manter uma coleção sem organização dificulta encontrar o que ela contém.

O Memoraio nasce para dar continuidade a esse trabalho. Ele mantém um catálogo do acervo, mostra a situação de cada canal e organiza os arquivos para que possam ser encontrados depois. Você consulta as novidades, escolhe o que deseja guardar e acompanha o andamento. Na próxima utilização, o programa parte do que já existe.

A ideia é tornar a preservação e a consulta de conteúdo audiovisual uma rotina compreensível — para estudo, pesquisa, produção e organização de referências, respeitando as permissões de acesso e os direitos sobre o conteúdo.

## Veja o aplicativo em ação

[![Interface com canais inteiramente fictícios](https://github.com/raulafayette/memoraio/releases/download/v0.3.0-community-preview/memoraio-demo-sintetica.png)](https://github.com/raulafayette/memoraio/releases/download/v0.3.0-community-preview/memoraio-demo-sintetica.mp4)

[Assistir à demonstração curta em MP4](https://github.com/raulafayette/memoraio/releases/download/v0.3.0-community-preview/memoraio-demo-sintetica.mp4) · [Como foi produzida](docs/demo.md)

A interface é real; os canais e textos são fictícios e o progresso é simulado e identificado. Nenhum acervo pessoal foi utilizado. Veja as [tarefas abertas para colaborar](https://github.com/raulafayette/memoraio/issues).

## O que você consegue fazer

| Necessidade | Como o Memoraio ajuda |
|---|---|
| Saber em que pé está cada canal | Cartões com quantidade de transcrições disponíveis, itens identificados, pendências e última consulta. |
| Descobrir novidades sem começar um download | Atualização individual ou coletiva do levantamento, separada do botão de iniciar. |
| Controlar o processamento | Início individual, de selecionados ou de todos; pausa por canal e fila persistente. |
| Entender o andamento | Grupos separados por estado, quatro barras por canal e progresso geral das transcrições. |
| Consultar o texto | TXT acessível pela interface, organizado por canal e mês, com diretório padrão e destinos individuais. |
| Baixar mídia | Página própria para MP4 e MP3, com um link de vídeo ou expansão de playlist/canal em lote. |
| Retomar depois de uma interrupção | Catálogo persistente, checkpoints e conferência dos arquivos existentes. |
| Acompanhar o acervo ao longo do tempo | Totais disponíveis e resumos da semana e do mês, sem contar cópias como novos conteúdos. |

O serviço tem capacidade para processar **até três canais em paralelo**. Conteúdo indisponível, limitações da plataforma e condições da conexão podem reduzir o ritmo. O aplicativo distingue um levantamento parcial de uma contagem concluída.

## Como funciona

1. **Adicione suas fontes.** Novos canais entram em uma fila pausada. YouTube e Instagram aparecem separados.
2. **Consulte as novidades.** Atualizar o levantamento identifica conteúdos e verifica o que está disponível no acervo, sem liberar uma nova fila de downloads.
3. **Escolha o escopo.** No YouTube, selecione todos os conteúdos ou categorias como vídeos, lives e shorts. As opções do Instagram dependem do acesso permitido.
4. **Dê play.** Libere um canal, uma seleção ou todos. A fila distribui o trabalho entre as vagas disponíveis.
5. **Consulte e continue depois.** Abra os TXT, encontre os arquivos na pasta escolhida e retome a rotina em outra ocasião.

Os downloads são iniciados por você. Depois do início, o serviço local cuida do lote e das retomadas; fechar a janela não equivale a pausar. Suspender ou desligar o computador interrompe a execução.

### Transcrições e uso de espaço

No YouTube, o fluxo atual procura **legendas disponíveis**, sem baixar o vídeo completo para gerar o TXT. Conteúdos sem legendas podem permanecer sem transcrição.

No Mac, o reconhecimento local de voz para Instagram é opcional e exige configuração de um modelo. Ele usa áudio temporário e processamento no computador. A instalação básica não baixa modelos de IA. Transcrição em nuvem não está integrada.

O download de vídeo ou música é uma operação separada. Você escolhe MP4 ou MP3 quando quer guardar a mídia.

### Pastas compreensíveis

Exemplo fictício de organização:

```text
Pasta escolhida/
└── Canal de exemplo/
    ├── transcricoes/
    │   └── AAAA-MM/
    │       └── Conteúdo de exemplo.txt
    ├── videos/
    │   └── AAAA-MM/
    └── musicas/
        └── AAAA-MM/
```

Os atalhos e as cópias de consulta são separados dos objetos internos verificados pelo aplicativo. Alterar a pasta de exportação preserva o acervo interno e os arquivos já existentes.

## Privacidade desde a instalação

- **Acervo inicial vazio:** nenhuma lista pessoal de canais, conta ou interesse acompanha o código.
- **Dados locais:** catálogo, transcrições, arquivos, modelos e sessões da instalação ficam fora do repositório público.
- **Sem envio automático do acervo ao projeto:** não há uma conta central do Memoraio nem coleta de bibliotecas dos usuários implementada no aplicativo.
- **Conexões com finalidade definida:** consultar ou baixar conteúdo envolve a plataforma de origem; instalar dependências e modelos opcionais envolve seus distribuidores.
- **Demonstrações fictícias:** a ilustração e os exemplos desta apresentação não usam arquivos nem estatísticas de uma instalação pessoal.

Para colaborar, use catálogos temporários e dados sintéticos. Nunca publique cookies, tokens, listas de canais pessoais, transcrições reais ou capturas da sua biblioteca. Leia a [política de privacidade da contribuição](docs/privacy.md) e as [orientações de segurança](SECURITY.md).

## Instalação

| Plataforma | Situação atual | Caminho de instalação |
|---|---|---|
| **macOS Apple Silicon** | Interface nativa AppKit/WebKit; instalação pessoal com motor, ambiente e dados fora da pasta do código. | [Guia do Mac](docs/installation.md) · `Instalar.command` |
| **Windows com WSL 2** | Prévia experimental; motor Linux e interface no navegador. Ainda precisa de validação completa em um PC Windows. | [Guia do Windows](docs/windows.md) · `windows/Instalar.cmd` |

Python, FFmpeg, Node e outras dependências precisam estar disponíveis conforme o guia da plataforma. O aplicativo nativo sozinho não contém todo o motor. A distribuição pública ainda não oferece um instalador nativo Windows nem um pacote macOS notarizado para distribuição ampla.

## Vamos construir juntos

O código está aberto porque organizar memória audiovisual pode ser útil a muitas pessoas, com fontes e necessidades diferentes. Queremos evoluir a experiência com contribuições que tornem o programa mais claro, confiável e fácil de instalar.

Comece pelo [guia de contribuição em português e inglês](CONTRIBUTING.md), pelas [cinco tarefas iniciais](docs/community/START-HERE.md) ou pelo [roadmap colaborativo](docs/ROADMAP.md). Também há um [kit de divulgação](docs/community/OUTREACH.md) pronto para adaptar às regras de cada comunidade.

As frentes prioritárias são:

- **Instalação e distribuição:** simplificar a primeira utilização e avançar uma edição Windows nativa.
- **Confiabilidade:** ampliar testes de retomada, integridade, interrupções e filas.
- **Experiência de uso:** melhorar acessibilidade, controles, estimativas e leitura do andamento.
- **Compatibilidade:** testar as plataformas e documentar com precisão o que funciona e o que exige acesso adicional.
- **Consulta ao conhecimento:** explorar pesquisa e recursos locais de IA, preservando a distinção entre a fala original e uma interpretação gerada.

Abra uma [issue](../../issues) para relatar um problema ou propor uma melhoria. Para contribuir com código, consulte [CONTRIBUTING.md](CONTRIBUTING.md), apresente o comportamento esperado e inclua uma forma de verificar a mudança. Relatos devem usar exemplos fictícios ou material autorizado e devidamente anonimizado.

## Limites que queremos manter claros

O Memoraio não garante acesso a todo conteúdo de uma plataforma. Conteúdo público pode ter restrições de uso; stories, destaques e outros materiais protegidos dependem de uma sessão autorizada. O programa não contorna DRM nem controles de acesso. Funcionar com um conteúdo não certifica funcionamento com todos os conteúdos.

Checkpoints e verificação de integridade ajudam a recuperar interrupções; nenhum software é imune a qualquer falha. Backup do catálogo no mesmo disco não substitui backup externo do acervo.

A implementação também contém módulos experimentais de pesquisa local e simulação de licenciamento. Eles não representam um serviço comercial ativo nem alteram a instalação básica de downloads e legendas.

## Documentação

[Arquitetura](docs/architecture.md) · [Controles e organização](docs/manual-controls.md) · [Desenvolvimento](docs/development.md) · [Testes](docs/testing.md) · [Resiliência](docs/resilience.md) · [Distribuição](docs/distribution.md) · [Privacidade](docs/privacy.md) · [Licenças](docs/licenses.md)

O código original é distribuído sob a [licença MIT](LICENSE). Dependências, modelos, marcas e conteúdos de terceiros mantêm seus próprios direitos e licenças. Memoraio é o nome de trabalho do projeto.
