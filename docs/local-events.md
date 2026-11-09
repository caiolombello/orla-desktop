# Avisos locais / Local events

## Português

Na alpha 0.2.7 publicada, o dock oferece um único aviso local para a conclusão
de uma etapa de foco ou pausa do Pomodoro. O recurso é experimental, global e
desligado por padrão. Abra **Widgets** e ative **Mostrar conclusões do Pomodoro
dentro do dock (global)** para exibi-lo. Esta preferência é salva separadamente
das regras de perfil; ela vale para os perfis e para as preferências anteriores.
As notificações do KDE continuam independentes.

O aviso aparece dentro de uma área do dock, por até oito segundos, com texto
simples e ação para fechar. Usa as cores e a preferência de movimento reduzido
da aparência atual. Em larguras menores, o conteúdo é resumido ou encurtado; se
não houver ao menos 48 pixels para a área do aviso, o dock não ativa a
apresentação integrada. No menor espaço aceito, o indicador e o botão de fechar
continuam separados e o alvo de fechar permanece disponível. O espaço reservado
pode reduzir a área visível dos apps no centro do dock.

Desativar a opção limpa somente o aviso local e mantém o Pomodoro e seu prazo.
Se os dados do perfil estiverem inválidos ou forem de uma versão incompatível,
o dock preserva esses dados sem corrigi-los e não mostra o aviso local; a
conclusão usa o aviso existente do dock. Widgets, ordem e prazo do timer não são
transferidos para o estado do aviso. Não há regra por perfil para este evento.

Este incremento não substitui, lê ou envia eventos ao Centro de Notificações do
KDE. Outros eventos, HUD, ilha, histórico e comportamento por perfil ainda não
estão incluídos. A validação disponível usa fixtures offscreen e não qualifica
painel Plasma, foco/grab, leitor de tela, escala, múltiplos monitores ou
instalação. Consulte o [registro de validação](validation/local-events-0.2.7.md) e a [release publicada](https://github.com/caiolombello/orla-desktop/releases/tag/v0.2.7).

### Ilha no topo (Source)

Depois da 0.2.11, os mesmos avisos (conclusão do Pomodoro e confirmações de
áudio) podem aparecer numa cápsula preta no centro do topo da tela, como a ilha
do iPhone, em vez de ocupar uma área do dock. Ative **Mostrar esses avisos no
topo da tela, como uma ilha (global)** em **Widgets**; as duas opções acima
continuam decidindo quais avisos aparecem. A ilha mostra um ícone, o título e
um detalhe curto; o volume mostra uma barra de nível. Ela fica sobre o meio da
barra de menus, não recebe foco nem cliques, some ao expirar e não reserva
espaço no dock, então também funciona num dock estreito demais para a área do
aviso. A cor é sempre preta, nos esquemas claro e escuro.

#### Atividades ao vivo (Source)

Com **Mostrar na ilha a música, o Pomodoro e o microfone ou a câmera em uso
(global)**, a ilha também mostra o que está acontecendo agora, como a Dynamic
Island do iPhone:

- **Pomodoro em andamento:** fase e tempo restante. Tem prioridade sobre a
  música.
- **Música tocando:** capa, título e barras animadas. Ao pausar, a música fica
  mais 15 segundos para dar tempo de retomar.
- **Microfone ou câmera em uso:** ícone laranja (microfone) ou verde (câmera),
  como no macOS. Ocupa a ilha só quando nada mais está ativo; senão vira um
  ícone pequeno no fim da cápsula.
- **Próxima reunião:** de 10 minutos antes até 5 minutos depois do início de um
  evento com horário (eventos de dia inteiro não contam), vinda do mesmo plugin
  da agenda do dock e só com os eventos da agenda ligados. Tem prioridade sobre
  tudo. A cápsula compacta mostra só "Em 5 min"; o título aparece ao expandir,
  para não ficar à mostra numa tela compartilhada.
- **Avisos de bateria:** "Carregando" ao ligar o carregador e "Bateria fraca" ao
  cair para 20% e para 10%, com a barra de nível em verde, âmbar ou vermelho
  (UPower, em tempo real). Um celular pareado pelo KDE Connect avisa ao cair
  para 20% e 10%.

Um aviso (Pomodoro concluído, volume) toma a ilha enquanto dura e depois a
devolve. Um clique na ilha expande a atividade: a música ganha capa, progresso
e anterior/tocar/próxima (clicar na capa abre o player); o Pomodoro ganha pausar
e reiniciar; a privacidade lista o que está em uso. Um clique no fundo ou tirar
o ponteiro de cima recolhe. Um clique num aviso o dispensa. A ilha nunca recebe
o foco do teclado; os mesmos controles continuam acessíveis pelo teclado nos
popups do dock.

O microfone conta quando há uma gravação ativa no Plasma-PA que não seja um
medidor de nível ou mixer. A câmera não tem API de sessão: conta quando um
processo do usuário mantém um dispositivo V4L2 aberto (verificado com `fuser` a
cada 4 segundos, só com a opção ligada). Apps que usam a câmera pelo PipeWire
aparecem como o PipeWire segurando o dispositivo.

#### Janela

Na sessão Wayland, a ilha é uma superfície layer-shell (LayerShellQt) na camada
superior, ancorada no topo, que o KWin centraliza. A superfície tem o tamanho
da cápsula: só a cápsula recebe cliques, o resto da tela continua normal. Ela
cresce na hora e encolhe depois da animação. Janelas em tela cheia a cobrem,
como o macOS esconde a barra de menus. Fora do Wayland, a ilha usa a janela de
notificação do Plasma, sem receber entrada: mostra avisos e atividades
compactas, mas não expande. O tipo de exibição na tela (OSD) foi descartado: o
KWin o recoloca no centro, a dois terços da altura. Ainda não há prova com dois
monitores, escala fracionária, troca de tela ou sessão bloqueada (N2).

## English

The published 0.2.7 alpha adds one local dock notice for completion of a
Pomodoro focus or break period. It is experimental, global and off by default.
Open **Widgets** and enable **Mostrar conclusões do Pomodoro dentro do dock
(global)** to display it. This preference is saved separately from profile
rules and applies across profiles, including the previous flat preferences.
KDE notifications remain independent.

The notice appears inside the dock for up to eight seconds, uses plain text and
has a close action. Its colors and reduced-motion behavior follow the current
appearance. At narrower widths, the content is shortened; if the dock cannot
reserve at least 48 pixels for the notice, the integrated presentation stays
off. At the minimum supported width, the indicator and close action remain
separate and the close target stays available. The reserved space may reduce
the visible app area in the center of the dock.

Turning the option off clears only the local notice and preserves the Pomodoro
and its deadline. If profile data is invalid or from an unsupported version,
the dock preserves it without repair and does not show the local notice; timer
completion uses the existing dock notice. Widget state, ordering and timer
deadline are not copied into event state. Per-profile rules for this event are
not included.

This increment does not replace, read from or send events to KDE's Notification
Center. Other events, HUD, island, history and per-profile behavior are not
included. Available validation uses offscreen fixtures and does not qualify the
Plasma panel, focus/grabs, screen reader, scaling, multi-monitor behavior or
installation. See the [validation record](validation/local-events-0.2.7.md) and the [published release](https://github.com/caiolombello/orla-desktop/releases/tag/v0.2.7).

### Top island (Source)

After 0.2.11, the same notices (Pomodoro completion and audio confirmations)
can appear in a black capsule at the top center of the screen, like the
iPhone's island, instead of taking a slot in the dock. Enable **Mostrar esses
avisos no topo da tela, como uma ilha (global)** under **Widgets**; the two
options above still decide which notices appear. The island shows an icon, the
title and a short detail; volume shows a level bar. It sits over the middle of
the menu bar, takes no focus or clicks, fades out when it expires and reserves
no dock space, so it also works on a dock too narrow for the notice slot. It is
always black, in light and dark schemes.

#### Live activities (Source)

With **Mostrar na ilha a música, o Pomodoro e o microfone ou a câmera em uso
(global)**, the island also shows what is happening right now, like the
iPhone's Dynamic Island:

- **Running Pomodoro:** phase and time left. It outranks music.
- **Playing music:** cover, title and animated bars. A paused track stays for
  15 more seconds so it can be resumed.
- **Microphone or camera in use:** an orange (microphone) or green (camera)
  icon, as on macOS. It takes the island only when nothing else is live;
  otherwise it becomes a small icon at the capsule's end.
- **Next meeting:** from 10 minutes before to 5 minutes after a timed event
  starts (all-day events never count), read through the dock calendar's
  plugin and only with calendar events on. It outranks everything. The compact
  capsule shows only "Em 5 min"; the title appears when expanded, so it is not
  on display on a shared screen.
- **Battery notices:** "Carregando" when the charger is plugged in and "Bateria
  fraca" when the level drops to 20% and to 10%, with the level bar in green,
  amber or red (UPower, live). A phone paired through KDE Connect notifies at
  20% and 10%.

A notice (Pomodoro done, volume) takes the island over while it lasts, then
gives it back. A click expands the activity: music gets cover, progress and
previous/play/next (clicking the cover raises the player); the Pomodoro gets
pause and reset; privacy lists what is in use. A click on the background or
moving the pointer away folds it back. A click on a notice dismisses it. The
island never takes keyboard focus; the same controls stay keyboard-reachable
in the dock popups.

The microphone counts when Plasma-PA has an active recording stream that is
not a level meter or mixer. The camera has no session API: it counts when a
process of the user holds a V4L2 device open (checked with `fuser` every 4
seconds, only with the option on). Apps using the camera through PipeWire show
up as PipeWire holding the device.

#### Window

In a Wayland session the island is a layer-shell surface (LayerShellQt) on the
top layer, anchored to the top edge, which KWin centers. The surface is the
capsule's size: only the capsule takes clicks and the rest of the screen is
untouched. It grows at once and shrinks after the animation. Fullscreen
windows cover it, as macOS hides its menu bar. Outside Wayland the island uses
Plasma's notification window without input: it shows notices and compact
activities but does not expand. The on-screen-display type was dropped: KWin
moves it to the center, two thirds down the screen. Two monitors, fractional
scaling, screen changes and the locked session are not proven yet (N2).
