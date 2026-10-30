# Design system — Memória (nome de trabalho)

Referência instalada fora do projeto: Apple HIG Skill, release 2026-09-27, snapshot 2026-09-12. A skill é uma interpretação de terceiros; documentação Apple é a fonte primária. Não aplicada modalidade Duo nem enforce.

A orientação “Avoid custom window frames or controls” foi aplicada usando NSWindow e seus controles padrão. A orientação “Defer branding to content” fundamenta uma identidade discreta. Fonte: [Windows](https://developer.apple.com/design/human-interface-guidelines/windows), [Branding](https://developer.apple.com/design/human-interface-guidelines/branding).

Decisões próprias do produto: cor de acento verde, superfície neutra, escalas de espaço de 4/8/12/16/24/32, controles a partir de 32px, texto web 14px, títulos 18/28px. Essas medidas são escolhas do projeto, não exigências da Apple. Família de fontes do sistema. Tema segue a preferência do sistema; foco visível, movimento reduzido e contraste ampliado têm estilos dedicados. Estado é descrito por texto além da cor.

Biblioteca usa linhas legíveis, com seleção persistente entre páginas. Filtros e consulta de formatos revelam opções avançadas sem ocupar toda a vista inicial. Origem, revisão e histórico permanecem separados de qualquer interpretação da IA. Links de exportação correspondem a arquivos produzidos pelo servidor.

Aplicativo: janela redimensionável, comandos Arquivo/Editar/Visualizar/Tarefas/Janela/Ajuda, Command-W/H/Q, zoom de texto e modo de tela cheia padrão. Fechar janela e sair da interface mantêm o serviço; comando separado encerra tudo. Notificações pedidas somente por ação explícita. Ícone desenhado no projeto sem usar SF Symbols como marca.

Referências aplicáveis lidas: todas as 16 foundations, macOS, collections, generative-ai, playing-audio/video, e expansão única para lists-and-tables, image-views, menu bar, windows, toolbars, machine-learning, loading, airplay, live-viewing-apps e going-full-screen. Referências de outras plataformas foram lidas para respeitar o roteiro da skill; suas recomendações não foram atribuídas ao macOS.

Validação real de aparência, teclado e exportação ainda precisa constar em docs/validacao-v3.md antes de considerar a interface pronta. Não há certificação de acessibilidade nem teste em todos os dispositivos.
