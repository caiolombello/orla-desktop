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

Ainda qualificar transferência com popup aberto, retirada da entrada da barra,
seleção de saída, microfone, brilho, rede, Não perturbe, múltiplos docks/monitores
e os demais critérios CC0/CC1/T1. Um install ou PASS offscreen não encerra
esses gates.
