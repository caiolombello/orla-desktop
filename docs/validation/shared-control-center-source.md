# Central compartilhada — incremento Source S1

13/10/2026. Implementação experimental para CC0/CC1-A/T1; os marcos completos
continuam abertos. Os assets públicos 0.2.9 permanecem imutáveis.

## Comportamento e limites

O dock mantém uma única view `ControlCenter`, um `AudioControlState`, o loader
de áudio e a conexão de confirmação com o HUD. A entrada opcional da barra
carrega o cliente canônico do pacote do dock; ela encaminha intenções, sem
construir outro backend. Uma intenção aceita ainda pode falhar antes da abertura.

Sem dono, com vários docks registrados ou com versão/URL/engine incompatível,
a entrada permanece indisponível. Não há eleição automática de dock. Esse
protocolo interno experimental não é o SDK público de extensões.

A transferência invalida pedido e gesto de áudio antes de fechar. Ela espera
`closed` e o diálogo nativo invisível antes de trocar host e reabrir. Referências
tipadas, gerações e guardas de reentrada preservam pedidos sucessores e impedem
combinar âncoras de janelas diferentes. Fechar/remover uma entrada libera apenas
seu cliente. Ocultar o botão do dock preserva uma abertura originada pela barra.

Abrir não chama setters. Readback tardio de uma operação cancelada não confirma
uma nova abertura. Uma ação nova só gera confirmação/HUD após convergência do
estado observado; isso não atribui causalidade exclusiva ao serviço.

## Verificação

| Execução final local | Resultado |
|---|---|
| Registry + Session, PySide/Qt 6.12 | 49 PASS (20 + 29) |
| Composição + eventos + Central + dock, Qt 6.11.2/Fusion | 65 PASS, 3 TaskManager SKIP |
| Mesma bateria, `org.kde.desktop` | 65 PASS, os mesmos 3 SKIP |
| Barra completa, Qt 6.11.2 | 30 PASS em cada estilo |
| Layout, incluindo manifests antigos e módulo novo | 124 PASS |
| Session, cinco suítes no mesmo processo | 145 PASS, zero janelas restantes |
| Revisão independente dirigida às falhas corrigidas | 8 PASS, zero bloqueios Source |
| Design/empacotamento | check sem issues, 7 guards PASS, release fixture PASS |

- G0: sete subprocessos e 43 observações de identidade, engines, URLs, overlays,
  versões e destruição. O resultado delimita o contrato Qt; não identifica o
  pacote carregado pela sessão Plasma real.
- Registry/Entry: versão e dono único, destruição, invalidação de host/janela,
  clientes independentes, erro assíncrono e recusa de reentrada durante release.
- Session: close/hide assíncronos, último pedido, guarda entre notificações e
  callbacks, falha de abertura, cancelamento antes de close, readback tardio,
  perda de referências, teardown e restauração de foco que respeita foco novo.
- Composição local offscreen: view/áudio idênticos pelas duas entradas, zero
  escritas ao abrir, confirmação/HUD únicos, falha compartilhada, retirada da
  barra e destruição do dono. Usa KDE QML local e provedores sintéticos.
- Barra/layout: módulo direito opcional, cliente indisponível/foco/teclado,
  release exato sob reentrada, dois applets com o mesmo plugin e IDs distintos,
  manifests antigos, desativação e restauração.
- CI portátil executa Registry/Session no Qt 6.12. A composição com KDE QML tem
  suíte própria; ausência desses módulos é explicitamente diferente de PASS.
  Os três casos do TaskManager omitidos offscreen exigem Wayland ou X11.
- Design check, guards, galeria claro/escuro, pacote e exclusão das fixtures
  dependentes de `bar/` do ZIP verificam o contrato visual e a distribuição.

As falhas de reentrada e foco foram reproduzidas antes das correções e revisadas
independentemente. Sincronização dos testes aguarda sinais/estado, preservando
as verificações de geometria, Escape e foco. Nenhum delay foi inserido no produto
para acomodar os testes.

## Galeria

Capturas sintéticas offscreen, sem dados de usuários, hardware ou sessão Plasma
real. O pequeno trecho no topo do crop pertence à âncora sintética.

| Escuro | Claro |
|---|---|
| ![Central escura](../screenshots/shared-control-center/cc-shared-dark.png) | ![Central clara](../screenshots/shared-control-center/cc-shared-light.png) |
| ![Entrada com foco](../screenshots/shared-control-center/bar-cc-dark-focus.png) | ![Entrada com foco](../screenshots/shared-control-center/bar-cc-light-focus.png) |
| ![Entrada indisponível](../screenshots/shared-control-center/bar-cc-dark-unavailable.png) | ![Entrada indisponível](../screenshots/shared-control-center/bar-cc-light-unavailable.png) |

## Gate seguinte: S2 nativo

### Referência da janela do painel — correção em 13/10

A sessão real confirmou o registro canônico e o estado compartilhado pela
barra e pelo dock. A atualização gerenciada acrescentou a entrada ao mesmo
painel, mantendo os cinco IDs anteriores e o banco original de recuperação.
A abertura ainda não foi qualificada: o primeiro roteiro parou na guarda de
hover; o segundo confirmou hover e envio do clique, mas não observou popup.
Foco no botão e acknowledgment do dispositivo não comprovam `clicked`.

Uma regressão isolada reproduziu uma causa de falha de abertura: `Window` do
QML rejeita os hosts C++ `QQuickWindow` e `QQuickView` usados pelos painéis.
A atribuição interrompia `ControlCenterEntry.open()` antes de encaminhar ao
dono; a captura da exceção na barra podia deixar o botão sem ação nem erro.
A referência agora usa `QtObject`, mantendo a identidade exata da janela e
as guardas de visibilidade, destruição e release. O teste público reutiliza
o cliente e verifica abrir, liberar, reabrir e cancelar ao ocultar cada host.

O teste falhou nos dois hosts antes da correção. Depois passaram 57 testes
(Registry 21, Session 29, composição 7) em Fusion e os mesmos 57 em
`org.kde.desktop`, sem skips ou warnings. A galeria foi regenerada e revisada
em claro e escuro; não houve mudança de composição visual. Essa prova usa
hosts C++ offscreen. Abertura/foco com o código corrigido e áudio real
têm provas nativas separadas, descritas abaixo.

### Abertura pelas duas entradas — prova nativa delimitada

Na sessão Plasma 6.7.5/Wayland, Qt 6.11.2, uma tela de 2648 × 1490 DIP com
escala 2, o roteiro final de 18,61 s observou abertura, Tab e Escape tanto pela
barra quanto pela dock retrátil. Tab levou foco ao volume pela barra e ao mudo
pela dock; Escape ocultou o popup, desativou o áudio e devolveu foco à entrada
correspondente. A janela de 378 × 542 DIP ficou dentro da tela: alinhada à
barra direita e centralizada sobre o botão da dock, com transient parent
correspondente ao painel de cada abertura.
O registro canônico manteve dono único e as mesmas referências de popup,
view e estado de áudio. Abrir e navegar produziram zero setters/retries.

Os roteiros anteriores pararam na guarda de hover da dock, antes de enviar
um clique a ela. O roteiro final incluiu dois movimentos na borda inferior,
separados por 125 ms, compatíveis com a pressão exigida pelo KWin, e só clicou
após observar hover real. Isso qualifica o fluxo final; não prova que todas
as falhas anteriores tinham a mesma causa. Transferência com popup já aberto
continua um gate próprio. Foram observadas duas criações
cumulativas do backend para duas aberturas sequenciais; não se mediu a
quantidade de backends simultâneos. Os dispositivos virtuais foram liberados e os arquivos
de configuração, launcher, atalhos e recuperação permaneceram preservados.

### Áudio e pacote final — prova nativa delimitada

O roteiro de áudio final durou 18,36 s e acionou mudo com Space e um passo de
volume com seta no controle focado. O serviço real confirmou cada efeito no
mesmo alvo observado. O teste restaurou exatamente o mudo e os valores brutos
dos canais originais, confirmou o fechamento por Escape e o foco no botão da
barra, e liberou os dispositivos virtuais. Houve duas intenções de escrita
pela interface e zero retries. A prova guarda apenas resultados e observações
tipadas; nomes de dispositivos e valores privados permanecem em memória.
Isso comprova efeito/readback nessa configuração, sem causalidade exclusiva
ou garantia de compare-and-swap. A seleção de outra saída permanece UNRUN.
O primeiro roteiro de áudio parou na guarda de hover antes de qualquer clique
ou escrita; seu resultado foi preservado.

A instrumentação temporária foi removida após essas provas. Os pacotes finais
correspondem ao Source `204c16b` e mantêm a correção da janela. A verificação
após recarga confirmou os seis itens da barra, dock, launcher, atalhos,
configuração e banco de recuperação preservados. Essa recarga verifica pacote
e composição instalada; não repete a prova de interação sem instrumentação.

Após a prova de 13/10, ainda faltavam transferência com popup aberto, retirada
da entrada da barra, seleção de saída, microfone, brilho, rede, Não perturbe,
múltiplos docks/monitores e os demais critérios CC0/CC1/T1. Um install ou PASS
offscreen não encerra esses gates.

### Transferência e entrada opcional — correção e prova em 14/10

O primeiro episódio encontrou uma falha: um pedido pela barra chegou com o
popup da dock ainda visível, fechou-o, mudou o host e reabriu no topo, mas a nova
abertura logo se encerrou. O backend anterior ainda tinha uma referência Qt
válida quando o seguinte terminou de ser criado. O resultado foi preservado;
o caminho inverso e a desativação ficaram UNRUN nesse episódio. Os pacotes e
configurações foram restaurados antes de corrigir o Source.

A reprodução com o `Loader` real no Qt 6.11.2 mostrou que `item` fica null e
`Component.onDestruction` ocorre antes da destruição efetiva do QObject. Assim,
contar apenas esses callbacks pode ocultar sobreposição. A sessão agora captura
uma referência tipada ao backend nativo antes de fechar e espera sua liberação.
Também espera o diálogo anterior ficar invisível e inativo antes de mudar o host.
As retomadas são enfileiradas por sinais; não foi acrescentado um delay em ms.
O backend pode ser recriado, enquanto popup, view e estado de áudio permanecem
os mesmos. Backends injetados persistentes não participam dessa barreira opcional.

| Verificação da correção `38e2b6c` | Resultado |
|---|---|
| Registry + Session + composição, Qt 6.11.2/Fusion | 61 PASS, zero skips/warnings |
| Mesma bateria, `org.kde.desktop` | 61 PASS, zero skips/warnings |
| Regressões novas | Backend ainda vivo; cancelamento; destruição do dono; janela oculta ainda ativa |
| Revisão independente | Pedido sucessor durante destruição e diálogo sem API `active`: PASS |
| Design e pacote | Check, sete guards, build e galeria claro/escuro revisada: PASS |

As regressões de backend vivo e janela oculta/ativa falharam antes das respectivas
guardas. Testes sintéticos não certificam comportamento do compositor.

Galeria da correção, com dados sintéticos e sem mudança de composição visual:

| Escuro | Claro |
|---|---|
| ![Central escura](../screenshots/shared-control-center/transfer-dark.png) | ![Central clara](../screenshots/shared-control-center/transfer-light.png) |

O episódio nativo seguinte, com a correção, passou em Plasma 6.7.5/Wayland e
Qt 6.11.2, numa tela de 2648 × 1490 DIP; os itens observados reportaram DPR 2.
O intervalo entre o início do input e o fechamento final foi de 269,55 s:

- Dock → barra → dock: os dois pedidos chegaram com popup e diálogo ainda
  visíveis. Cada mudança de host ocorreu após `closed`, invisibilidade,
  inatividade e liberação do backend anterior. A referência foi liberada enquanto
  o diálogo ainda estava ativo nas duas transferências; a segunda guarda impediu
  reabrir nesse intervalo. Ambas as novas aberturas permaneceram visíveis, com
  âncora/transient parent corretos e as mesmas referências de popup/view/áudio.
- Cinco criações e cinco inícios de destruição de backend, máximo de um span
  `completed` → início de destruição. Nenhuma referência ao backend anterior
  estava presente no `completed` seguinte; ao final ela estava null e o áudio
  inativo. Isso qualifica os QObjects observados, não todas as conexões, threads
  ou recursos globais de áudio.
- Desativar apenas `showControlCenter` do applet direito por `writeConfig` e
  `reloadConfig` do Plasma preservou a abertura originada pela dock, fechou a
  abertura da barra e permitiu reabrir pela dock enquanto a entrada estava
  desligada. A preferência foi restaurada ao valor original; todas as demais
  configurações e os bancos permaneceram iguais. O checkbox na janela de
  configuração não foi exercitado neste episódio.
- Tab focou o volume; Escape fechou sem escritas. O item de foco do painel ficou
  no botão da dock e o KWin voltou à janela própria de teste. Não se afirma que
  o painel foi reativado nem que houve nova reabertura pelo teclado.
- Zero setters/retries; leitura real confirmou default, alvo, mudo e valores
  brutos dos canais inalterados. Não houve seleção de saída ou outra operação
  de hardware, acesso ao clipboard ou captura de dados pessoais.

A instrumentação foi removida e somente os três arquivos da correção ficaram
instalados: dock com 67 arquivos e barra com 14. Launcher, CLI, atalhos,
configurações e recuperação permaneceram preservados; o Plasma terminou ativo,
com resultado success e zero restarts. Os helpers e dispositivos próprios foram
encerrados. Essa recarga confirma o pacote final, sem repetir a interação após
remover o probe.

Transferência e desativação têm esse aceite delimitado. Permanecem abertos o
checkbox nativo, seleção de saída, transferência durante operação de áudio
pendente, outros monitores/ambientes e os demais critérios CC0/CC1/T1.

### Encaixe dos controles na barra — 14/10

O painel real tem 32 pontos de altura, com uma área útil de 24 para os applets.
Os botões exigiam 28/32 mesmo nessa área menor. A regressão reproduziu o
excesso; o Source `800a9c8` limita as alturas de layout ao espaço recebido e
reduz o padding vertical para preservar o ícone e o texto. O indicador de erro
também tem altura limitada. A preferência continua 28/32; o mínimo anunciado
ao Plasma passa a 24, sem modificar a configuração do painel.

A ordem da leitura em `controlHeight` é deliberada: uma reprodução independente
com o BarHarness real, Qt 6.11.2 e ambos os estilos encontrou binding loop no
startup ao ler `height` antes de `implicitHeight`. Ler `implicitHeight` primeiro
eliminou os avisos. As falhas iniciais e as variantes privadas foram preservadas;
o mecanismo interno de inicialização permanece uma inferência.

| Verificação do Source final | Resultado |
|---|---|
| Barra, Fusion / KDE | 33 PASS em cada estilo, sem warnings |
| Composição compartilhada, Fusion / KDE | 7 PASS em cada estilo |
| Alturas 24/28/32/64, normal e compacta | Controles e ícones contidos; texto do menu cabe |
| Teclado em host curto | Menu Space/Escape, Tab para Central, Space e clique inferior |
| Design | Check, sete guards e galeria claro/escuro revisada: PASS |
| Revisão independente | Source e preparação nativa: zero bloqueadores |

Capturas offscreen com dados sintéticos, foco na Central e host de 24 pontos:

| Escuro | Claro |
|---|---|
| ![Barra curta escura](../screenshots/shared-control-center/bar-fit-dark.png) | ![Barra curta clara](../screenshots/shared-control-center/bar-fit-light.png) |

O episódio nativo passou em uma sessão Plasma 6.7.5/Wayland:

- Menu Orla e Central mediram 32 × 24, dentro do host. O ícone do menu mediu
  20 × 20; o canvas da Central, 24 × 20, com desenho centralizado pelo menor
  lado. Todos os 19 registros observados mantiveram controle e canvas contidos.
- Um clique por controle em `y=27`, junto à borda inferior, produziu exatamente
  um callback `clicked` e abriu seu popup. Tab/Escape na Central e ↓/Escape no
  menu fecharam ambos. Ao final, o foco lógico do menu ficou em seu botão e o
  KWin voltou à mesma janela própria; isso não prova reativação do painel.
- Não houve uso de clipboard, screenshots, ações de sessão ou acionamento de
  controles de hardware. Os quatro helpers de input confirmaram liberação dos
  dispositivos; a janela própria encerrou com código zero e os scripts KWin
  próprios foram removidos.
- O consumidor inicialmente presumiu ordem cronológica do journal. Os
  registros chegaram invertidos; ordenar pela sequência de cada contexto
  corrigiu a leitura, sem repetir input. Também foi preservada uma falha do
  audit ao exigir exit zero do journal vazio; a leitura final estava vazia,
  sem erro em stderr e com exit 1. Não se encontraram avisos de BarView no PID
  do episódio; isso não é uma auditoria de todos os logs do Plasma.

A retirada do probe deixou exatamente os dois arquivos de produção da barra,
com 14 arquivos no pacote. Dock, launcher, CLI, atalhos, mapas/modos das
configurações e bancos ficaram iguais. Plasma terminou ativo, com success e
zero restarts; a geometria final confirmou painel 32/hosts 24. Essa recarga
confirma o pacote sem repetir a interação após retirar o probe.

Preferência compacta na UI nativa, entrada por teclado/anel de foco na barra,
fontes ampliadas, esquema claro nativo, outras telas/escalas e os demais gates
de T1/UX0 permanecem UNRUN. O conteúdo do indicador de erro não foi exercitado
na sessão real.

### Dock retrátil e retorno ao aplicativo — 14/10

Uma nova prova com o Source `8f730b8`, sem instalar ou alterar código de UI,
usou KWrite 26.08.1 real com perfil XDG, D-Bus e arquivo sintético próprios.
A tela observada mediu 2648 × 1490 DIP; as capturas mediram 3840 × 2160 pixels.
O painel gerenciado continuou em `autohide`. Um observador temporário do KWin
leu apenas os PIDs conhecidos, UUIDs, frames, foco, ponteiro e o getter público
`hidden`; não alterou janelas, painéis ou preferências.

Com o KWrite maximizado, o mesmo painel passou de `hidden=true` para
`hidden=false` após um gesto contínuo na borda inferior. A captura confirmou
vidro e ícones. O dispositivo temporário permaneceu ativo durante essa parte;
o bridge contém pausas de 120 ms entre movimentos relativos, mas o log desta
sessão não mede a cadência recebida pelo KWin.

Um clique no ícone da Central abriu uma janela de aproximadamente 378 × 542
DIP, centralizada sobre esse botão. O recorte confirmou o título estático
“Central de Controle”, sem registrar mídia ou nomes de dispositivos. Escape
ocultou essa superfície e devolveu foco ao mesmo UUID do KWrite. Após uma
leitura fresca do aplicativo ativo, Ctrl+End, um marcador próprio, Enter e
Ctrl+S produziram exatamente marcador + LF uma vez: 45→67 bytes. Afastar o
ponteiro voltou a ocultar o painel; `hidden=true` e o recorte vazio concordaram.

| Recorte da sessão real | Captura |
|---|---|
| Dock revelada sobre aplicativo próprio maximizado | [Vidro e ícones](../screenshots/shared-control-center/native-dock-reveal.png) |
| Dock oculta após afastar o ponteiro | [Região novamente livre](../screenshots/shared-control-center/native-dock-hidden.png) |
| Popup aberto pelo botão da dock | [Título da Central](../screenshots/shared-control-center/native-dock-cc-heading.png) |

Em fullscreen, F11 manteve o mesmo aplicativo ativo e o gesto na borda deixou
o painel em `hidden=true`, com região vazia. Isso é compatível com
[a política de bordas de clientes do KWin 6.7.5](https://raw.githubusercontent.com/KDE/kwin/v6.7.5/src/screenedge.cpp),
que bloqueia esse caso. A configuração em disco foi lida sem alterações:
delay 75 ms, cooldown 350 ms e pushback 1; seu estado carregado no compositor
não foi lido. Revelar a dock sobre fullscreen, como desejado para o Orla,
continua sem implementação qualificada. O teste não habilitou preferências
para contornar essa limitação.

Os dois probes anteriores ficaram inconclusivos: região vazia ou indicador
de aproximação não comprovavam revelação. Artefatos e erros iniciais foram
preservados; o contraste posterior não atribui retrospectivamente uma causa
às tentativas anteriores. A leitura do código de borda justificou o novo gesto,
sem alterar configuração nem produto.

O bridge contínuo encerrou pelo TTL antes do envio do marcador: seu log tem
dez comandos executados, nenhum de digitação e liberação confirmada. O arquivo
permanecia igual ao preimage; a prova do marcador usou um novo bridge e leitura
fresca de foco. Sete episódios de input confirmaram liberação; os dezesseis
observadores próprios foram descarregados. KWrite voltou ao frame original
antes da limpeza supervisionada; ele e seu D-Bus privado terminaram com exit 0.
BEFORE e AFTER ficaram exatos nos 1.363 arquivos e 232 diretórios protegidos
verificados, incluindo Source, instalação, configurações e bancos de layout.
A revisão independente não encontrou bloqueadores neste aceite delimitado.

R1/CC0/CC1-A/T1/UX0 permanecem parciais. Esta prova não exercitou hardware,
transferência pela barra, os demais popups, foco por Tab nos controles, esquema
claro nativo, outra escala/tela, perfil normal do usuário ou menus do T3.

## Hidden dialog keyboard ownership — 15 October 2026

The production four-opening fixture reproduced a blocked second Control Center
opening. Giving the host actual keyboard focus did not fix the old gate:
`QGuiApplication.focusWindow()` was the host, while the hidden native dialog
still reported `active=true` and `activeFocusItem=null`. Conversely, during hide
the dialog could still own keyboard focus and retain a non-null focus item.
Private signal traces recorded both states without changing production UI.

This agrees with [Qt 6.11's `QWindow::isActive()` contract](https://doc.qt.io/qt-6.11/qwindow.html#isActive):
activity includes the parent/transient family. The Session now uses the native
QQuickWindow's `activeFocusItem` for this keyboard barrier and wakes its deferred
queue when that item clears. A visible native dialog still blocks transfer;
an undefined focus-item property keeps the existing active-only fallback for
older boundaries. Generation checks, backend retirement and newer-focus rules
are unchanged. This is a fix for this dialog flow, not a universal equivalence
between QML item focus and compositor focus.

Two causal regressions failed before the fix and passed after it. The portable
case holds a hidden dialog with non-null focus despite `active=false`, then
allows one transfer after null focus despite `active=true`. The production
fixture establishes exact host keyboard ownership before each opening and
retains its original placement, 40 ms wait, lifecycle, Tab and Escape assertions.
It opens settings and Control Center twice each.

Locally, `test_qml`, `test_shared_control_center_registry`,
`test_control_center_session` and `test_shared_control_center` passed 91 entries
per Fusion/KDE style: 88 passed and three skipped. Qt/PySide6 were 6.11.2. Design
check, seven design guards and the 68-file applet build passed. These are
offscreen/fixture results; they do not qualify real Plasma host transfers,
multiple outputs or focus return in the user's session. The earlier failed
popup result remains historical evidence. Private RED, GREEN, signal traces,
review and regression receipts are under `.runtime/popup-diagnosis-20261015/`.

The tested 68-file package was installed with a backup and one controlled shell
stop/start. Only `ControlCenterSession.qml` changed in the applet. Readback
confirmed package hashes, the full configuration map, inventory, protected
files and the same resident launcher. This installation result alone is not
physical popup/focus qualification.

### Installed opening, Escape and reopening

After installation, a fresh physical-input episode passed two openings and two
Escape closes in Plasma 6.7.5/Wayland, Qt 6.11.2, one output at scale 1.45. Each
opening first revealed the auto-hide dock through its existing bottom edge.
Accessibility located `controlCenterButton` inside the owned panel, then both
`controlCenterContents` and its `controlCenterAllAction` descendant with positive
geometry. The pane measured 318 × 449 DIP in both openings. No title, media or
device names were read or captured.

Before each Escape, a fresh KWin observation confirmed the active window belonged
to the known Plasma process while both CC markers were showing. Both markers
became non-showing after Escape. The dock hid again after the final pointer
departure, and the last observed active-window UUID equaled the initial UUID.
Full configuration bytes/map, package, inventory, protected files and the
resident launcher remained unchanged. Temporary input devices, accessibility
flags, observer and bus resources were released or restored.

Earlier attempts remain failed: one queried Component geometry on already-hidden
accessible nodes, which no longer implement that interface; another completed
one CC/Escape cycle but did not reveal the auto-hide panel before reopening.
The final reader asks for geometry only when showing, and the same bounded edge
sequence is used before both clicks. No production change or preference change
was made to accommodate either test issue.

This qualifies those two dock-origin openings and closes. It does not establish
native lifecycle/setter counts, independent keyboard-owner identity, the KWin
popup window's identity/absence, bar-to-dock transfer, backend actions, other
outputs or schemes. Final receipt:
`.runtime/popup-diagnosis-20261015/root-native-r3/RESULT.json`, status
`PASS_INSTALLED_CC_OPEN_ESCAPE_REOPEN_ESCAPE`. The final regenerated dark/light
CC gallery captures were visually reviewed and are byte-identical to the
[published dark](../screenshots/visual-system/popup-dark-control-center.png) and
[light](../screenshots/visual-system/popup-light-control-center.png) captures.

## Newer host focus after native popup close — 15 October 2026

A separate Settings popup defect was reproduced offscreen and in an isolated
real Wayland/KWin session. A synchronous public `closed` observer established
`QGuiApplication.focusWindow() == host` and `host.activeFocusItem() == addButton`.
After the observer returned, DockPopup's deferred callback moved focus back to
the old Settings anchor. Both failed receipts retain the actual keyboard-owner
and focus-item observations. This controlled reentrant schedule does not claim
to reproduce ordinary physical pointer timing in the installed panel.

`DockPopup` now invalidates restoration on visibility, anchor and host changes.
Its deferred callback requires the original live window/anchor, the same closed
opening, and no distinct live focused control. Synchronous cancellation remains
authoritative: the shared Session clears `anchorControl` in `closed`, suppressing
the generic callback during Control Center transfers. The design system records
this focus contract for future UI contributions.

The same Wayland challenge passed after the fix: the new control remained focused
and the old anchor did not regain focus. `test_qml` includes the causal regression.
The dock, Registry, Session and composition suites passed 92 entries per
Fusion/KDE style (89 passed, three TaskManager skips). Design check, seven guards,
gallery and the 68-file applet build passed. The four Settings/Control Center
captures are byte-identical to the pre-fix local gallery; the current Settings
captures below were visually reviewed in both schemes.

| Dark | Light |
|---|---|
| ![Settings dark](captures/popup-focus-dark-settings.png) | ![Settings light](captures/popup-focus-light-settings.png) |

An additional Source-owned Wayland fixture passed dock → bar → dock requests
through the canonical Entry/Session while the old dialog was still visible and
owned keyboard focus. Public signal observations verified `closed`, native hide
and exact keyboard departure before each host change. The same popup/view/audio
state/dialog remained, the transient parent matched each requested window, and a
newer control chosen during final close retained focus. Audio/actions were
synthetic: their call lists stayed empty, and the native audio loader was absent.
Real audio backend QObject lifetimes/setters and the installed session's exact
keyboard-owner identity remain unqualified by this fixture.

Two early transfer-fixture attempts remain failed. The diagnostic identified a
Python conversion failure reading the typed `contents` QML alias; checking that
alias's actual identity in QML fixed the observer without changing the product.
Private receipts are under `.runtime/cc-transfer-20261015/`: Settings RED/GREEN
in `root-focus-probe-r1/r2`, transfer diagnosis in `r3/r4` and the passing
transfer fixture in `r5`. The final Source status is
`PASS_SOURCE_WAYLAND_TWO_WAY_CC_TRANSFER_AND_NEWER_FOCUS`.

The tested package was installed with backup and one controlled shell stop/start.
Only `DockPopup.qml` changed among the 68 applet files. Readback confirmed the
complete configuration map, panel inventory, protected files and resident launcher
preserved. This installation is separate from the physical interaction evidence.

### Installed public rehosting and Tab

After installation, a fresh episode passed three physical entry clicks in the
order dock → bar → dock. Each opening had one positive-geometry CC pane and inner
action at the requested panel region. A physical Tab was followed by a changed
`STATE_FOCUSED` technical control under that pane. Escape closed the final popup,
and the dock hid after pointer departure. Full configuration bytes/map, dock and
bar packages, exact bar roles, inventory, protected files and launcher were
preserved. Temporary input devices, accessibility flags, observer and bus resources
were released/restored. Automatic locking remains disabled.

The first physical attempt also reached all three hosts and focused controls,
but failed before final Escape: moving to the current cursor position emitted no
new motion event. Cleanup hit the same observer error. An independent guarded
episode closed only the owned CC popup and verified rehide, resources and full
preservation. The revised reader skips that redundant move, still requires a
fresh one-pixel nudge and all keyboard/context guards, and passed the complete
flow on a new baseline. The failed receipt remains failed.

This proves public rehosting and the observed Tab consequences in one installed
Plasma/Wayland output. It does not prove old visibility at request acceptance,
queued transfer ordering, exact `QGuiApplication.focusWindow()`/keyboard-seat
ownership, or real backend lifecycle/setter counts. No unique KWin popup match
was available, so that identity remains unqualified. Source-owned Wayland facts
above remain separate. Final status:
`PASS_INSTALLED_CC_PUBLIC_REHOSTING_AND_TECHNICAL_TAB`, receipt
`.runtime/cc-transfer-20261015/root-native-r2/RESULT.json`; independent cleanup:
`root-independent-cleanup-r1/RESULT.json`.

## Native audio pending transfer — 15 October 2026

`tests/native/run_control_center_audio.py` now provides a reproducible isolated
Wayland/KWin, D-Bus and PipeWire session for the production Control Center.
`control_center_audio.py` loads the existing dock/bar fixtures, keeps their fake
settings actions and replaces only the audio override with QML `null`. That
activates the actual `NativePulseAudio` loader and PlasmaPA client. It neither
installs code nor sends input to the installed desktop.

The private PipeWire configuration loads no ALSA, Bluetooth, network, device
enumeration or session-manager modules. Its only outputs are two
`support.null-audio-sink` nodes, explicitly advertised with `node.virtual=false`.
This is a synthetic protocol descriptor: PlasmaPA derives `virtualDevice` from
the Pulse hardware flag, which PipeWire supplies when `node.virtual` is false.
The production eligibility filter is unchanged. These fixtures certify no
physical device. The mapping was checked against
[PulseAudioQt 1.8.1](https://raw.githubusercontent.com/KDE/pulseaudio-qt/v1.8.1/src/device_p.h),
[PipeWire 1.6.9's node classification](https://raw.githubusercontent.com/PipeWire/pipewire/1.6.9/src/modules/module-protocol-pulse/manager.c)
and [its Pulse sink flags](https://raw.githubusercontent.com/PipeWire/pipewire/1.6.9/src/modules/module-protocol-pulse/pulse-server.c).

The fresh process uses an explicit private Pulse socket, client configuration
with autospawn disabled, a private PipeWire core, four private XDG directories
and an unavailable system bus. The runner captures Source hashes, compares
known host configuration/package file hashes and modes, and releases only
processes matching its UID, birth time and unique runtime marker through pidfds.
Output directories cannot be reused; unsafe path characters are rejected before
creation. It redacts the home path from owned logs after process cleanup.

The native fixture establishes a pending 80% volume gesture and accepts the
canonical bar request in one JS frame, before pumping Qt events. It observes:

- Pending request and gesture cleared before `aboutToHide`, and again before
  the transfer call returns.
- The actual backend `QObject.destroyed` signal before changing host and
  publishing its successor. A null loader item is recorded separately and
  does not count as destruction.
- Late real readback of 80%, independently checked with `pactl` on the private
  server, without any old confirmation, non-null event presentation or
  accessibility announcement.
- A new 60% request confirmed once, one event presentation and one announcement;
  the independent server readback is 39,322 raw on both channels. Queue occupancy
  alone is not used to infer a single HUD history.
- Return to the dock with the same view and `AudioControlState`, then final
  close. Three backend QObjects were published and three destroyed, with at
  most one published backend alive. Counters and observer errors are checked
  through engine teardown.

Fusion and `org.kde.desktop` runs passed with Qt/PySide6 6.11.2, KWin/PlasmaPA
6.7.5, PulseAudioQt 1.8.1 and PipeWire 1.6.9. Each ended with zero QML warnings,
zero lifecycle violations, no tracked live backend and no owned process left;
the host file fingerprints and Source hashes remained equal. The 76 portable
audio/Session/Registry checks passed in each style. Design check reported zero
issues and all seven design guards passed. No product UI, token or geometry
changed, so this increment reuses the existing visual captures.

The runner and its fixtures require the Source-only bar, so the alpha bundle
excludes all four new native-audio files. The release test reproduced their
accidental inclusion before the exclusion and passed after it, retaining its
byte-for-byte repeat-build and checksum assertions. Published assets are unchanged.

A private negative control removed only `beginClose()`'s audio invalidation.
The same native test failed with `audio_not_cancelled_before_close`, despite
eventual cancellation and otherwise successful readback; cleanup still passed.
This establishes sensitivity to the pre-close ordering regression. No mutation
was applied to the working tree or installed applet.

An earlier attempt remains failed: assigning Python `None` to the QML `var`
override produced `undefined`, so the real backend was never loaded. Assigning
actual JS `null` corrected the fixture. This was not a reproduced product bug.
Private receipts live under `.runtime/cc-audio-20261015/`; the public runner's
two JSON results distinguish probe failure from supervisor/cleanup failure.

This closes the isolated real-protocol fixture gap. It does not qualify an audio
operation pending during transfer in the installed panel, physical input,
physical hardware, native setter counts, all PulseAudioQt global connections or
threads, other outputs, or the complete CC0/CC1/T1 acceptance. The current applet
installation and public 0.2.9 assets were not changed in this increment.
