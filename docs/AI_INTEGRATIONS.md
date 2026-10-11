# IA opcional: APIs, planos e clientes locais

Revisão do plano: 11/10/2026. O documento abaixo continua sendo a proposta de longo prazo; uma fatia experimental de compatibilidade foi integrada ao fonte separado do launcher pelo PR [#20](https://github.com/caiolombello/orla-desktop/pull/20), com CI portátil [aprovada](https://github.com/caiolombello/orla-desktop/actions/runs/38115242191/job/114398735163) no run 38115242191. Isso não equivale à integração de um provedor de IA: nenhuma autenticação, elegibilidade de conta, inferência ou geração paga do Orla foi testada. As releases públicas 0.2.5–0.2.8 continuam sem o launcher/IA. Revalidar documentação, termos e versões antes de implementar cada rota.

## Estado atual do fonte: compatibilidade A0.1 experimental

O checkout inclui um painel **IA** no launcher opcional. Todos os provedores continuam desligados. Abrir o painel não inicia processos; a ação explícita **Verificar clientes instalados** consulta uma lista fixa de CLIs e, separadamente, o botão com consentimento testa uma troca mínima do protocolo anônimo do Codex para uma versão reconhecida. A consulta e o teste não recebem consulta de busca, prompt ou contexto de usuário; não há geração, autenticação, reaproveitamento de sessão, armazenamento de credenciais ou handoff para terminal.

O helper reporta detecção/versão de Codex, Claude Code, OpenCode e LM Studio quando seus CLIs e formatos são reconhecidos. Ollama é somente presença: a versão não é consultada para evitar contato com um servidor. Esses estados não demonstram que uma conta, plano, API ou modelo possa ser usado. A1 (texto escolhido enviado a um backend autorizado) não começou.

O painel está integrado ao repositório, mas não faz parte dos assets públicos 0.2.8; a experiência exige build separado do launcher. O histórico abaixo continua sendo desenho futuro por rota, não evidência de integração de provedor. Veja a [validação Source delimitada](validation/ai-provider-source.md) para hashes, resultados, PR/CI e limitações.

## Resultado esperado

Usar o provedor que a pessoa já prefere, dentro do launcher e das ações do Orla, com entrada inspecionável, cancelamento e controle do contexto. O desktop funciona integralmente sem IA. O primeiro caso de uso é transformar um texto que a pessoa escolheu: resumir, traduzir ou reescrever e revisar antes de copiar. Agenda, projetos e ações do sistema entram depois de contratos de permissão testados.

Separar três conceitos nas preferências: **provedor/modelo**, **cliente de execução** e **forma de acesso/cobrança**. Codex CLI, Claude Code e OpenCode são clientes; instalar um cliente ou possuir assinatura não comprova que qualquer API está autorizada. Orla não oferece uma assinatura própria de IA nesta proposta.

## Caminhos propostos por integração

| Caminho | Uso no Orla | Condição e limite |
|---|---|---|
| OpenAI API | Respostas integradas com chave fornecida pelo usuário | Conta, permissões, modelos e cobrança de API próprios; separar do modo ChatGPT |
| Sign in with ChatGPT — SIWC | Respostas integradas usando plano elegível pelo fluxo oficial para app open source | Cadastro/autorização próprios do Orla, limites do plano e regras de preview; elegibilidade real ainda não comprovada |
| Codex app-server | Cliente local para sessões, respostas e aprovações documentadas | Adaptador por versão; protocolo experimental e ferramentas inicialmente desativadas |
| Anthropic API / nuvem suportada | Respostas integradas mediante credencial autorizada do usuário | API ou provedor de nuvem; assinatura Claude não habilita login embutido no Orla |
| Claude Code original | Ação “Abrir projeto no Claude Code” em terminal | Usuário opera e autentica o binário oficial; Orla não captura sessão nem transforma assinatura em backend de chat |
| OpenCode | Conectar ao servidor local documentado do usuário ou abrir sua TUI | Autenticação do servidor e versão verificadas; cada provedor mantém seus próprios requisitos |
| Ollama / LM Studio | Inferência em servidor/modelo local configurado pelo usuário | Compatibilidade e capacidades conferidas; endpoint local não prova que o modelo não usa nuvem |
| Outros provedores | Adaptadores adicionais de API ou cliente oficialmente integrável | Mesmos contratos, testes e regras de privacidade; sem fallback automático para outro destino |

### OpenAI e Codex

A documentação atual oferece uso do plano ChatGPT em clientes open source pelo SIWC, com autorização de inferência separada da identidade. A implementação proposta deve usar esse fluxo registrado para o Orla, sem importar credenciais do Codex ou sessões do navegador. A conexão não traz histórico de conversas do ChatGPT. Planos e usuários elegíveis estão sujeitos às condições vigentes. [SIWC quickstart](https://developers.openai.com/siwc/quickstart)

Antes de liberar: provar registro, callback e PKCE, validação de identidade quando aplicável, consentimento, renovação, armazenamento local e revogação. Listar um modelo não comprova direito de uso: testar uma requisição autorizada pela pessoa e tratar inelegibilidade como estado próprio. A rota API com chave continua separada. [Registro e sign-in open source](https://developers.openai.com/siwc/token-sharing-open-source/sign-in), [API quickstart](https://developers.openai.com/api/docs/quickstart)

O preview tem um contrato próprio: Responses com streaming e `store:false`, histórico fornecido pelo cliente e limitações de parâmetros/ferramentas. Não anunciar paridade com a API geral, memória de ChatGPT, computer use ou conectores hospedados. Renovação de token e recuperação da sessão precisam de testes específicos no caminho app-server. [Limitações do preview](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations), [Codex app-server com SIWC](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)

O Codex instalado nesta inspeção é `codex-cli 0.162.1`; `codex app-server --help` marca o recurso como experimental. A consulta foi somente a versão/ajuda. Preferir stdio com processo de propriedade do adaptador, negociar versão e limitar cwd, ferramentas e aprovações. Não expor um socket global sem autenticação. A implementação ainda deve provar compatibilidade e encerramento sem interferir nas sessões do usuário.

**Monetização:** acesso ao plano por SIWC precisa permanecer gratuito, com tokens sob controle local do usuário, sem revender ou compartilhar cotas e sem uso disparado por outras pessoas. Temas pagos independentes não devem condicionar esse acesso. A elegibilidade de addons comerciais que envolvam SIWC segue não confirmada e precisa ser resolvida antes de ofertá-los. [Termos SIWC](https://openai.com/policies/sign-in-with-chatgpt-terms/)

### Claude e OpenCode

As regras atuais da Anthropic orientam aplicações de terceiros para API/nuvem autorizada e não permitem oferecer login Claude.ai ou encaminhar pedidos pela assinatura do usuário. Permitem que a pessoa entre no Claude Code original. Por isso, o primeiro caminho por assinatura é abrir o cliente oficial no projeto escolhido; o chat integrado usa API. Não colher tokens nem embrulhar a sessão Pro/Max para contornar essa fronteira. [Autenticação e uso de credenciais](https://code.claude.com/docs/en/legal-and-compliance#authentication-and-credential-use), [Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview)

OpenCode documenta servidor HTTP, OpenAPI e SDK. Conectar apenas ao endpoint que o usuário selecionou, em loopback por padrão, protegido por autenticação; informar diretório/sessão e permissões antes de enviar. Não descobrir e controlar automaticamente todas as sessões existentes. Um servidor acessível não concede acesso ao provedor subjacente: conferir a rota e os termos desse provedor. [Servidor](https://docs.opencode.ai/docs/server/), [SDK](https://docs.opencode.ai/docs/sdk/), [Provedores](https://docs.opencode.ai/docs/providers/)

### Modelos locais

Ollama implementa um subconjunto de APIs compatíveis com OpenAI; LM Studio oferece servidor local. Criar adaptadores com matriz de versão/modelo/capacidade e verificar streaming, cancelamento e ferramenta suportada. Mostrar o destino real, inclusive quando um servidor local encaminha para nuvem. Não baixar modelos grandes, iniciar serviços nem publicar portas durante a instalação do dock. [Compatibilidade Ollama](https://docs.ollama.com/api/openai-compatibility), [Servidor LM Studio](https://lmstudio.ai/docs/developer/core/server)

## Contrato interno proposto

Começar experimental, sem afirmar SDK pronto. Adaptadores internos usam o mesmo contrato; provedores de terceiros só são aceitos após os gates X5 de [EXTENSIONS.md](EXTENSIONS.md).

| Operação / evento proposto | Comportamento esperado |
|---|---|
| `discover` / `capabilities` | Disponibilidade, versão, modelo e capacidades; sem iniciar geração ou revelar segredo |
| `connect` / `disconnect` | Fluxo suportado pelo fornecedor; estado de autorização, renovação e exclusão local |
| `generate` | ID da requisição, entrada/contexto aprovados, destino/modelo, modo de acesso e limites aplicáveis |
| `delta` / `completed` / `failed` | Resposta incremental, resultado final ou erro tipado; somente a requisição ativa altera sua UI |
| `cancel` | Interromper trabalho pendente; distinguir cancelamento confirmado de desconexão/incerteza |
| `usage` | Uso reportado, estimado ou desconhecido; nunca inventar dólares, quota ou horário de reset |
| `approvalRequired` | Efeito, argumentos e escopo de uma ferramenta; negar não executa a operação |

Erros tipados: cliente ausente, versão incompatível, autenticação expirada, plano inelegível, modelo indisponível, limite, rede, timeout, permissão negada e falha do processo. Separar tentar novamente de continuar uma sessão; pedidos mutantes não são repetidos silenciosamente. A negociação expõe capacidades reais: texto, imagens, ferramentas, streaming, cancelamento e relato de uso. Desabilitar o que a rota não oferece.

O broker guarda segredos no cofre disponível no sistema, mantendo-os fora de QML, manifesto, exportação, argumentos de processo, logs e pacote de extensão. Se não houver armazenamento seguro, oferecer sessão sem persistência ou explicar a dependência; não gravar tokens em texto puro. Para SIWC, persistência permanece local. Para clientes externos, a autenticação do próprio cliente continua sob seu controle.

## UX e confiança

1. Escolher a tarefa, editar o texto e anexar contexto deliberadamente. Não ler clipboard, arquivos, títulos de janela ou agenda em segundo plano como contexto implícito.
2. Ver provedor, modelo, endpoint/modo, dados enviados e custo estimado quando disponível. Mostrar “custo não informado” e quotas sem conversão monetária indevida.
3. Executar, acompanhar streaming e cancelar. Preservar rascunho/resposta parcial e avisar quando cancelamento não garante ausência de cobrança ou reversão de uma ação.
4. Revisar e copiar, editar ou descartar. Resultados só afetam o desktop por ação explícita; texto gerado não é comando automaticamente autorizado.
5. Desconectar, revogar permissões e apagar dados locais. Informar separadamente a revogação disponível no provedor; exclusão local não promete apagar histórico remoto.

Começar com **texto escolhido → sugestão → cópia deliberada**, sem ferramentas. Depois: explicar uma leitura selecionada de quota, rascunhar resumo de agenda escolhida e abrir projeto no cliente oficial. Conteúdo de arquivos, calendário, resultados e extensões permanece dado, não autoridade para aumentar permissões. Segredos e `.env` não entram em contexto automático.

Ferramentas futuras usam comandos L1/L3, com validação pelo host e aprovação do efeito. A integração não bypassa aprovações do cliente local nem delega acesso amplo ao desktop por padrão. MCP local pode ser estudado depois: transporte e declaração de tool não oferecem isolamento; não confundir com suporte a MCP hospedado no SIWC. Ficam fora do primeiro MVP voz, computer use, execução autônoma e automações de background.

## Etapas e critérios de saída

| ID | Entrega proposta | Dependências e aceite |
|---|---|---|
| **A0 — fundação, 0.3–0.4** | Contrato, cofre, estados UX e provas de integração sem dados pessoais | Provedores simulados; nenhum pedido pago no CI; decisões de auth/termos registradas; UI cancelável |
| **A1 — MVP, 0.5** | Texto explícito com um backend local e um backend API opt-in | A0, L2; streaming/cancelamento/timeout e erros aprovados; instalação sem IA continua normal |
| **A2 — ChatGPT/Codex, 0.5–0.6** | SIWC oficial e adaptador app-server por versão | A0/A1; elegibilidade e ciclo completo de autorização/renovação/revogação provados; sem paywall para usar plano |
| **A3 — APIs adicionais, 0.6–0.7** | Anthropic API e outros backends justificados pelo uso | A1; matriz de capacidades, cobrança/modo claro e testes de contrato; sem conversão de assinatura em API |
| **A4 — clientes locais, 0.6–0.7** | Servidor OpenCode autenticado e abrir Claude Code original | A0, ações L1/L3; respeitar cwd, versão, permissões e sessões do usuário; iniciar somente por gesto explícito |
| **A5 — contexto e ações, 0.7–0.9** | Agenda/projeto selecionados e ferramentas limitadas | G1/I1/L3 quando usados; prévia de contexto; efeitos aprovados e falhas/repetição qualificados |
| **A6 — extensões de IA, após X5** | Provedores comunitários pelo host de extensões | Isolamento, credenciais mediadas, atualização/revogação e compatibilidade testados; revisar termos por rota |

As versões são janelas de planejamento, sem datas prometidas. Adaptadores internos não dependem de lançar plugins executáveis. A2/A3/A4 podem avançar em paralelo depois de A0/A1; nenhum bloqueia o dock ou a beta se precisar de mais qualificação. O caminho Claude Code em terminal pode ser entregue antes do chat integrado.

## Verificação necessária

- CI sem chave/API paga: fixtures de streaming, eventos fora de ordem, erro, processo morto, cancelamento, token expirado e negação de tool. Fixtures não contêm dados de conta nem prompts reais.
- Integração real separada, explicitamente iniciada pelo usuário: autenticação, primeira resposta, cancelamento e desconexão, com versão/modelo/rota registrados e logs redigidos. Mock verde não valida elegibilidade ou faturamento.
- Provar ausência de segredo em exportação, argv, logs, screenshots de diagnóstico e pacote; teste de cofre ausente/bloqueado.
- Provar que provedor desligado, rede ausente ou limite atingido afetam somente IA. Nenhuma troca automática para outro provedor ou chave.
- Provar que dados externos e resultado do modelo não executam ações nem elevam acesso; permissões negadas/revogadas impedem chamadas ao broker.

Esta especificação orienta a implementação. Não concede ao Orla acesso a qualquer conta, assinatura, token, ferramenta ou dado do usuário.
