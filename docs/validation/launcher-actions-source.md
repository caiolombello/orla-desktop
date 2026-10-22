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
