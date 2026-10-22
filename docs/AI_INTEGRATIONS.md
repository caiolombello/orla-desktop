# IA opcional: APIs, planos e clientes locais

Revisão do plano: 11/10/2026. O documento abaixo continua sendo a proposta de longo prazo; uma fatia experimental de compatibilidade foi integrada ao fonte separado do launcher pelo PR [#20](https://github.com/caiolombello/orla-desktop/pull/20), com CI portátil [aprovada](https://github.com/caiolombello/orla-desktop/actions/runs/38115242191/job/114398735163) no run 38115242191. Isso não equivale à integração de um provedor de IA: nenhuma autenticação, elegibilidade de conta, inferência ou geração paga do Orla foi testada. A release 0.2.9 inclui no ZIP somente `scripts/ai.py` e `tests/test_ai.py`; launcher C++/QML, painel de IA e barra continuam excluídos. Isso é conteúdo-fonte auxiliar, não uma integração de IA publicada ou pronta. Revalidar documentação, termos e versões antes de implementar cada rota.

## Estado atual do fonte: compatibilidade A0.1 experimental

O checkout inclui um painel **IA** no launcher opcional. Todos os provedores continuam desligados. Abrir o painel não inicia processos; a ação explícita **Verificar clientes instalados** consulta uma lista fixa de CLIs e, separadamente, o botão com consentimento testa uma troca mínima do protocolo anônimo do Codex para uma versão reconhecida. A consulta e o teste de compatibilidade não recebem consulta de busca, prompt ou contexto de usuário; nessas ações não há geração, autenticação, reaproveitamento de sessão, armazenamento de credenciais ou handoff para terminal.

O helper reporta detecção/versão de Codex, Claude Code, OpenCode e LM Studio quando seus CLIs e formatos são reconhecidos. Ollama é somente presença: a versão não é consultada para evitar contato com um servidor. Esses estados não demonstram que uma conta, plano, API ou modelo possa ser usado. A1 ainda não foi concluída.

O painel está integrado ao repositório, mas não faz parte dos assets públicos 0.2.9 e 0.2.10; a experiência exige build separado do launcher. O ZIP inclui somente os helpers de detecção/teste e seus testes. O histórico abaixo continua sendo desenho futuro por rota, não evidência de integração de provedor. Veja a [validação Source delimitada](validation/ai-provider-source.md) para hashes, resultados, PR/CI e limitações.

### Fatia integrada nesta mudança Source: texto explícito via Ollama

Esta mudança Source integra a menor parte local da A1 somente para Ollama,
com validação delimitada da composição. A pessoa escolhe reescrever, resumir ou
traduzir, digita o texto, modelo, porta e idioma de destino quando aplicável e
seleciona `127.0.0.1` ou `::1`. A prévia revela destino, modelo, tarefa, dados e
**custo não informado** antes de um consentimento de sessão. Editar host, porta
ou modelo revoga o consentimento. Nada roda ao abrir, editar ou consentir;
somente **Gerar** inicia a chamada.

Em execução, todos os campos ficam travados e **Cancelar** permanece disponível.
O streaming aparece numa saída somente leitura, a parcial continua revisável e
a cópia exige **Copiar resultado**. Fechar o painel ou abrir Steam cancela
compatibilidade e texto. O fechamento solicitado pela UI e o atalho repetido
com a janela ativa esperam compatibilidade, texto e Steam drenarem antes de
prosseguir uma única vez. A nova tentativa limpa o resultado anterior antes
do preflight; chamadas ignoradas durante execução/fechamento o preservam.
Timeout mantém sua causa após a limpeza. Uso desconhecido continua desconhecido,
e uma resposta terminal rejeitada por custo inválido não publica tokens.
Ao voltar à busca, as quatro rotas QML de execução de resultado passam por uma
verificação comum dos três proprietários e de fechamento pendente, inclusive
callbacks que guardaram o ticket ao pressionar o botão. Os controles mostram
espera e se reabilitam após a limpeza; a busca continua editável. A falha de
limpeza notifica a interface ao mudar de estado, sem repetir polls idênticos,
e mantém a barreira ocupada até resolver o runtime.

A cadeia operacional usa processos próprios:

```text
painel IA -> AiTextController -> python -I -B ai_text_ollama.py run-ollama
          -> lifecycle T1/T2 -> conector HTTP Ollama numérico
```

O controller usa caminhos absolutos, cwd 0700 próprio e ambiente filho vazio.
O helper aceita somente Ollama numérico em loopback. T1/T2 continuam protegidos:
executar `ai_text.py` diretamente ainda retorna `unsupported_transport`, e o
adaptador HTTPS privado de OpenAI integrado historicamente pelo PR 34 segue sem
entrypoint, credenciais, seleção ou UI. Essa fatia não reutiliza a expressão
genérica “API na nuvem” para OpenAI.

O recorte exclui probe, descoberta, inicialização de servidor, download de
modelo, contexto padrão, leitura de clipboard, histórico, arquivos, tools,
autenticação, credenciais e API paga. Loopback identifica o destino da conexão,
não o processo que escuta nele: esse processo pode encaminhar o texto para a
rede. Por isso a interface não promete identidade Ollama, privacidade nem
processamento offline.

O plano R2, o shim, o controller R3 e a correção de UI têm revisão delimitada
favorável. A composição inicial passou build normal, seis CTests isolados e
90 testes Python (6 do shim, 23 T1 e 61 T2). Após as seis correções revisadas
do PR [#36](https://github.com/caiolombello/orla-desktop/pull/36), um build novo
e os seis CTests passaram com 24 entradas do controller e 18 da UI. As fixtures
cobriram a cadeia controller → helper → servidor HTTP Qt, streaming, cancelamento,
parcial, resultado anterior e a barreira do atalho com três proprietários.
Os dois jobs hospedados passaram em `1f59e0c`; em `2c8b750`, o portátil passou,
mas o processo da UI saiu com SIGSEGV depois das 17 entradas aprovadas. A causa
continua desconhecida. Os dois jobs passaram posteriormente em `57c2aa0`, com
os seis CTests reportados pelo job do launcher; a etapa GDB foi pulada. A captura
continua condicionada à falha, sem converter falha original em sucesso ou provar
correção do SIGSEGV.

As duas correções seguintes de notificação da limpeza e execução na busca
passaram na composição exata: build novo, os seis CTests, 25 entradas do
controller e 27 da UI (24,75 s, limite preservado de 30 s). O novo teste Steam
teve seu controle obsoleto corrigido após diagnóstico; a ação de cópia é
observada somente no clipboard privado da plataforma offscreen.
Os dois jobs passaram também em `28c5ef4`, com os seis CTests hospedados em
74,04 s e a UI em 24,27 s; o log de sucesso não imprime os contadores Qt filhos.

As duas correções seguintes notificam o estado final antes de `closeReady` e
mantêm um pedido de saída até a conclusão da limpeza, mesmo quando o atalho
repete um pedido de ocultação. A geração reentrante continua bloqueada durante
a notificação final. O caminho imediatamente pronto usa o mesmo fechamento;
a intenção é consumida antes de ocultar/sair, sem duplicação nem quit herdado.
A composição conjunta passou um build novo de 40 passos e os seis CTests
isolados em 75,925 s, com controller 27 e UI 27. A UI levou 24,60 s, dentro
do limite preservado de 30 s. A revisão do controller aprovou esse Source
com uma limitação preservada: um desafio QML cooperativo adicional exigiu
confirmação de cancelamento e observou cancelamento não confirmado, com causa
exata desconhecida. Os casos QML forced/timeout e os 27 testes normais passaram.
A revisão independente da saída passou os 27 testes normais e um desafio
adicional com os três helpers reais: o último controlador notificou todos
prontos com quit ainda pendente, o atalho efetivo fez o fechamento imediato
único e a prontidão posterior não duplicou ocultação/saída. O ciclo seguinte
sem quit também passou. A primeira fixture desse desafio pressupunha um
prazo Steam errado e falhou antes da verificação causal; ficou preservada.
A fixture corrigida alterou apenas o prazo de teste exposto, em build novo.
A correção seguinte mantém o uso de tokens privado até a resposta completa,
saída normal zero e limpeza confirmada. Dados extras, saída com erro,
cancelamento ou timeout não publicam metadados rejeitados; o texto parcial
continua revisável. Sete regressões com helpers reais e retries passaram,
após falharem causalmente no código anterior. A revisão independente passou
34 entradas do controller e um desafio adicional de cinco entradas com saída
padrão fechada e processo ainda vivo, incluindo uso desconhecido e fechamento.
A composição do código passou build novo de 40 passos e os seis CTests uma vez
em 78,502 s, com controller 34 e UI 27 (24,508 s, limite de 30 s).
Os dois jobs hospedados passaram em `8d137cf`, com os seis CTests em 78,72 s.
A build local desse commit passou os seis em 79,47 s, mas não foi instalada
antes de dois novos comentários de revisão. A correção seguinte preserva a
primeira falha observada quando cancelamento ou fechamento começam depois dela
e drena stdout sem interpretar eventos após o primeiro erro de protocolo.
O cancelamento anterior à falha permanece cancelamento; o parcial aceito antes
do erro continua revisável. Dezessete regressões com helpers reais e retries
foram adicionadas: quinze falharam causalmente na base, com dois controles
pré-início aprovados. A composição final passou build novo de 40 passos e os
seis CTests uma vez em 81,147 s: controller 51 e UI 27 (24,663 s, limite 30 s).
A revisão independente passou controller 51 e um desafio QML de quatro
entradas. O setup inicial falhou antes dos helpers e seus oráculos causais
ficaram UNRUN; o trace serializado null não comprova ordem temporal.
Em `5aaf518`, CI run 38175193804 aprovou o job portátil, mas behavior saiu
com SIGSEGV após 7 PASS/0 FAIL/1 skip esperado; os outros cinco CTests passaram.
A causa continua UNKNOWN. Um único GDB local saiu zero sem reproduzir o crash.
O diagnóstico hospedado agora seleciona apenas behavior ou UI, nessa prioridade,
sem alterar a falha original nem os limites. Isso não é uma correção do crash;
CI desta revisão e integração na branch principal continuam pendentes.
O canary local desse Source foi instalado reversivelmente após build permanente
ALL40/seis CTests em 80,85 s. Atalho, retorno de foco, painel de IA, Tab com
rolagem, popup de tarefa, calculadora, saída limpa e reinício passaram no KDE.
Não foi executada descoberta ou geração real de IA. Ollama e modelo reais,
qualidade semântica, clipboard e acessibilidade nativos, matriz de telas,
empacotamento relocável, distribuição/release e admissão completa continuam
abertos. A1 permanece aberta: o roadmap completo ainda exige também o backend
API opt-in e os demais gates publicados.

A revisão posterior preserva o erro original após recuperar a limpeza, bloqueia
novos trabalhos IA/Steam enquanto o fechamento está pendente e mantém
cancelamento/timeout quando o sinal interrompe a publicação. A composição local
passou ALL40, seis CTests em 83,64 s (UI 30 dentro de 30 s; controller 53) e 93 testes
Python. O SIGSEGV após Totals do desafio dirigido continua UNKNOWN: um GDB não
reproduziu e a suíte completa aprovada não explica a falha. CI/merge da nova
revisão estão pendentes; a instalação local continua no canary `5aaf518`.

A revisão seguinte valida eventos de falha somente após EOF limpo e saída normal
zero do helper. Eventos extras, bytes sem terminador e saída não zero preservam
`invalid_helper_response`; o primeiro cancelamento explícito continua registrando
a causa já observada. O launcher passa a abrir em 660×420, com entradas IA/Steam
de pelo menos 40×40 e conteúdo IA contido na largura disponível, incluindo versões
longas. A combinação passou build novo ALL40 e os seis CTests uma vez em 84,38 s:
UI 32/26,588 s Qt (limite 30 s) e controller 57/12,621 s Qt (limite 40 s).
Os 93 testes Python aprovados na revisão anterior não foram repetidos porque seus
arquivos permaneceram iguais. Revisões independentes aprovaram cada mudança de
código. CI/merge desta combinação e os testes do layout compacto no KDE permanecem
pendentes; a instalação local ainda está no canary `5aaf518`, e as causas dos
crashes históricos continuam UNKNOWN.

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


A revisão mais recente mantém cancelamento/timeout durante a publicação de
`started` e apresenta mensagens fixas de recuperação para todos os códigos de
falha aceitos. Dois revisores independentes aprovaram os escopos; a composição
passou build novo de 40 passos, seis CTests (90,697s) e 116 testes Python. A fixture cobre a
escrita completa antes do retorno do sink; não promete entrega/ACK ou escrita
parcial atômica. CI da revisão, atualização do canary `5aaf518`, provedores reais e
admissão completa seguem pendentes. Veja o registro de validação de IA.
