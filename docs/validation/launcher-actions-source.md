# Launcher: painel completo de ações

O botão **Ações** e **Ctrl+K** abrem todas as ações anunciadas pelo resultado selecionado, na ordem do provedor. O menu mostra resultado e origem, mantém os textos limitados e oferece rolagem e foco visível. ↑/↓ navegam; Enter ou clique executam somente a ação escolhida. Escape ou Ctrl+K fecham primeiro o menu, preservando busca e seleção; outro Escape fecha o launcher. Resultados sem ações mantêm o botão desativado.

O menu usa `QtQuick.Templates.Menu/MenuItem` com `Popup.Item`, os tokens existentes e o protocolo de execução já presente. Controladores, provedores e barreira de fechamento mantêm suas implementações. Cada pressionamento guarda o ticket e o episódio do menu: callbacks antigos não podem executar depois de fechar, reabrir, mudar a consulta ou sair para IA/Steam. Não há callback de foco enfileirado após o fechamento.

## Verificação Source e visual

Código do painel: `ef8efd5`; divisão dos testes e CI: `1b8791e`. Qt 6.11.2 e KDE Frameworks 6.30. Os testes exercitam doze ações com rótulos longos em 440/660 px, terceira ação por Enter, última ação por clique e rolagem por teclado até o último item. Navegar não executa; callbacks antigos são recusados e os três donos de trabalho continuam respeitando o fechamento.

Todos os 19 métodos Qt Test permanecem cobertos: quinze na suíte geral e quatro de ações/fechamento, com conjuntos disjuntos e união completa. As duas suítes mantêm o watchdog de 30 segundos. A suíte agregada antiga chegava a 29,97 s no KDE; após acrescentar cobertura, excedeu 30 s duas vezes. Os registros desses timeouts foram preservados. A divisão corrige a falta de margem sem aumentar o watchdog ou retirar casos. A CI confere os oito CTests e executa os testes da seleção isolada.

Na versão imutável compilada para a instalação local, os oito CTests passaram com Fusion (99,62 s) e `org.kde.desktop` (101,94 s). Os testes do seletor isolado passaram (2); o design check não encontrou problemas e os sete testes de design passaram. Os testes usam dados sintéticos, D-Bus/XDG privados e renderização offscreen; não qualificam sessão Wayland, contas, provedores externos ou isolamento de rede.

Foram revisadas 24 capturas: Fusion/KDE × esquema do sistema claro/escuro × 440/660 px × primeiro/terceiro/último foco. O launcher permanece escuro em ambos os esquemas do sistema, conforme o design system.

| Captura sintética | Captura |
|---|---|
| Fusion, sistema escuro, 660 px | [Menu de ações](../screenshots/launcher-actions/actions-dark-660.png) |
| KDE, sistema claro, 440 px | [Menu estreito](../screenshots/launcher-actions/actions-light-440.png) |
| KDE, doze ações, último foco em 440 px | [Rolagem e foco](../screenshots/launcher-actions/actions-long-kde-440.png) |

## Instalação e prova nativa delimitada — 14/10/2026

A instalação local troca somente o caminho do ELF no wrapper do launcher e reinicia `orla-launcher.service`. A versão compilada corresponde a `1b8791e`, com 287 arquivos-fonte conferidos e cópia de runtime sem permissão de escrita. O serviço ficou ativo, sem reinícios automáticos, executando o ELF esperado. Os 1.353 guards de arquivos e 231 guards de diretórios permaneceram exatos; CLI, applets, bancos de layout e configurações não foram substituídos. Dono de Meta, teclas, padrões e owner de KGlobalAccel foram iguais antes/depois. As rotas de recuperação tiveram 16 testes privados; o coletor, oito. Não foi provocado um rollback na sessão real.

Na sessão Wayland, uma tela com escala 1,45, Meta ativou o PID do launcher instalado e a busca encontrou o Dolphin. O arquivo de aplicativo instalado não anuncia ações extras: Ctrl+K não abriu menu e o botão desativado foi observado. Para a prova do menu, a consulta `1-1` ofereceu a ação real da calculadora. Ctrl+K abriu o menu; após ↓, a única ação disponível manteve foco visível; o primeiro Escape fechou somente o menu, preservando visualmente consulta e resultado. O segundo Escape devolveu o foco à mesma janela própria maximizada, confirmado pelo UUID no KWin e pelo estado de foco do Qt, enquanto o processo da fixture permanecia vivo.

Uma fixture anterior expirou antes da medição final de foco; essa medição ficou inconclusiva e foi preservada. A prova final usou uma nova fixture com prazo maior. As duas fixtures encerraram e foram reaproveitadas **zero** vezes; dez observadores próprios do KWin foram descarregados e oito episódios de input confirmaram liberação dos dispositivos temporários. A conferência final de ELF, atalhos e arquivos protegidos passou.

| Captura da versão instalada | Captura |
|---|---|
| Busca de aplicativo por Meta | [Dolphin](../screenshots/launcher-actions/native-query.png) |
| Menu real da calculadora | [Ação e foco](../screenshots/launcher-actions/native-actions.png) |
| Primeiro Escape preserva consulta e resultado | [Busca novamente focada](../screenshots/launcher-actions/native-menu-closed.png) |

Enter/clique sobre uma ação real, janela anterior de terceiro, fullscreen, dois monitores, mudança assíncrona durante o menu e todas as rotas nativas de fechamento continuam UNRUN nesta prova. Não houve lançamento de aplicativo, cópia para clipboard, chamada de IA ou alteração de contexto. L0/L2/UX2 permanecem parciais; favoritos, aliases, comandos internos e o setup completo seguem no roadmap. A próxima prova verifica continuidade com aplicativo anterior comum/fullscreen; depois, autohide e popups do dock no mesmo cenário.

## Retorno a aplicativo real comum e fullscreen — 14/10/2026

Uma nova prova delimitada usou KWrite 26.08.1 real na sessão Wayland, com arquivo sintético próprio, perfil XDG e D-Bus privados. O mesmo PID e UUID permaneceram nas treze observações do KWin. A conferência de Source correspondeu a `a9336dc2a0cdf398895b2edd29086750cd5a0bcb`; esta prova não instalou uma nova versão do launcher.

Na janela comum, Meta abriu o launcher; a consulta `1-1` mostrou o resultado da calculadora. Ctrl+K abriu o menu e ↓ manteve foco na única ação real disponível. O primeiro Escape fechou o menu, preservando visualmente consulta e resultado, com foco novamente na busca. O segundo Escape ocultou o launcher e devolveu o foco ao mesmo UUID do KWrite, ainda comum. O ciclo foi repetido após F11, com o mesmo UUID em fullscreen; o retorno preservou `fullScreen=true`. Ao terminar, F11 restaurou `fullScreen=false` antes de encerrar o aplicativo próprio.

O destino do input também foi verificado. Após cada retorno, uma leitura fresca confirmou o KWrite próprio ativo; Ctrl+End, um marcador ASCII único, Enter e Ctrl+S acrescentaram exatamente marcador + LF ao arquivo sintético. O primeiro recibo confirmou 45→65 bytes; o segundo partiu desses mesmos 65 bytes e confirmou 65→85. Cada marcador apareceu uma vez, sem repetir digitação ou salvamento. Enter e Ctrl+S foram usados no editor: não exercitaram dispatch de ação do launcher nem clipboard.

Os quatorze episódios de input confirmaram liberação dos dispositivos temporários, sem falha de limpeza. Os treze observadores próprios do KWin foram descarregados. A limpeza supervisionada encerrou somente KWrite e seu D-Bus privado, ambos com exit 0, sem erros ou sinais enviados a processos alheios; não foi expiração espontânea. AFTER e BEFORE ficaram exatamente iguais para os 1.361 guards de arquivos e 232 de diretórios conferidos, incluindo Source, launcher, Plasma e os roots protegidos conhecidos. Isso não representa uma auditoria de todos os arquivos da máquina. A revisão independente não encontrou bloqueadores de overclaim nesse escopo.

| Recorte da versão instalada, comum e fullscreen | Captura |
|---|---|
| Menu da calculadora | [Ação e foco](../screenshots/launcher-actions/native-kwrite-menu.png) |
| Primeiro Escape | [Consulta e resultado preservados](../screenshots/launcher-actions/native-kwrite-menu-closed.png) |

Os recortes do launcher são idênticos nos dois casos; o estado comum/fullscreen do aplicativo anterior foi confirmado pelos observadores, não pela imagem do launcher.

O aceite é `PASS_BOUNDED`: continuidade do foco e input salvo na instância própria do KWrite, comum/fullscreen, com perfil e bus privados. O menu nativo tinha uma ação; navegação entre várias ações reais, Enter/clique para dispatch, clipboard, perfil normal do usuário, instância preexistente, menus do T3, vários monitores, isolamento de rede e provedores externos permanecem UNRUN. O stderr do KWrite foi descartado, portanto seus avisos nativos permanecem UNKNOWN. L0/L2/UX2 continuam parciais; esta prova não fecha R1 nem W1. Autohide e popups do dock no mesmo cenário têm episódio e aceite separados.
