# Privacidade e conteúdo público

O repositório distribui código e documentação. Bibliotecas pessoais pertencem à instalação de cada usuário e não fazem parte do projeto público.

## O que pode entrar no repositório

Código-fonte revisado, documentação genérica, ilustrações conceituais, configurações sem valores secretos e testes que geram seus próprios dados fictícios. Avisos de licença e atribuições legítimas de dependências devem ser preservados.

## O que deve ficar fora

Listas pessoais de canais ou perfis; nomes, links e identificadores associados a uma biblioteca real; vídeos, áudios e transcrições reais; catálogos e cópias de segurança; sessões e cookies; tokens, chaves e credenciais; logs de uso; modelos e ambientes instalados; caminhos de usuário; capturas da biblioteca; exportações da conversa de desenvolvimento.

Uma imagem de demonstração precisa ser produzida com uma instalação temporária e fontes fictícias. Remova também títulos, contagens, pastas, nomes de usuário e endereços que possam revelar a instalação usada.

## Antes de publicar

1. Gere uma cópia somente do código e da documentação revisados. Não copie o histórico de um projeto pessoal.
2. Execute `python scripts/audit_public.py . --tracked --history` no repositório de publicação.
3. Revise as alterações, os arquivos ocultos, os links, as imagens e os metadados de autoria. Use um endereço `noreply` nos commits. O perfil proprietário do repositório continua visível no GitHub.
4. Compare localmente a exportação com as fontes e identificadores privados, quando houver. A lista usada para essa comparação não deve ser copiada para o repositório nem impressa nos logs públicos.
5. Confira os logs e artefatos de CI. Os testes devem usar somente diretórios temporários e dados sintéticos.

A auditoria automática identifica classes de arquivos e padrões conhecidos; ela não prova a ausência de toda informação pessoal possível. Revisão humana e controle do que é enviado continuam necessários.

## Conexões do aplicativo

A interface utiliza um serviço HTTP autenticado em `127.0.0.1`, no próprio computador. Consultas e downloads fazem conexão com os provedores de conteúdo. Dependências e modelos opcionais são obtidos dos seus distribuidores. Não há sincronização automática do acervo com o GitHub ou com uma conta central do projeto.

O login opcional do Instagram acontece no site oficial, em uma janela local. Uma sessão autorizada continua sendo informação sensível e não deve acompanhar relatórios de erro.

## Relatos de problema

Descreva os passos com nomes e links fictícios sempre que possível. Compartilhe apenas trechos de log estritamente necessários e revisados. Não anexe um catálogo inteiro para demonstrar um erro. Para vulnerabilidades, siga [SECURITY.md](../SECURITY.md).
