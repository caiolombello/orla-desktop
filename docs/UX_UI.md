# UX, interface e extensões do Orla Desktop

Este documento detalha como o Orla pode crescer de um dock alpha para um espaço de trabalho modular do KDE. É uma especificação e uma proposta de sequência; recursos marcados como planejados ainda não fazem parte do Orla Dock 0.2.1 alpha. O produto atual oferece dock, três temas simples, controle de tamanho/animação, widgets opcionais, mídia MPRIS e leituras locais de integrações. A página e o código atuais são referências visuais; os fluxos abaixo não alegam implementação.

## Princípios de produto

- **Começar pelo trabalho do usuário:** abrir e alternar apps é a tarefa principal do dock; launcher, barra, notificações e IA são módulos opcionais, desligados até a pessoa escolhê-los.
- **KDE primeiro:** respeitar Plasma, atalhos, painel, serviços, foco, tema e convenções de teclado. A inspiração do macOS orienta a composição e a sensação de continuidade; Orla usa marca, ícones e linguagem visual próprios, sem marca Apple nem promessa de imitar APIs ou comportamentos privados.
- **Personalização segura:** pré-visualizar, guardar rascunho, aplicar, desfazer e exportar. Configurações e painéis não selecionados são preservados; substituir um painel exige escolha explícita e mantém recuperação do layout original.
- **Estados claros:** toda integração apresenta disponível, conectando, carregando, vazio, desatualizado, sem permissão, limitado, desconectado e erro quando esses estados se aplicam.
- **Aberto por padrão:** core útil sem conta, API paga ou catálogo central obrigatório; extensões têm capacidades explícitas e podem ser instaladas de fontes escolhidas pelo usuário.
- **Privacidade visível:** explicar de onde vem cada dado, quando ele sai do dispositivo, qual provedor o recebe e como desconectar/apagar configuração.

## Arquitetura de experiência

| Superfície | Tarefa principal | Navegação e saída |
|---|---|---|
| Dock | Abrir/focar apps, ver janelas e módulos rápidos | Menu contextual; configurações abrem no módulo certo; continua útil sem os demais |
| Barra superior opcional | Acessar menu do sistema/app ativo, status e Control Center | Cada grupo é módulo independente; ocultável pelo Plasma e configuração Orla |
| Launcher opcional | Encontrar apps, ações e comandos pelo teclado | Atalho configurável; setas/Enter executam seleção; Escape fecha e devolve foco |
| Central de Controle | Ver estado do sistema e fazer ajustes diretos | Painéis curtos com confirmação do estado real; erro oferece recuperação |
| Eventos | Consultar um aviso sem interromper a tarefa | Toast, HUD e ilha compacta escolhidos por tipo; Centro de Notificações do Plasma continua acessível |
| Preferências | Montar layout, módulos, perfis, acessibilidade e provedores | Busca de configuração; alterações temporárias até “Aplicar”; “Cancelar” restaura |

O setup pergunta o mínimo e não é um wizard obrigatório: escolher **Só dock**, **Dock + barra**, **Dock + launcher** ou **Montar depois** cria uma prévia. Presets são pontos de partida editáveis. Antes de aplicá-los, Orla descreve os painéis que criará; nunca apaga ou reposiciona painéis preexistentes sem ação separada explícita. Oferecer restauração em um clique.

## Sistema visual

Preservar a marca costeira existente e evoluí-la com tokens semânticos; os valores são ponto inicial de design, não substituem verificação de contraste nem o esquema Plasma.

Os tokens implementados, componentes e regras verificadas por `scripts/design.py` estão em [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md); a tabela abaixo registra a proposta original.

| Token | Base proposta | Uso |
|---|---|---|
| `ink` | `#111923` | Texto forte e superfícies escuras |
| `sea` | `#69D7C2` | Ação/seleção e destaque, acompanhado de forma/ícone |
| `paper` | `#F4F0E8` | Superfície clara e tema Papel |
| `surface` / `surface-raised` | Derivados do esquema ativo do Plasma | Painéis, popup, menus e campos |
| `text` / `text-muted` | Derivados do esquema ativo do Plasma | Hierarquia com contraste medido |
| `focus` / `danger` / `warning` / `success` | Derivados acessíveis do tema | Foco visível e estado com rótulo/ícone, nunca só cor |

Regras propostas:

- Utilizar componentes Qt Quick Controls/Kirigami e ícones do tema KDE quando isso melhora consistência; ícones de extensões precisam de fallback e não podem carregar recursos remotos na UI.
- Oferecer Vidro, Meia-noite, Papel e seguir o Plasma. Blur é aprimoramento progressivo: superfície opaca legível quando o compositor não oferece blur ou transparência.
- Layout, escala e densidade respondem a Plasma, DPI fracionário, idioma e conteúdo; testar 100%, 125%, 150% e 200%. Sem texto truncado que esconda ação ou status; tooltip ajuda, não substitui rótulo essencial.
- Alvos principais de mouse têm pelo menos 40×40 px no launcher e Control Center; botões compactos do dock não podem exigir precisão de pixel e oferecem área de clique adequada ao tamanho escolhido.
- Animação explica expansão, troca ou chegada de estado. Preferência de movimento reduzido e configuração de velocidade; também obedecer política do sistema quando disponível. Sem animação necessária para compreender uma mudança.
- Direção visual própria: costa, enseadas, linhas de horizonte e tipografia editorial com parcimônia. Evitar copiar símbolos, wallpapers, sons e assets da Apple ou aplicar vidro/gradiente como solução universal.

### Personalização e temas

O editor usa três colunas/painéis adaptáveis: lista de módulos e layout; prévia de dock/barra; propriedades do item selecionado. Em janela estreita, empilha a lista e a prévia sem esconder Aplicar/Cancelar. Mudanças na prévia não alteram o painel real até aplicar. Arrastar tem equivalente por teclado (mover antes/depois), indicação de destino e ação desfazer.

Controles da primeira experiência personalizável: escala e tamanho; alinhamento, margem e espaçamento; forma/opacidade; tema e cores de realce; ordem e visibilidade dos widgets; animação; posição/monitor; itens fixados; módulos habilitados. Evitar controles que não possam ser mantidos nem validados. Perfil selecionado sempre visível e reversível.

Presets iniciais: **Essencial** (dock e apps), **Maré** (dock com widgets), **Estúdio** (dock, barra compacta e foco em produtividade) e **Jogo** (dock/media/Steam). A composição **Inspirado no macOS** é uma escolha visual opcional e separada dos presets; reutiliza serviços e fluxos KDE. Meta → Orla Search tem um fluxo explícito no fonte, descrito abaixo, e ainda exige qualificação própria. Todos mostram a lista de mudanças; substituem somente os painéis explicitamente selecionados e preservam recuperação do layout original.

Importar/exportar configuração em arquivo declarativo versionado (por exemplo, JSON), com prévia de diferenças, validação de esquema e migração conhecida. Não importar segredos, tokens, conteúdo de calendário nem caminhos privados por padrão. Arquivo inválido não sobrescreve configuração válida. Permitir exportação seletiva de aparência/layout sem dados pessoais.

## Temas e catálogo comunitário

Separar **tema** (tokens, assets e variantes declarativas) de **plugin** (componente que pode ler dados ou executar ações). Os temas declarativos são a primeira extensão pública e entram cedo: X1 define formato/galeria/validador; X2 habilita importar/gerir temas com prévia e recuperação. Pacote com manifesto pequeno, licença e autoria, versão mínima do Orla/Plasma, paleta e assets locais com tamanho limitado. Sem QML/JS executável no processo do dock, fontes remotas, scripts ou permissões de dados. Prévia isolada, desfazer e remover preservando a seleção anterior. Validar contraste, variantes clara/escura, foco, textos longos e ícones em CI.

X3, previsto para 0.6/0.7, pode listar fontes de extensões e permitir instalar/atualizar/remover. O catálogo é descoberta, não autoridade: exibir origem, autor, licença, versão, permissões e hash; instalar de fonte externa requer escolha e confirmação. A pessoa pode importar manualmente pacote documentado. Desinstalar revoga o acesso, para processo, limpa apenas dados da extensão após confirmação e registra o que ficará guardado.

Extensões executáveis exigem um processo separado com protocolo versionado e permissões por capacidade (ex.: ler metadados MPRIS, ler quota local, abrir URL, enviar notificação); negar por padrão acesso a arquivos, rede, calendário, clipboard e execução de comandos. Mostrar o efeito antes da concessão, permitir revogar, e validar saída/tempo/uso de memória. Falha ou ausência do plugin não impede o dock de abrir. Cada integração expõe comandos documentados e limitados, nunca acesso arbitrário ao shell como atalho de desenvolvimento.

### Contribuição e sustentabilidade

Publicar guia de desenvolvimento, checklist de acessibilidade/temas, exemplos mínimos, template de issue e extensão, testes visuais e galeria de temas. Manter CI que valida manifesto, licença informada, compatibilidade, recursos incluídos, permissões, dimensões de ícone e contraste. Releases exigem revisão humana, changelog, origem e artefato reproduzível/verificável.

Desenvolvedores podem distribuir extensões gratuitas, cobrar licença fora do catálogo, oferecer suporte/doações ou publicar pacotes comerciais em loja própria. No futuro, catálogo pode mostrar botão de compra externa claramente separado da instalação. Orla não processa pagamentos nem promete compatibilidade/reembolso para transações de terceiros sem decisão explícita sobre operação, suporte, segurança e jurisdição. Extensão paga não pode degradar nem bloquear função do core; licença e dependências ficam claras antes de adquirir. Revisar marca, segurança, privacidade e regras locais antes de viabilizar marketplace transacional.

## Launcher e integrações de IA

O launcher começa por busca e ações determinísticas. Resultados mostram origem (KRunner, Orla, extensão), atalho, escopo e disponibilidade. Digitar apenas consulta; Enter/clique executa o item selecionado. Nenhuma ação destrutiva ou externa roda como efeito colateral de completar texto.

Windows/Meta é uma escolha independente de tema e preset. No fonte, a pessoa
inicia `build/launcher/bin/orla-launcher --managed-shortcuts`: uma única instância usa
a ação persistente `org.orla.Launcher` / `orla-search-open`, inicialmente com
Ctrl+Alt+Meta+O quando disponível. Com o launcher já ativo, consulta
`python3 scripts/orla.py search-shortcut status` (somente leitura) e escolhe
`enable` para acrescentar Meta isolada; iniciar o launcher não toma Meta.
`disable` ou `recover` devolvem apenas Meta à ação anterior registrada e mantêm
os demais atalhos atuais, inclusive alterações feitas depois da ativação.
Um novo proprietário de Meta bloqueia a recuperação e mantém seu registro.

O [fluxo completo e os limites](../launcher/README.md#windowsmeta-para-orla-search--escolha-explícita)
incluem a necessidade do launcher ativo, ausência de autostart/instalador de
serviço e recusa de contextos personalizados. KDE não oferece escrita condicional
(CAS): uma edição concorrente na mesma ação entre consulta e gravação pode ser
sobrescrita. A revisão local de 13/10 passou sete CTests e verificou Meta,
consulta/↓/Enter de fixture própria, reabertura, Escape/foco, atalho alternativo,
reinício do serviço e restauração do KRunner no Wayland, com DPR observado 1,45.
O [baseline de 15 tentativas](validation/launcher-focus-baseline.md) localizou a
perda sem intervalo na entrega à janela anterior durante a ativação. As
reaberturas a 50/100/500 ms passaram três vezes por intervalo; isso não garante
50 ms em todos os ambientes. Não se observou janela ativa com a busca sem foco,
e a ativação atual foi preservada. A prontidão visual deve acompanhar atividade
da janela e foco real do campo; digitação sem intervalo e outros ambientes
continuam sem qualificação. A release
pública 0.2.9 permanece sem launcher; não há nova API pública de extensões.

IA é uma capacidade opt-in invocada para uma tarefa identificável, não uma tela de chat obrigatória nem dependência de dock. Em 0.3, spikes devem validar APIs e CLIs oficiais, elegibilidade, consentimento, custo, armazenamento de credenciais e limites de protocolo antes do desenho de integração. A integração MVP pode chegar a partir de 0.5 como módulo opcional e isolado; não depende da estabilização de um SDK de plugins de terceiros. Vias possíveis:

| Via | Experiência e limites |
|---|---|
| API do usuário | Escolher endpoint/provedor compatível, inserir chave no armazenamento seguro do sistema, estimar custo quando o provedor publica preço e mostrar estimativa desconhecida quando não publica |
| CLI/subscrição instalada pelo usuário | Detectar cliente suportado e pedir autorização/interação pelo próprio cliente; usar apenas comando/fluxo documentado pelo provedor e permitido pelos termos atuais |
| Extensão de comunidade | Provedor isolado, nome e origem sempre mostrados; permissões de rede/arquivos/contexto apresentadas antes da ativação |

Não ler bases de sessão, copiar tokens, extrair credenciais do browser nem emular login/OAuth de produtos. Não tratar assinatura como autorização para automatizar um protocolo privado. OAuth novo só é apropriado quando provider documentar oficialmente o fluxo, a elegibilidade do plano e o uso por terceiros/OSS. Integrações com subscrição devem seguir o cliente/CLI oficial e os limites documentados. Para decisões por provider (incluindo Codex, Claude Code e OpenCode), consultar [AI_INTEGRATIONS.md](AI_INTEGRATIONS.md); conferir documentação, elegibilidade, consentimento, licenciamento e termos atuais antes de implementar. Se não houver integração suportada, explicar e oferecer configuração manual de API, sem tentar contornar login ou cobrança.

Antes de enviar, mostrar o texto, contexto anexado (trecho de seleção, nome/caminho, dados de calendário ou projeto), provedor, destino, retenção informada, modo/API, estimativa de custo ou “não disponível”. Começar sem contexto automático: pessoa escolhe o que anexar e por quanto tempo. Chave fica no keyring/secret service; jamais em arquivo de tema, exportação, log, crash report ou prompt. A pessoa consegue apagar configuração/conversas locais e trocar/desconectar o provider.

Fluxo de valor: selecionar tarefa (ex.: resumir texto escolhido, explicar resultado de busca ou rascunhar comando) → inspecionar/editar entrada e contexto → escolher provider → executar → acompanhar etapas úteis → revisar artefato/diff → aceitar, editar, copiar explicitamente, repetir, desfazer ou descartar. Resultado gerado é sugestão até aceite. Ações de sistema sempre explicam efeito e pedem confirmação no ponto de execução.

Estados de IA: pronto; aguardando conexão; enviando; recebendo resposta; aguardando aprovação de ferramenta; parcial; cancelado; limite atingido; offline/erro; completo. Manter rascunho e resposta parcial ao falhar. Oferecer cancelar de verdade, retry com escopo definido e aviso se operação já pode ter sido cobrada. Progresso é indeterminado se não houver percentual real; nunca exibir “pensamento” ou raciocínio privado como se fosse evidência. Apresentar fontes realmente consultadas e distinguir citação, contexto fornecido e inferência; sem fontes, dizê-lo.

## Notificações, HUD e atenção

Um registro de evento define origem, prioridade, duração, destinos habilitados e ação. Usuário controla posição/monitor, som, duração, aplicativos permitidos, horários e Não Perturbe. Agrupar eventos repetidos e evitar toast sobre área interativa/foco; teclas de volume/brilho não devem duplicar OSD do Plasma. Toast deve ser curto, acessível, fechável e não tomar foco; HUD mostra mudança transitória confirmada pelo estado real; ilha compacta mantém uma atividade persistente apenas enquanto há informação útil (mídia, gravação confirmada, timer), com clique/teclado para detalhes. Histórico pertence ao mecanismo KDE; Orla não consome nem reemite notificações globalmente até provar ausência de duplicação e preservação de ações/histórico.

## Acessibilidade e estados

- Navegação integral por teclado, foco visível e lógico, Escape fecha popup sem perder seleção; não prender o foco em dock/barra. Atalhos exibidos junto às ações e editáveis sem conflito com Plasma/KRunner.
- Texto redimensionável, contraste verificado para texto/ícones/foco/estados em todos os temas; informação nunca depende só de cor, som, gesto ou hover. Alternativas nomeadas para leitores de tela e labels em PT-BR/EN.
- Reduzir movimento, prevenir flashes, permitir fechar toast e não interromper leitor de tela com anúncios de streaming. Anunciar apenas mudança final/etapa útil via região acessível.
- Para widgets de tela, barras de progresso, calendários e listas: foco por item previsível, seleção distinta de item ativo, vazio/erro explicado e botão explícito de recuperação.
- Verificar fluxos reais com leitor de tela e alto contraste no Plasma suportado; auditoria automática é evidência auxiliar, não declaração de conformidade.

## Design e DX para mantenedores

- Componentes Qt Quick/Kirigami pequenos com tokens semânticos centralizados e variantes documentadas. Separar estado de apresentação, provider de dados e operação. Preferências têm esquema versionado, defaults seguros e migrações cobertas por teste.
- Organizar módulos por superfície/capacidade e oferecer interfaces públicas com versão antes de chamar algo de SDK. Extensões não importam arquivos privados do dock nem compartilham objetos globais mutáveis.
- Galeria local de estados reais/sintéticos: temas, escala, dock com/sem tarefas, popup, sem integração, dados antigos, erro, loading, foco/teclado, calendário vazio, quota desconhecida e nomes longos. Dados de showcase devem ser sintéticos e rotulados.
- Comandos de desenvolvimento para executar modo preview isolado, validar tema/manifesto, rodar testes e empacotar extensões; logs sem segredos e erro indicando arquivo/capacidade e recuperação. Prover licença de dependências e regras de tradução de strings/exemplos.
- Toda contribuição UI inclui descrição do objetivo, capturas da galeria em claro/escuro, navegação teclado, estados de erro/vazio e validação em escala fracionária. Verificar contraste, clipping e regressão dos presets no CI.

## Métricas e gates de qualidade

Metas abaixo são propostas a medir em máquinas de referência; não são resultados atuais. Estabelecer baseline antes de otimizar.

| Sinal | Critério alvo antes de beta/1.0 |
|---|---|
| Tempo de acesso | Dock pronto em até 1 s após serviço/UI disponíveis; launcher com primeiro resultado local em até 150 ms p95 em máquina de referência |
| Estabilidade | 7 dias de piloto sem perda de configuração; módulos opcionais podem falhar sem derrubar dock |
| Personalização | Ativar preset, ajustar tamanho/tema, desfazer, reiniciar e exportar/importar sem perder painéis nem segredos |
| Acessibilidade | Fluxos primários teclado e leitor de tela; contraste, foco, zoom e movimento verificados por tema |
| Extensões | Tema inválido rejeitado sem quebrar tema ativo; extensão sem permissão isolada e revogável; remoção reproduzível |
| IA | Nenhum envio antes da ação deliberada; provider/contexto/custo e estado visíveis; cancelamento, limite, erro e resultado parcial tratados |
| Atenção | Sem duplicação com OSD/notificação do Plasma na matriz de apps/ações suportados; toast não rouba foco |

Não usar volume de prompts, tempo dentro do launcher ou venda de extensões como sucesso isolado. Acompanhar conclusão da tarefa, tempo até o primeiro resultado útil, correções/desfazer, falhas/retries, cancelamento e envio de contexto. Telemetria permanece desligada por padrão; qualquer coleta futura precisa ser opt-in, minimizada e explicada.

## Sequência de UX proposta

1. **0.3 — previsibilidade e pesquisa de IA:** validar os fluxos existentes em painel real, navegação/fechamento de popup, foco, monitor/escala e dependências opcionais. Corrigir texto, estados ausentes e recuperação antes de acrescentar controles. Fazer spikes para API/CLI oficial, elegibilidade de uso por plano, consentimento, custo e segredo; isso não presume integração entregue.
2. **0.4 — personalização e temas iniciais:** editor com prévia, Aplicar/Cancelar/desfazer, tokens/presets, seleção de widgets, esquema de export/import, acessibilidade e X1/X2 para tema declarativo local. Qualificar Spotify e bateria com status fiel.
3. **0.5 — perfis + launcher:** perfis compreensíveis e reversíveis; launcher por teclado em camada simples com busca/resultados/ações/status vazios; aceitar cancelamento e navegação em cada estado.
4. **0.6–0.7 — barra e controles:** habilitar superfície/módulos individualmente, reutilizar widgets KDE qualificados, manter labels/atalhos e estado confirmado; provar antes a compatibilidade de Menu Global e serviços de sistema.
5. **0.8 — eventos:** preferência por tipo e não perturbe; evitar interrupções e duplicação antes de liberar apresentação global.
6. **0.6–0.7 — distribuição de extensões (X3):** catálogo/fontes, importação, atualização e remoção com origem, integridade, permissões e revisão/licença visíveis. Plugins executáveis seguem a trilha isolada abaixo.
7. **Depois dos spikes e a partir de 0.5 — IA integrada e opcional:** entregar uma tarefa estreita com API ou fluxo de CLI oficial elegível; mostrar provider, contexto, custo/limite e permitir cancelar e revisar o resultado. Os adapters nativos do Orla não precisam aguardar SDK público de extensão. Estender somente a protocolos oficialmente permitidos.
8. **Após contratos e limites de segurança — plugins executáveis:** processo externo, manifesto/permissões, revogação, compatibilidade e revisão; temas declarativos e adapters de IA nativos não ficam bloqueados por essa etapa. Publicar exemplos gratuitos antes de avaliar loja paga.
9. **1.0 — uso diário:** gates da tabela de qualidade aprovados nos ambientes declarados, instalação/recuperação e documentação para usuários e contribuidores completas.

## Validação com pessoas

Testar com pessoas que usam somente dock, KDE com painéis customizados, baixa visão/leitor de tela, alto DPI, multi-monitor, laptop/desktop e perfis de trabalho/jogos. Cenários: instalar sem mover painel existente; montar só dock; esconder widgets; mudar monitor/escala; desfazer preset; remover tema; descobrir extensão e negar permissão; buscar ação e cancelar; identificar o que seria enviado à IA; interromper notificações. Registrar onde hesitam, erros e recuperação; não declarar usabilidade validada até conduzir sessões observadas. Antes da beta, repetir com distribuição/Plasma além do ambiente principal quando esse suporte for anunciado.
