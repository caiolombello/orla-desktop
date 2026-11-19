# `layout status` no Plasma 6.8.3

**Data:** 19/11/2026. **Ambiente:** Fedora 44, Plasma 6.8.3, KF6 6.32, Qt 6.11.2, Wayland, uma tela.
**Commit verificado:** branch `feat/layout-status-plasma-6-8`.

## O que mudou

`layout status` passa a ler o inventário dos painéis no Plasma 6.8.3. Os demais
subcomandos (`plan`, `apply`, `plan-update`, `update`, `disable`, `restore`) e a
janela de composição continuam exigindo 6.7.5, com a mesma mensagem de recusa.
O script do Plasma lê o inventário em 6.7.5 ou 6.8.3 e recusa todas as outras
operações fora de 6.7.5.

## Por que só a leitura

O diff de `shell/scripting` do plasma-workspace entre `v6.7.5` e `v6.8.3` mantém
o setter de `widget.index` (remove o ID e limita a `order.length() - 1`). Mas
`Containment.addWidget(widget)`, usado para mover a bandeja e o relógio
reaproveitados, passou a transferir a posse do applet. `screenpool.cpp`,
`shellcorona.cpp` e `panelview.cpp` foram reescritos em grande parte, e
`containment.cpp` mudou no libplasma. Sem um ciclo nativo apply → disable →
restore → reaplicar em 6.8.3, essas operações continuam bloqueadas.

## Verificação

- Testes offscreen:
  - `test_panel_layout*`: 181 testes.
  - `test_workspace*` com Fusion e org.kde.desktop.
  - `test_package_cli`.
  - Os quatro testes novos falham no código anterior.
- Leitura ao vivo:
  - Backups dos dois arquivos de configuração e do estado de layouts.
  - `layout status --service plasma-plasmashell.service` terminou com código 0.
  - O PID do serviço e `NRestarts=0` não mudaram, e os hashes de `plasma-org.kde.plasma.desktop-appletsrc`, `plasmashellrc` e `current.json` ficaram iguais.
  - Os painéis e as telas lidos coincidem com o `activeInventory` do recibo de outubro (desconsiderando a versão).

## Achado: o recibo de outubro não pode mais ser desativado nem restaurado

O recibo ativo (schema 2, `COMMITTED`) foi criado em 6.7.5. `disable` e `restore`
exigem que os dois arquivos de configuração sejam byte a byte iguais ao snapshot
`after`. Desde outubro, o próprio Orla mudou grupos desse arquivo:

- configurações do dock (`Containments/32/Applets/34/Configuration/General`);
- formato do relógio da barra (`menu_bar_clock`/`macos_look`);
- itens da bandeja e `lastScreen`.

Portanto o recibo é recusado em qualquer versão do Plasma, não só no 6.8.3. A
barra gerenciada continua funcionando; o que falta é uma decisão de projeto
sobre se `disable` deve aceitar mudanças fora do painel gerenciado e mudanças
feitas pelas próprias ferramentas do Orla, em vez de comparar o arquivo inteiro.

## Não executado

- Nenhum `plan`, `apply`, `update`, `disable` ou `restore` ao vivo em 6.8.3.
- Nenhum reinício do Plasma, nenhuma captura de tela.
