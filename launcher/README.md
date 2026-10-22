# Orla Launcher — componente opcional experimental

Janela Qt Quick própria para aplicativos e calculadora locais, usando as APIs públicas de KRunner, e inventário Steam local explícito. Digitar consulta; Enter ou clique executa a seleção. ↑/↓ navegam, Tab alcança as ações e Esc limpa/cancela e fecha. Calculadora oferece a ação explícita de copiar; digitar não altera o clipboard. O core usa KConfig anônimo e desliga o histórico do runner. O núcleo de busca não mantém histórico de consultas do Orla nem usa contexto automático, runner de shell, integrações de conta ou rede.

## Steam local — somente no fonte

O painel **Steam** não lê nada ao abrir. Cada raiz precisa ser informada na sessão como `native=/caminho/absoluto` ou `flatpak=/caminho/absoluto`; **Carregar jogos** chama o helper limitado `scripts/steam.py` sem shell. O inventário validado entra na busca em categoria própria e some ao encerrar o processo. Não há raiz padrão, detecção por HOME, persistência, perfil, histórico, conta, autenticação ou rede.

Somente um resultado atual com estado `installed_candidate` pode encaminhar `steam://rungameid/<appid>` por Enter/clique. **Abrir downloads no Steam** encaminha apenas `steam://open/downloads`. O retorno informa no máximo que o desktop aceitou o pedido; não prova handler, cliente, login, titularidade ou que o jogo abriu. Recarga, cancelamento e mudança de consulta invalidam tickets anteriores. `StateFlags=4` continua sendo uma interpretação experimental de presença local, com `ownership` e `connection` sempre desconhecidos.

Essa integração permanece fora dos assets públicos 0.2.5–0.2.9, não foi executada contra raízes pessoais e não qualifica Steam native/Flatpak, biblioteca desmontada, dois jogos reais ou gesto humano Wayland. Os testes usam árvores e processos próprios, opener injetado e D-Bus/XDG privados; nunca chamam o handler Steam real.

## Experimento de compatibilidade com provedores de IA — somente no fonte

O código do launcher inclui um painel experimental **IA**. Ele é separado do dock, começa desligado e não faz parte dos assets publicados 0.2.5–0.2.9. Abrir o painel não inicia helper nem cliente. **Verificar clientes instalados** é uma ação local explícita: consulta uma lista fixa (Codex, Claude Code, OpenCode, Ollama e LM Studio) e mantém todos desativados. Ollama é apenas detecção de presença, pois consultar sua versão pode contatar um servidor.

A ação separada **Testar compatibilidade anônima** exige consentimento próprio e testa somente uma troca limitada `initialize`/`initialized` do Codex para uma versão reconhecida. Não autentica, reutiliza sessão conectada, envia texto/contexto pessoal, inicia modelo, turno ou geração, nem informa uso. Não há chat, fluxo de texto selecionado, cofre de credenciais ou handoff para terminal. Cancelar/fechar é tratado pelo controlador; o resultado permanece no estado da sessão e não vira configuração persistente.

Para executar clientes, o controlador exige um `XDG_RUNTIME_DIR` absoluto, privado, pertencente ao usuário e sem symlinks. Cada operação recebe uma pasta temporária própria nesse runtime; o helper recebe seu caminho e identidade por argumentos privados. O controlador mantém a operação ocupada até confirmar o encerramento do grupo e a remoção da pasta original. Uma diferença de identidade detectada impede a limpeza e a conclusão.

A invocação `python3 -I -B scripts/ai.py detect` continua reconhecida. Sem a pasta privada fornecida pelo controlador, as consultas que exigem execução isolada ficam indisponíveis; o helper não cria uma pasta no checkout. O teste do protocolo anônimo continua sendo uma ação separada de consentimento na interface. CLI reconhecida ou troca mínima bem-sucedida não demonstra autorização do provedor, elegibilidade de conta, acesso a modelo, API suportada ou prontidão para inferência.

A fatia Source recebeu aprovação independente e foi integrada pelo PR [#20](https://github.com/caiolombello/orla-desktop/pull/20); a CI portátil [também passou](https://github.com/caiolombello/orla-desktop/actions/runs/38115242191/job/114398735163). Esse run anterior não compilou o launcher C++/QML nem executou CTests. O job separado de build em Fedora 44 agora [compilou o launcher e passou os cinco CTests fechados](https://github.com/caiolombello/orla-desktop/actions/runs/38124013823/job/114424469019). Não há versão de release própria para o launcher: os assets 0.2.9 excluem launcher C++/QML, painel de IA e barra. O ZIP do dock inclui somente `scripts/ai.py` e `tests/test_ai.py`, sem oferecer painel ou integração de IA ao usuário. Evidências sintéticas e one-shot delimitadas estão no [registro de validação](../docs/validation/ai-provider-source.md). Autenticação, inferência, semântica de cancelamento, uso, pedidos pagos, procedência do cliente instalado, isolamento de namespace/rede e comportamento nativo Wayland/QML permanecem sem qualificação.

## Geração de texto Ollama — integração experimental neste Source

Esta mudança Source integra ao painel **IA** uma transformação de texto
limitada a Ollama: reescrever, resumir ou traduzir. A pessoa informa texto,
modelo, porta, idioma quando necessário e escolhe somente `127.0.0.1` ou `::1`.
Antes do envio, a interface mostra destino, modelo, tarefa, dados e **custo não
informado**, explica que qualquer processo nesse endereço pode receber ou
encaminhar o texto e pede consentimento para a sessão. Alterar host, porta ou
modelo revoga esse consentimento. Abrir o painel, editar campos ou consentir não
executa nada; somente **Gerar** inicia o pedido.

Durante a execução, os campos ficam bloqueados e a ação principal vira
**Cancelar**. Deltas aparecem numa área somente leitura; resposta parcial é
preservada para revisão e **Copiar resultado** continua sendo uma ação manual.
Fechar o painel ou abrir Steam cancela os dois controladores de IA. O pedido
de fechamento da UI e a repetição do atalho com a janela ativa esperam os três
proprietários — compatibilidade de IA, texto e Steam — antes de concluir uma
única vez. Uma nova tentativa limpa texto e uso anteriores antes de validar
a entrada; uma tentativa ignorada durante execução ou fechamento preserva o
resultado ativo. Ao voltar à busca, Enter, cliques e ações de resultado ficam
bloqueados enquanto algum dos três proprietários está ocupado ou há fechamento
pendente. Os controles
mostram o estado de espera, permitem continuar digitando e voltam a funcionar
após a limpeza. Uma falha de limpeza atualiza a interface sem repetir o aviso
nos polls idênticos; a operação permanece ocupada até a recuperação.

O controller inicia exatamente Python isolado com `-I -B`, o helper
`ai_text_ollama.py` e `run-ollama`, em cwd privado e com ambiente filho vazio.
O helper operacional seleciona somente o conector Ollama numérico e reutiliza o
lifecycle T1/T2 protegido. O entrypoint direto `ai_text.py` continua falhando
fechado com `unsupported_transport`; o adaptador HTTPS privado de OpenAI também
permanece sem ligação operacional, credenciais ou UI. Não há probe automático,
início de servidor, download de modelo, fallback, leitura de clipboard,
histórico, arquivos/contexto, autenticação ou API paga.

Esta mudança adota a composição Source validada. O shim, o controller R3 e a
correção de UI receberam revisão independente delimitada. O build normal da composição, seis
CTests isolados e 90 testes Python passaram (6 do shim, 23 T1 e 61 T2),
usando somente processos e servidores HTTP privados e sintéticos. Após as
correções do PR [#36](https://github.com/caiolombello/orla-desktop/pull/36), um
build normal e os seis CTests passaram, com 19 entradas do controller e
17 da UI. As duas correções seguintes de resultado anterior e atalho receberam
revisões independentes; a composição final passou um build novo e os seis
CTests, com 24 entradas do controller e 18 da UI. Timeout continua sendo falha
de prazo após a limpeza; uso só é
rotulado como reportado quando o estado validado informa isso. Uma resposta
terminal com custo inválido não publica os tokens daquela resposta. A fixture
do shim também passou em Python 3.12.3 e 3.14.7 em harnesses próprios que
preservam HOME/CODEX_HOME. Não houve
Ollama ou modelo real, validação semântica da resposta,
clipboard nativo, acessibilidade nativa, instalação, pacote relocável, release
ou admissão de usuário/Wayland. Loopback limita o destino de rede; não confirma
identidade Ollama, processamento offline ou privacidade, e o processo que
escuta ali pode encaminhar o conteúdo para outra rede. Os dois jobs hospedados
passaram em `1f59e0c`. Em `2c8b750`, o job portátil passou e as 17 entradas da
UI passaram, mas o processo saiu com SIGSEGV depois de terminar os testes; a
causa permanece desconhecida. Os dois jobs passaram depois em `57c2aa0`; o job
do launcher reportou os seis CTests aprovados e o diagnóstico GDB foi pulado.
O workflow mantém a captura limitada somente após falha, preservando o resultado
original. Esse run aprovado não explica o SIGSEGV anterior.

As duas correções seguintes de NOTIFY e execução de resultados passaram na
composição exata: build novo, seis CTests, 25 entradas do controller e 27 da UI.
A UI terminou em 24,75 s, dentro do limite preservado de 30 s. O teste de ação
lê somente o buffer de clipboard privado da plataforma offscreen. A revisão
detectou uma referência obsoleta no novo teste Steam; o teste foi corrigido
para conferir o controle vivo após a reconstrução do modelo.
Os dois jobs também passaram em `28c5ef4`; os seis CTests hospedados terminaram
em 74,04 s e a UI em 24,27 s. Esse log aprovado não imprime os contadores Qt
dos processos filhos.

As duas correções seguintes publicam a notificação final antes de liberar o
fechamento e mantêm a intenção de sair mesmo após novos pedidos de ocultação.
O estado final chega aos bindings da UI com a barreira de geração preservada
durante a notificação; depois a prontidão é emitida uma vez. O pedido de saída
faz parte do mesmo fechamento após a limpeza dos três proprietários, incluindo
o caminho em que todos já ficaram prontos. Os flags são consumidos antes de
despachar ocultação/saída, sem herdar um quit no ciclo seguinte.
A composição conjunta passou build novo de 40 passos e os seis CTests isolados
em 75,925 s, com 27 entradas do controller e 27 da UI, sem falhas nesses dois
processos. A UI levou 24,60 s, dentro do limite preservado de 30 s.
A revisão do controller aprovou o Source com uma limitação explícita: um
desafio QML cooperativo adicional falhou ao exigir cancelamento confirmado
(apresentou cancelamento não confirmado, causa exata desconhecida); os casos
QML forced/timeout e os 27 testes normais passaram. A falha foi preservada.
A revisão independente da saída passou os 27 testes normais e um desafio
adicional com os três helpers reais: o último controlador notificou todos
prontos com quit ainda pendente, o atalho efetivo fez o fechamento imediato
único e a prontidão posterior não duplicou ocultação/saída. O ciclo seguinte
sem quit também passou. A primeira fixture desse desafio pressupunha um
prazo Steam errado e falhou antes da verificação causal; ficou preservada.
A fixture corrigida alterou apenas o prazo de teste exposto, em build novo.
O uso de tokens agora fica pendente até validar a resposta completa, saída
normal zero e limpeza confirmada. Dados extras, erro de saída, cancelamento
e timeout descartam esse uso sem apagar o texto parcial revisável. Sete novas
regressões com helpers reais e retries passaram depois das falhas causais no
código anterior. A revisão independente passou controller 34 e um desafio
adicional de cinco entradas: saída padrão fechada com processo ainda vivo
não publica uso; conclusão válida publica uso reportado ou desconhecido,
e fechamento preserva a barreira e a ordem de notificação.
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
com SIGSEGV depois de 7 PASS/0 FAIL/1 skip esperado; os outros cinco CTests
passaram. Causa UNKNOWN; um único GDB local saiu zero sem reproduzir o crash.
O workflow amplia somente o diagnóstico após falha para um alvo behavior/UI,
priorizando behavior e mantendo os limites e o resultado original. CI desta
revisão e integração na branch principal continuam pendentes.
O canary local de `5aaf518` substituiu reversivelmente o executável instalado,
com backup e alteração somente do caminho no wrapper. A build permanente ALL40
passou seis CTests uma vez em 80,85 s. No KDE foram observados atalho, retorno
de foco, painel de IA, rolagem por Tab, popup de tarefa, cálculo `2+2`, saída
limpa e reinício; o serviço ficou ativo/habilitado. Esses fluxos básicos não
qualificam geração/provedor real, clipboard/acessibilidade, matriz de telas,
pacote relocável, distribuição/release ou admissão completa.

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

## Fundação do pacote de dados — somente no fonte

`launcher/package.py` contém um builder determinístico e um verificador externo
para um ZIP de dados com cinco arquivos allowlisted: ELF, helpers de IA/Steam,
licença e manifesto. O verificador compara o SHA-256 externo antes de interpretar o conteúdo.
Depois da decodificação limitada, confere o commit esperado no manifesto, além
de nomes, modos, hashes, CRC e limites reais de descompactação. Ele não extrai nem executa o payload.

O inventário de dependências ainda é uma declaração fornecida pelo chamador
(`caller_assertion_unverified`); não foi coletado do ambiente. `doctor` retorna
`unsupported_doctor`. Staging CMake, resolução relocável dos helpers, coleta
RPM, diagnóstico do host e artifact hospedado continuam pendentes. Essa fatia
não instala o launcher e não altera dados do usuário. O ZIP Source gerado pela
CI continua excluindo `launcher/`, inclusive este empacotador. Ele inclui os
helpers-fonte de texto da IA em `scripts/` e seus testes em `tests/`; isso não
os transforma em recursos instalados.

```sh
python3 -B -m unittest discover -s launcher/tests -p 'test_package.py' -v
```

Os 17 testes mantidos usam ELF e inventários sintéticos, com ZIPs adversariais e
verificação de determinismo. O checksum precisa vir de um canal confiável;
um `SHA256SUMS` ao lado do arquivo, sozinho, não autentica sua origem.

## Compilar e testar

Requer compilador C++17, CMake ≥3.24, Qt ≥6.11.2 (Core, Gui, Widgets, Qml e Quick; Network, Test e DBus para os testes), KF6 ≥6.30 (Runner, Config, GlobalAccel, WindowSystem) e runners `krunner_services` e `calculator` do Plasma. Ambiente validado: Fedora 44, Qt 6.11.2, KF6 6.30.0, Plasma 6.7.5. O Qt Quick Controls também deve estar disponível em runtime. Os testes exigem Python 3, `dbus-daemon` e `gdbus`. No Fedora, os headers vêm de `qt6-qtbase-devel`, `qt6-qtdeclarative-devel`, `kf6-krunner-devel`, `kf6-kconfig-devel`, `kf6-kglobalaccel-devel` e `kf6-kwindowsystem-devel`; os runners instalados foram fornecidos por `plasma-workspace-libs`.

```sh
cmake -S launcher -B build/launcher -G Ninja -DBUILD_TESTING=ON
cmake --build build/launcher
ctest --test-dir build/launcher --output-on-failure
build/launcher/orla-launcher --no-global-shortcut
```

Sem atalho global, Esc encerra o processo. Na execução normal, o componente tenta registrar **Ctrl+Alt+Meta+O** apenas durante a sessão do processo; `--shortcut 'Ctrl+Alt+Meta+F12'` escolhe outra combinação. Uma combinação ocupada não é substituída e a janela continua utilizável. Esc oculta a janela enquanto o atalho está registrado; fechar pelo X ou Ctrl+Q encerra e remove o registro temporário próprio. Não há autostart, instalação automática, alteração de painel ou integração de menu nesta pasta.

`--start-hidden` inicia a janela oculta quando o registro do atalho funciona. Se o atalho estiver ocupado ou desativado, a janela permanece visível para que o launcher continue acessível.

### Windows/Meta para Orla Search — escolha explícita

O modo `--managed-shortcuts` registra uma única instância com a identidade
persistente `org.orla.Launcher` / `orla-search-open`. Na primeira execução, tenta
salvar **Ctrl+Alt+Meta+O** sem substituir uma combinação ocupada; nas seguintes,
reutiliza a configuração salva, inclusive quando desativada. Encerrar o processo
preserva esses atalhos, mas eles só abrem a busca enquanto o launcher estiver
ativo. Esse modo não aceita `--shortcut` nem `--no-global-shortcut`.

Inicie o launcher em um terminal e mantenha-o ativo; execute a CLI em outro:

```sh
build/launcher/orla-launcher --managed-shortcuts
```

```sh
python3 scripts/orla.py search-shortcut status
python3 scripts/orla.py search-shortcut enable
python3 scripts/orla.py search-shortcut disable
python3 scripts/orla.py search-shortcut recover
```

`status` apenas consulta o proprietário atual de Meta, o registro de recuperação
e se o launcher gerenciado está ativo; não cria registro nem altera atalhos.
`enable` exige esse launcher já ativo e **Ctrl+Alt+Meta+O** configurado antes de
adicionar Meta isolada à ação Orla. Antes de remover Meta do proprietário
anterior, salva um registro privado em `$XDG_STATE_HOME/orla/search-shortcut`
(ou no diretório de estado padrão). Não há tomada automática de Meta ao iniciar.

`disable` desfaz a atribuição de Meta; `recover` retoma uma restauração pendente
após falha ou interrupção. Ambos removem apenas Meta de Orla e a devolvem à ação
anterior registrada, preservando os demais atalhos atuais dessas ações e outras
alterações no desktop. Não restauram um arquivo de configuração completo nem
removem o atalho persistente Ctrl+Alt+Meta+O. Se Meta recebeu outro proprietário,
a recuperação recusa a alteração e preserva o registro para resolver o conflito.

Esse fluxo usa `busctl` e KGlobalAccel da sessão Plasma, sem iniciar serviços.
Múltiplos proprietários e contextos personalizados de Meta são recusados. As
consultas e confirmações reduzem conflitos, mas KDE não oferece compare-and-swap
(CAS) para essa escrita: uma alteração concorrente na mesma ação entre consulta
e gravação ainda pode ser sobrescrita. Evite editar essa ação em paralelo.
Não há instalador de serviço, autostart ou API pública de extensões nesta fatia.

**Qualificação local de 13/10:** passaram 19 testes da CLI, 23 casos de atalhos e
sete CTests em build permanente (97,17 s). No Plasma 6.7.5/Wayland, Qt 6.11.2,
com DPR observado de 1,45, Meta abriu a busca, ↓ selecionou a fixture própria e
Enter executou somente essa seleção. O processo permaneceu ativo e reabriu;
Escape devolveu o foco, o atalho alternativo funcionou e Meta+O não abriu a busca.
Reiniciar o serviço preservou Meta; desativar restaurou o KRunner e reativar
voltou ao Orla. Os defaults anteriores foram conferidos e preservados.

O primeiro teste real encontrou saída automática do Qt após o job KIO executar
um app com a janela oculta. A correção usa `setQuitLockEnabled(false)`, como o
[KRunner 6.7.5](https://github.com/KDE/plasma-workspace/blob/v6.7.5/krunner/main.cpp),
e a regressão executa o `main` real, reabre a busca e verifica saída explícita.
O [baseline posterior de foco](../docs/validation/launcher-focus-baseline.md)
registrou 15 tentativas próprias. As três sem intervalo perderam caracteres
para a janela anterior; a primeira tecla foi emitida antes do callback do
atalho. As reaberturas a 50/100/500 ms passaram três vezes por intervalo, e as
três primeiras aberturas de novos processos a 500 ms também passaram. A mediana
até o callback de atividade com foco foi 15,15 ms nas reaberturas; isso não
garante digitação sem intervalo ou define um orçamento geral. A ativação foi
preservada: os dados não demonstraram atraso adicional de foco do campo.
Outros monitores, atalhos inibidos e reinício do daemon continuam abertos.
Ctrl+Q foi verificado na regressão isolada, sem novo
teste nativo nesta revisão. Os recibos históricos abaixo mantêm seu escopo.

## Limites de qualificação

Build, busca real por aplicativos/calculadora, cancelamento, proteção contra callbacks antigos e execução exclusiva de uma fixture própria foram verificados. Os testes de teclado Qt simulam eventos dentro da própria janela; não comprovam atalhos globais nem foco real no compositor. Todos os CTests usam bus D-Bus privado sem diretórios de ativação de serviços e XDG/runtime temporários próprios. O processo Qt verifica o ID desse bus antes de construir RunnerManager. O teste de fixture cria um `.desktop` e recibo próprios; tudo é removido ao terminar, e nenhum aplicativo pessoal é lançado automaticamente. O runner do Plasma pode registrar o acesso ao aplicativo explicitamente aberto em serviços do desktop, como KActivities; desligar o histórico do Orla não desliga esses serviços.

**Recibo histórico dos probes iniciais:** atalho por gesto real, foco global e retorno do foco permaneceram UNRUN nesses probes. O caminho usa `KWaylandExtras::xdgActivationToken` e `KWindowSystem::activateWindow`, com callbacks canceláveis; KWin decide conceder foco. A janela continua visível para clique se o compositor recusar. A fonte KWin 6.7.5 ainda documenta o limite de passar seat/serial por KGlobalAccel a clientes sem foco. Não há solicitação de interfaces privilegiadas ou inspeção das janelas de outros apps. O primeiro probe manual terminou sem gesto. No segundo, a pessoa confirmou “Abriu e o foco voltou”, mas os eventos shortcut/↓/Escape não apareceram no recibo instrumentado. Esse relato humano foi preservado e não foi convertido em PASS nativo. As duas janelas da fixture pertenciam ao mesmo processo; não houve qualificação entre aplicativos, e a admissão L0 ampla permanece aberta.

**Prova posterior delimitada:** em `43905da`, Ctrl+Alt+Meta+O, consulta,
↓ e Escape retornando à mesma janela de teste passaram em dois processos
independentes, numa tela Plasma 6.7.5/Wayland. Isso não qualifica Enter/dispatch,
Meta isolada, provedores reais ou múltiplos monitores; L0/L2 seguem abertos.
A revisão visual de 13/10 foi instalada com backup e passou nova consulta/Escape
com retorno à janela de teste em uma tela Wayland/DPR 2. A galeria claro/escuro
é sintética; esquema claro nativo, múltiplas telas, Enter/execução e provedores
reais permanecem sem qualificação. Os probes e canaries anteriores são históricos.
Nesses recibos, Meta permaneceu atribuída ao KRunner. A configuração explícita
descrita acima exige prova própria, incluindo recuperação do atalho anterior.

As releases públicas 0.2.5–0.2.9 não incluem este componente em seus bundles. O ZIP 0.2.9 carrega apenas os helpers-fonte `scripts/ai.py` e `tests/test_ai.py`; eles não instalam nem habilitam o launcher. O painel experimental de IA permanece apenas no fonte e não é qualificado para uso diário; empacotamento e instalação opcional do launcher seguem pendentes.

## Fontes verificadas

- [ResultsModel e construtor com grupos próprios — KF6 6.30](https://github.com/KDE/krunner/blob/v6.30.0/src/model/resultsmodel.h), [implementação do contexto/cancelamento](https://github.com/KDE/krunner/blob/v6.30.0/src/model/runnerresultsmodel.cpp).
- [RunnerManager: whitelist e histórico — KF6 6.30](https://github.com/KDE/krunner/blob/v6.30.0/src/runnermanager.h), [KConfig em memória](https://github.com/KDE/kconfig/blob/v6.30.0/src/core/kconfig.h).
- [Atalho de sessão — kglobalacceld 6.7.5](https://github.com/KDE/kglobalacceld/blob/v6.7.5/src/globalshortcut.cpp), [KGlobalAccel 6.30](https://github.com/KDE/kglobalaccel/blob/v6.30.0/src/kglobalaccel.h).
- [KWaylandExtras 6.30](https://github.com/KDE/kwindowsystem/blob/v6.30.0/src/kwaylandextras.h), [política de token — KWin 6.7.5](https://github.com/KDE/kwin/blob/v6.7.5/src/xdgactivationv1.cpp).
- [TextField](https://doc.qt.io/qt-6.11/qml-qtquick-controls-textfield.html), [Text.PlainText/elide](https://doc.qt.io/qt-6.11/qml-qtquick-text.html), [Keys](https://doc.qt.io/qt-6.11/qml-qtquick-keys.html), [QQuickWindow](https://doc.qt.io/qt-6.11/qquickwindow.html) — Qt 6.11.2.
- [QProcess](https://doc.qt.io/qt-6.11/qprocess.html) e [QDesktopServices](https://doc.qt.io/qt-6.11/qdesktopservices.html) — subprocesso com argumentos separados e encaminhamento de URI no Qt 6.11.2.


A revisão mais recente mantém cancelamento/timeout durante a publicação de
`started` e apresenta mensagens fixas de recuperação para todos os códigos de
falha aceitos. Dois revisores independentes aprovaram os escopos; a composição
passou build novo de 40 passos, seis CTests (90,697s) e 116 testes Python. A fixture cobre a
escrita completa antes do retorno do sink; não promete entrega/ACK ou escrita
parcial atômica. CI da revisão, atualização do canary `5aaf518`, provedores reais e
admissão completa seguem pendentes. Veja o registro de validação de IA.
