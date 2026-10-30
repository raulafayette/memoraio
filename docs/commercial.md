# Viabilidade comercial e Pix — 29/10/2026

## Decisão atual

Não ativar cobrança por extração irrestrita de YouTube/Instagram. Presença pública e capacidade técnica do extrator não concedem autorização contratual ou autoral. O protótipo comercial limita-se a ferramentas para mídia própria ou devidamente autorizada e permanece em **simulação local**. Não houve cobrança, registro de conta de pagamento ou envio de biblioteca.

Os termos do YouTube restringem download/reprodução e acesso automatizado, salvo hipóteses expressamente autorizadas ou permissão prévia adequada. Isso impede tratar um downloader comercial genérico como fluxo aprovado. A API oficial e a licença de conteúdo também precisam ser avaliadas separadamente: autorização de um autor não é automaticamente autorização da plataforma. [Termos YouTube](https://br.youtube.com/t/terms).

A Meta distingue coleta automatizada autorizada de coleta contrária aos seus termos e relata medidas contra scraping contratado. O acesso direto aos termos do Instagram retornou 429 nesta pesquisa; não foram feitas tentativas para contornar o bloqueio. A ausência de acesso à página não deve ser interpretada como autorização. [Meta: scraping](https://about.fb.com/news/2021/05/scraping-by-the-numbers/amp/), [ações contra scraping contratado](https://about.fb.com/news/2022/07/actions-against-scraping-for-hire/).

A Lei 9.610/1998 atribui ao titular direitos patrimoniais e exige autorização para várias formas de reprodução e arquivamento, sujeitas às limitações legais. Não foi presumida uma exceção geral para transcrever integralmente qualquer conteúdo público ou revendê-lo. Revisão jurídica específica deve considerar o uso, a licença e a forma de obtenção. [Lei atualizada, Câmara](https://www2.camara.leg.br/legin/fed/lei/1998/lei-9610-19-fevereiro-1998-365399-normaatualizada-pl.html).

LGPD: definir finalidade, base legal, papéis, retenção, canal do titular, segurança e eventual transferência. Transcrições podem conter dados pessoais e sensíveis; processamento local reduz exposição, sem criar automaticamente isenção. Licenciamento deve receber só identidade mínima da conta/instalação e dados necessários à cobrança, não falas ou vídeos. [LGPD atualizada](https://www2.camara.leg.br/legin/fed/lei/2018/lei-13709-14-agosto-2018-787077-normaatualizada-pl.html).

Consumidor: o art. 49 do CDC prevê arrependimento em sete dias em contratações fora do estabelecimento. Uma licença de 48h não elimina, por si só, esse direito. Antes de lançar, definir oferta clara, fornecedor, preço total, duração, suporte, cancelamento, restituição e documentos fiscais com orientação profissional. [CDC, portal oficial](https://consumidor.gov.br/pages/conteudo/publico/102).

## Provedores

| Critério | Mercado Pago | Asaas |
|---|---|---|
| Tarifa pública observada | Pix de checkout/link: 0,99%, conforme produto e contrato | QR dinâmico/fatura: R$0,99 nos três primeiros meses, depois R$1,99; condições da conta prevalecem |
| Confirmação | Webhook e consulta autenticada de payment/order | Webhook e consulta autenticada de cobrança |
| Autenticidade | SDK oficial de validação de x-signature; exceções por produto precisam ser respeitadas | authToken do webhook em asaas-access-token; segredo armazenado no backend |
| Testes | Contas/credenciais e notificações de teste; suporte Pix depende do fluxo | Ambiente api-sandbox.asaas.com/v3 e simulações; diferenças de produção documentadas |
| Estorno | Fluxo de refunds do produto escolhido e conciliação do estado posterior | Fluxo de estorno e estados da cobrança; simular a sequência completa |
| Operação | Eventos podem ser reenviados; persistir antes de confirmar recebimento e consultar recurso | Eventos podem ser reenviados ou chegar fora de ordem conforme configuração; idempotência necessária |

Taxas são observações datadas, não cotações para esta conta. “Pagamento instantâneo” não é SLA da nossa liberação: depende de rede, provedor, webhook, consulta e banco. Prever estado pendente visível e conciliação de eventos perdidos. Reembolso operacional não deve depender só da expiração da licença.

Fontes: [taxas Mercado Pago](https://www.mercadopago.com.br/ferramentas-para-vender/link-de-pagamento?code=POINT_ORG_LEGACY&device=62), [taxas Asaas](https://www.asaas.com/pix-asaas), [webhooks Mercado Pago](https://www.mercadopago.com.br/developers/pt/docs/your-integrations/notifications/webhooks), [criação de webhook Asaas](https://docs.asaas.com/reference/criar-novo-webhook), [sandbox Asaas](https://docs.asaas.com/docs/sandbox), [limitações sandbox](https://docs.asaas.com/docs/faq-sandbox).

## Hipóteses e custos

Gratuito: até 10 conteúdos distintos por dia, com operações combinadas contando uma vez. Temporário: 48h contadas da confirmação pelo backend. O protótipo usa dia UTC e preço fictício de R$19,90; nenhum dos dois foi aprovado como oferta comercial.

Nesse preço hipotético, antes de impostos, atendimento, reembolsos e operação, 0,99% representa aproximadamente R$0,20; uma tarifa de R$1,99 representa 10% do preço. A vantagem de processamento local é evitar custo de GPU por minuto no servidor. Medir conversão, suporte, duração dos conteúdos, consumo de armazenamento e cancelamentos antes de escolher preço ou plano. Não há validação de demanda nem projeção de lucro nesta entrega.

## Arquitetura implementada e limites

`licensing/ledger.py` é separado do motor e do catálogo. Registra pedidos, instalação, confirmação, expiração, uso diário, eventos e auditoria em outro banco. Tokens de sessão são guardados como hash. Licenças usam Ed25519 e vinculam conta/instalação/expiração; chave privada não pertence ao aplicativo.

O webhook simulado autentica HMAC e horário, ignora o status alegado pelo cliente e consulta o provedor simulado. Confere referência, valor, moeda e ambiente. Duplicatas não estendem acesso. Reembolso revoga novos direitos; expiração volta ao gratuito. Não há QR Pix válido: o identificador de teste é deliberadamente não pagável. Testes cobrem esses casos.

Não confundir esse simulador com homologação bancária. O código recusa provedor externo. A próxima integração real deverá persistir pedido/outbox antes da chamada externa, usar idempotência do provedor, reconciliar falhas, validar notificações com o mecanismo oficial e homologar criação, QR, aprovação, reenvio, estorno e indisponibilidade. Credenciais, conta sandbox e URL HTTPS controlada ainda não foram fornecidas. Nenhum botão de pagamento foi ativado no aplicativo pessoal.

## Software aberto e sustentabilidade

| Modelo | Vantagem | Limite |
|---|---|---|
| Aberto + serviços pagos | Colaboração ampla; cobra suporte, backup opcional, atualizações assinadas e gestão | Precisa de serviço que entregue valor; código local pode ser modificado |
| Open core | Diferencia recursos comerciais | Mais complexidade de licença, contribuição e fronteira de funcionalidades |
| Aplicativo aberto + backend separado | Isola segredos e pagamento; mantém processamento privado | Backend precisa de autenticação e operação contínua |
| Conveniência/distribuição paga | Instalação, assinatura, suporte e atualizações têm valor | Forks e distribuição própria continuam possíveis conforme a licença |

Escolha de trabalho: código original aberto sob MIT e serviços opcionais separados. A licença permite uso comercial e forks; não é compatível prometer exclusividade absoluta do limite de 10 vídeos ou impedir que um fork altere o cliente. O backend protege seus próprios serviços, confirmações e chaves; não controla de modo absoluto o computador do usuário. Arquivos já exportados permanecem do usuário após expiração/revogação.

Para ativação comercial faltam: avaliação jurídica do fluxo concreto, fornecedor/tributação/atendimento, conta e homologação sandbox, política de privacidade/retenção e oferta aprovada. Esses são impedimentos reais de lançamento; não bloqueiam a evolução local do acervo.
