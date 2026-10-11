# Audio HUD / HUD de áudio

## Português

O código atual oferece confirmações breves de áudio dentro do dock. Em
**Personalizar Orla Dock → Widgets**, ative **Mostrar confirmações de áudio
dentro do dock**. A opção começa desligada e é independente em cada perfil.
Dados de perfis anteriores são preservados até uma alteração explícita.

O HUD confirma volume, mudo e saída padrão alterados pela Central de Controle
do Orla. Ele aparece somente depois de o serviço aceitar a alteração e
informar o valor correspondente. Mudanças externas, ações recusadas e erros
de conexão não geram uma confirmação de sucesso. Alterações sucessivas do
mesmo controle atualizam o aviso existente; a confirmação expira em 1,8 segundo.

As conclusões do Pomodoro mantêm sua preferência global separada e duração
de até oito segundos. Desativar somente o HUD de áudio preserva esses avisos.
Textos acompanham o tema, usam movimento reduzido quando escolhido e têm uma
ação para fechar. Sem avisos, a área de eventos fica oculta e não reserva
espaço. Um aviso aparece temporariamente sobre a extremidade direita do dock,
sem alterar sua largura ou a posição de rolagem. O aviso não pede foco; ao
fechá-lo pelo teclado, o foco pode retornar ao controle anterior do dock.

Widgets de música, bateria e integrações ficam como ícones compactos quando
não têm dados úteis. Continuam clicáveis e acessíveis pelo teclado, com o
estado completo no tooltip. Dados úteis disponíveis, inclusive dados
explicitamente desatualizados, recuperam a apresentação ampla sem substituir
o controle focado. A dock
mantém rolagem horizontal e revela o item focado, sem uma barra persistente.

Este incremento pertence ao código atual; os arquivos já publicados da
release 0.2.9 permanecem inalterados. Testes determinísticos e revisão
independente cobrem confirmação, expiração, perfis, agrupamento e anúncios
de acessibilidade. Hardware, leitor de tela e comportamento em vários
monitores ainda precisam de validação. Ele não substitui as notificações nem
o OSD do KDE e não observa teclas globais de volume.

## English

The current source offers brief audio confirmations inside the dock. Under
**Personalizar Orla Dock → Widgets**, enable **Mostrar confirmações de áudio
dentro do dock**. It starts disabled and is independent for each profile.
Older saved profile data is preserved until an explicit change.

The HUD confirms volume, mute and default-output changes made through Orla's
Control Center, only after the service accepts the change and reports the
matching value. External changes, rejected actions and connection errors do
not produce success confirmations. Repeated changes update the same notice;
an audio confirmation expires after 1.8 seconds.

Pomodoro completions retain their separate global preference and up to eight
seconds of visibility. Disabling audio feedback preserves those notices.
Notices follow the theme and reduced-motion preference and have a dismiss
action. With no notice, the event surface stays hidden and reserves no space.
A notice temporarily overlays the right end of the dock without changing its
width or scroll position. Arrival does not request focus; keyboard dismissal
can restore focus to the previous dock control.

Music, battery and integration widgets use compact icons when useful data
is absent. They remain clickable and keyboard accessible, with their complete
status in the tooltip. Useful available data, including explicitly stale data,
restores the wide presentation without replacing the focused control. Horizontal scrolling and
focus reveal remain available without a persistent scrollbar.

This increment belongs to the current source; published 0.2.9 assets remain
unchanged. Deterministic tests and independent review cover confirmation,
expiry, profiles, grouping and accessibility announcements. Hardware, screen
readers and multiple monitors still require validation. The HUD preserves
KDE's notifications and OSD and does not observe global volume keys.
