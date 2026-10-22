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
