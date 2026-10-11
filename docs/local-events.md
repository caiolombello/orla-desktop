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
