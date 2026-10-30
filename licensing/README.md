# Licenciamento opcional — somente simulador

Este módulo não cria Pix real, não contém segredos e não é iniciado pelo aplicativo. Não conectar a produção sem concluir a homologação descrita em docs/viabilidade-comercial-v3.md.

Instale requirements-licensing.lock.txt no ambiente de desenvolvimento e execute os testes. O Ledger recebe um provedor simulado, relógio, segredo e chave Ed25519 por injeção. Essa separação permite testar falhas e não distribuir segredos no cliente. Banco de licenças deve ser separado de data/catalog.sqlite3.

O serviço real ainda precisa de autenticação de contas, TLS, segredo/chave geridos, outbox/inbox persistentes, limites de requisição, conciliação agendada, fluxos de suporte/reembolso e revisão jurídica. Não considerar este protótipo um serviço de pagamento pronto para produção.
