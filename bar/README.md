# Menu Orla — experimental optional bar component

[Português](#português) · [English](#english)

## Português

O **Menu Orla (experimental)** é um applet separado (`org.orla.bar`, versão 0.1.0) para **Plasma 6.7.x**. É o primeiro componente da barra opcional, disponível somente no checkout de código. **Não está nos assets publicados das releases 0.2.5–0.2.11.** O dock continua independente.

### O que o código oferece

- Botão com ícone próprio Orla ou sem ícone, label configurável e opção de mostrar o nome do aplicativo ativo. **Mostrar nome do menu**, **controles compactos (28 px)** e **Aplicar estilo inspirado no Mac** preservam o texto personalizado e permitem editar cada controle depois.
- Nome em texto simples e limitado; preserva a apresentação desde o início da abertura do menu até seu fechamento completo. Aplicativo ativo sem nome aparece como **Aplicativo**; sem aplicativo ativo, **Área de trabalho**. Não mostra o título do documento/janela.
- Ações explícitas de informações do sistema, configurações do KDE e configuração deste applet. Sobre o sistema abre o módulo nativo de informações da distribuição.
- **Recentes**: até cinco aplicativos usados há pouco, com ícone, como os "Itens recentes" do menu Apple. A lista vem do modelo de uso recente do KDE (o mesmo do menu de aplicativos), carregado só no Plasma 6.7.x e só enquanto o Menu Orla está ativo. Clicar abre o aplicativo pelo ID do arquivo `.desktop` mostrado, mesmo que a ordem mude. O KDE só registra o uso quando há uma Activity atual.
- **Forçar encerramento…**: aciona o "Matar janela" do KWin (o mesmo de Ctrl+Alt+Esc); o próximo clique escolhe a janela, e Esc cancela.
- **Atualizações…** (U3): mostra o estado que o notificador do Discover informa, num selo como o do menu Apple: **Disponíveis**, **Segurança**, **Reiniciar**, **Instalando…** ou **Sem rede**. A barra lê os itens registrados na bandeja do KDE (`StatusNotifierWatcher`), só enquanto o Menu Orla está ativo e de novo a cada abertura. O Discover só registra o item quando há algo a avisar, então sem selo a barra não afirma que o sistema está atualizado. Clicar aciona a mesma ação do ícone do Discover na bandeja: a página de atualizações ou o pedido de reinício. Sem o ícone, abre o Discover na página de atualizações. A barra não conta, baixa nem instala pacotes.
- **Downloads do Steam…**: aparece só com o Steam aberto (o item dele na bandeja) e abre `steam://open/downloads`. O progresso dos jogos fica no Steam; a atualização do próprio Orla continua em **Sobre Orla Desktop** e no guia de updates.
- Bloquear, suspender, sair, reiniciar e desligar conforme as capacidades disponíveis. Navegação e hover não executam ações. Sair/reiniciar/desligar usam `ForcePrompt` para solicitar confirmação nativa; envio aceito não comprova que a ação terminou e não há retry automático.

A ponte privada `org.kde.plasma.private.sessions` fica em um componente isolado por Loader. Os adaptadores nativos só são carregados em hosts identificados como 6.7.x; fora dessa faixa, ficam indisponíveis. As APIs/fontes foram verificadas em Plasma 6.7.5, Qt 6.11.2, Fedora 44. A faixa 6.7.x é um limite do código, não uma matriz nativa validada.

### Instalação manual opcional

Requer uma sessão Plasma 6.7.x e `kpackagetool6`. A atualização foi testada em um painel real no Fedora 44, Plasma 6.7.5/Wayland; outros ambientes e a primeira instalação continuam sem qualificação. Na raiz do checkout:

```sh
kpackagetool6 -t Plasma/Applet -i bar
```

Depois, adicione **Menu Orla (experimental)** pela interface Adicionar Widgets do Plasma em um painel escolhido por você. Altura, monitor e posição pertencem à configuração do painel KDE. Este applet não cria nem modifica painéis automaticamente.

Para atualizar uma instalação existente do mesmo applet, ou removê-lo intencionalmente:

```sh
kpackagetool6 -t Plasma/Applet -u bar
# Remova primeiro o widget do painel:
kpackagetool6 -t Plasma/Applet -r org.orla.bar
```

### Barra gerenciada — código experimental, sem release

Os comandos abaixo são para um checkout que contenha o helper experimental de layout; não estão disponíveis nos bundles publicados até 0.2.11. A composição gerenciada ainda requer qualificação nativa. A CLI separada compõe Menu Orla, Menu Global, espaçador, bandeja e relógio KDE. O template [mac-inspired-topbar.json](../layouts/mac-inspired-topbar.json) propõe um painel superior de 32 px, translúcido e compacto, com áudio/rede nativos na bandeja. O módulo opcional `control-center`, desativado no template, acrescenta uma entrada à direita que usa a mesma Central e o estado do dock. Essa rota ainda exige qualificação na sessão real. Há modos `dock-plus-bar` e `dock-only`; `bar-only` não é suportado. O dock é gerenciado independentemente.

Requer o checkout completo do helper (`scripts/orla.py`, `caiodock.py`, `panel_layout.py`, `panel_layout_update.py` e `panel_layout.js`), Menu Orla e os widgets KDE selecionados instalados, Python 3, `gdbus`, `systemctl` e **Plasma 6.7.5**. Todos os subcomandos exigem `--service`: informe o nome literal do serviço Plasma do usuário atual, cuja identidade/processo/configuração o helper verifica; não há escolha automática de serviço.

Instale ou atualize primeiro o applet pelo fluxo manual acima (`-i bar` ou `-u bar`); o helper não o instala. Na raiz do checkout completo clonado, substitua o serviço abaixo pelo serviço verificado. `status` lê o inventário e o recibo, sem alterar painéis; `python3 scripts/orla.py doctor` verifica as dependências gerais do dock, não substitui esse inventário. Copie o template e edite `screen.connector` (substitua **SELECT-MONITOR** pelo conector real), `replacePanelIds` (IDs explícitos dos painéis desse monitor a substituir) e, se necessário, `reuseWidgetIds` (IDs explícitos de widgets compatíveis desses painéis a preservar). O template não pode ser aplicado sem essas escolhas; um painel que contém o dock é recusado.

```sh
PLASMA_SERVICE='<verified-current-user-Plasma.service>'
python3 scripts/orla.py layout status --service "$PLASMA_SERVICE"
cp layouts/mac-inspired-topbar.json my-topbar.json
# Edite my-topbar.json antes de planejar:
python3 scripts/orla.py layout plan --service "$PLASMA_SERVICE" --manifest my-topbar.json --output my-topbar-plan.json
# Revise o plano salvo e os IDs antes de aplicar:
python3 scripts/orla.py layout apply --service "$PLASMA_SERVICE" --plan my-topbar-plan.json
```

`plan` salva um plano privado sem mudar os painéis. `apply` substitui somente os painéis selecionados, cria a barra gerenciada e guarda backups/recibo privados; reinicia o serviço Plasma selecionado nas etapas de backup/verificação. Não instala o applet ou o launcher. Mudança de inventário, identidade ou configuração pode ser recusada, sem autorização para sobrescrever o estado divergente.

Use o caminho **receipt.json** informado pelo helper, que é atualizado após cada operação. As ações abaixo têm efeitos distintos:

```sh
RECEIPT='<private-receipt-path-printed-by-apply>'
# Voltar a dock-only: remover somente a barra Orla gerenciada:
python3 scripts/orla.py layout disable --service "$PLASMA_SERVICE" --receipt "$RECEIPT"
# Restaurar explicitamente o layout original anterior ao apply:
python3 scripts/orla.py layout restore --service "$PLASMA_SERVICE" --receipt "$RECEIPT"
```

`disable` preserva os demais painéis/dock e os dados de recuperação; não recria os painéis substituídos. `restore` recupera o layout original com seus backups verificados. Se apply falhar após a mutação, o helper tenta restaurar o layout anterior e registra o resultado no recibo; falha nessa recuperação mantém os backups e exige inspeção. Transações de layout interrompidas não são repetidas automaticamente. O helper pode tentar reiniciar o serviço uma única vez quando confirma o limite de partidas de um serviço conhecido e anteriormente saudável, com o processo anterior verificado. Outras falhas exigem inspeção do recibo e, para recuperação de uma transação interrompida, `restore --recover` explícito. A recuperação de um disable interrompido pode restaurar a barra gerenciada ativa, em vez do layout original.

### Adicionar a Central à barra existente

A primeira operação experimental de atualização aceita uma barra gerenciada
ativa com recibo original v1 e bandeja seguida pelo relógio. Ela acrescenta
somente a entrada da Central entre esses módulos, preservando o painel,
os widgets existentes e suas configurações atuais.

```sh
python3 scripts/orla.py layout plan-update --service "$PLASMA_SERVICE" --receipt "$RECEIPT" --add control-center --output my-topbar-update.json
# Revise o plano, os IDs, a tela e o estado atual antes de atualizar:
python3 scripts/orla.py layout update --service "$PLASMA_SERVICE" --plan my-topbar-update.json
```

`plan-update` lê o estado atual e salva o plano privado. `update` reinicia o
serviço nas etapas de verificação e informa um **novo** caminho de recibo;
use esse caminho nas operações seguintes. O backup original permanece
imutável. Um banco separado do estado anterior ao update permite desfazer
uma falha dessa atualização. Mudanças externas posteriores podem impedir a
recuperação automática; os bancos ficam preservados para inspeção.

`restore --recover` de um update interrompido recupera a composição anterior
ao update. `restore` de um update concluído recupera o layout original somente
quando isso preserva as configurações externas à barra. O helper recusa
sobrescrever dados divergentes. Recibos de update exigem este helper novo;
helpers anteriores os recusam. A qualificação da entrada na sessão real,
incluindo foco, âncora e áudio, permanece separada dos testes do helper.

Em 12/10/2026, o helper final sem modificações passou apply → disable → restore normal do layout original → novo plan/apply em uma tela Plasma 6.7.5/Wayland com DPR 2. Disable manteve somente o dock independente; o restore recuperou os painéis originais; reaplicar terminou com a barra gerenciada e a ordem dos cinco módulos verificada. A observação visual confirmou relógio sem data e dock oculto com o cursor afastado. Nenhum novo crash foi observado nesse ciclo. Crashes intermitentes anteriores em desligamentos/reinícios rápidos do Plasma continuam um risco experimental separado; a proteção contra o limite de partidas não comprova sua correção.

Menu Global depende de aplicativos que exportem menus; áudio/rede usam controles nativos da bandeja. A Central compartilhada experimental exige uma única Orla Dock compatível; a entrada da barra fica indisponível sem esse dono. Ações reais de sessão, ações de menus de aplicativos, áudio/rede, a rota da Central na barra, outros ambientes, múltiplos monitores e o aceite completo de T1–T4 continuam abertos. A prova do Menu Orla abaixo cobre o applet isolado.

### Testes e limites

Com Python 3/PySide6 e Qt Quick Controls instalados, na raiz do checkout:

```sh
python3 bar/run_tests.py
# Opcional, com o estilo KDE instalado:
python3 bar/run_tests.py --style org.kde.desktop
```

O wrapper executa 18 testes com backends injetados e um teste opcional do adaptador de janela PlasmaCore, quando o módulo está instalado. Usa Qt offscreen/software, diretórios XDG temporários e endereços D-Bus próprios indisponíveis; não executa ações reais de sessão. Os 19 testes passaram em Fusion e KDE, com revisão independente do código. O adaptador nativo usa uma janela Plasma para o menu, aberto abaixo do botão, e uma dica separada, evitando que a dica cubra o botão em um painel estreito.

Em 12/10/2026, um teste real no painel superior comprovou hover, clique, menu completo, duas aberturas e navegação com ↓/Escape em um monitor com DPR 2. Retorno de foco entre aplicativos, ações reais/diálogos de confirmação, vários monitores, RTL, outras escalas e o aceite completo dos módulos/matriz permanecem sem qualificação. T1/T2 continuam parciais; T3/T4 permanecem abertos. Veja o [roadmap](../ROADMAP.md).

## English

**Orla Menu (experimental)** is a separate applet (`org.orla.bar`, version 0.1.0) for **Plasma 6.7.x**. It is the first optional bar component, available only in the source checkout. **It is excluded from the published 0.2.5–0.2.11 release assets.** The dock remains independent.

### What the source provides

- An Orla icon or text-only menu button, configurable label and optional active application name. **Show menu label**, **compact controls (28 px)** and **Apply Mac-inspired style** preserve custom text and allow each control to be edited afterwards.
- A bounded plain-text application name, preserved from the start of menu opening until it fully closes. An unnamed active application shows **Aplicativo**; no active application shows **Área de trabalho**. Document/window titles are not displayed.
- Explicit system information, KDE settings and applet configuration actions. System information opens KDE's distribution information module.
- **Atualizações…** (U3) shows the state KDE's Discover notifier reports, in a badge like the Apple menu's: available, security, restart, installing or offline. The bar reads the items registered in KDE's tray (`StatusNotifierWatcher`), only while the Orla Menu is enabled and again each time it opens. Discover registers its item only when it has something to report, so no badge is not a claim that the system is up to date. Choosing it triggers Discover's own tray action (its updates page or the restart prompt); without the item, Discover opens on its updates page. The bar never counts, downloads or installs packages.
- **Downloads do Steam…** appears only while Steam runs (its tray item) and opens `steam://open/downloads`. Game progress stays in Steam; Orla's own update stays under **Sobre Orla Desktop** and the updates guide.
- Capability-aware lock, suspend, logout, reboot and shutdown. Hover/navigation performs no action. Logout/reboot/shutdown use `ForcePrompt` to request native confirmation; accepted dispatch does not prove completion, and there is no automatic retry.

The private `org.kde.plasma.private.sessions` bridge is isolated behind a Loader. Native adapters load only on hosts identified as 6.7.x; outside that range they stay unavailable. Sources/APIs were checked against Plasma 6.7.5, Qt 6.11.2, Fedora 44. The 6.7.x guard is a code boundary, not a validated native version matrix.

### Optional manual installation

Requires a Plasma 6.7.x session and `kpackagetool6`. Updating the applet was tested in a real Fedora 44, Plasma 6.7.5/Wayland panel; other environments and first installation remain unqualified. From the checkout root:

```sh
kpackagetool6 -t Plasma/Applet -i bar
```

Then add **Orla Menu (experimental)** through Plasma's Add Widgets interface to your chosen panel. Height, monitor and position are configured by the KDE panel. This applet does not create or modify panels automatically.

To update an existing installation of this applet, or intentionally remove it:

```sh
kpackagetool6 -t Plasma/Applet -u bar
# Remove the widget from its panel first:
kpackagetool6 -t Plasma/Applet -r org.orla.bar
```

### Managed bar — experimental source, unreleased

These commands require a checkout containing the experimental layout helper; they are unavailable in the published bundles through 0.2.11. Managed composition still requires native qualification. The separate CLI composes Orla Menu, KDE Global Menu, spacer, tray and clock widgets. The [mac-inspired-topbar.json](../layouts/mac-inspired-topbar.json) template proposes a 32 px translucent, compact top panel with native audio/network tray controls. Its optional `control-center` module, disabled in the template, adds a right-side entry using the dock's existing view and state; native qualification of that route remains open. Recent applications remain planned. Modes are `dock-plus-bar` and `dock-only`; `bar-only` is unsupported. The dock is managed independently.

Requires the complete helper checkout (`scripts/orla.py`, `caiodock.py`, `panel_layout.py`, `panel_layout_update.py` and `panel_layout.js`), installed Orla Menu and selected KDE widgets, Python 3, `gdbus`, `systemctl` and **Plasma 6.7.5**. Every subcommand requires `--service`: provide the literal current-user Plasma service name, whose identity/process/configuration the helper verifies; there is no automatic service selection.

First install or update the applet using the manual flow above (`-i bar` or `-u bar`); the helper does not install it. From the complete cloned checkout root, replace the service below with the verified service. `status` reads inventory and the receipt without changing panels; `python3 scripts/orla.py doctor` checks general dock dependencies and does not replace this inventory. Copy the template and edit `screen.connector` (replace **SELECT-MONITOR** with the actual connector), `replacePanelIds` (explicit IDs of panels on that monitor to replace) and, if needed, `reuseWidgetIds` (explicit compatible widget IDs from those panels to preserve). The template cannot be applied without those choices; a panel containing the dock is refused.

```sh
PLASMA_SERVICE='<verified-current-user-Plasma.service>'
python3 scripts/orla.py layout status --service "$PLASMA_SERVICE"
cp layouts/mac-inspired-topbar.json my-topbar.json
# Edit my-topbar.json before planning:
python3 scripts/orla.py layout plan --service "$PLASMA_SERVICE" --manifest my-topbar.json --output my-topbar-plan.json
# Review the saved plan and IDs before applying:
python3 scripts/orla.py layout apply --service "$PLASMA_SERVICE" --plan my-topbar-plan.json
```

`plan` saves a private plan without changing panels. `apply` replaces only selected panels, creates the managed bar and retains private backups/a receipt; it restarts the selected Plasma service during backup/verification steps. It does not install the applet or launcher. Inventory, identity or configuration drift can be refused, without permission to overwrite divergent state.

Use the **receipt.json** path printed by the helper, which is updated after each operation. These actions have different effects:

```sh
RECEIPT='<private-receipt-path-printed-by-apply>'
# Return to dock-only: remove only the managed Orla bar:
python3 scripts/orla.py layout disable --service "$PLASMA_SERVICE" --receipt "$RECEIPT"
# Explicitly restore the original layout from before apply:
python3 scripts/orla.py layout restore --service "$PLASMA_SERVICE" --receipt "$RECEIPT"
```

`disable` retains other panels/the dock and recovery data; it does not recreate replaced panels. `restore` recovers the original layout from verified backups. If apply fails after mutation, the helper attempts to restore the previous layout and records the outcome in the receipt; failed recovery retains backups and requires inspection. Interrupted layout transactions are not repeated automatically. The helper may retry starting the service once when it confirms the startup limit for a known, previously healthy service with a verified prior process. Other failures require receipt inspection and, to recover an interrupted transaction, explicit `restore --recover`. Recovering an interrupted disable may restore the active managed bar rather than the original layout.

### Add Control Center to an existing bar

The first experimental update accepts an active managed bar with its original
v1 receipt and adjacent tray/clock modules. It adds the Control Center entry
between them, retaining the panel, existing widgets and current settings.

```sh
python3 scripts/orla.py layout plan-update --service "$PLASMA_SERVICE" --receipt "$RECEIPT" --add control-center --output my-topbar-update.json
# Review the plan, IDs, screen and current state before updating:
python3 scripts/orla.py layout update --service "$PLASMA_SERVICE" --plan my-topbar-update.json
```

Planning writes only a private plan. Updating restarts the selected service
at verification stages and prints a **new** receipt path; use that path for
subsequent operations. The original bank stays immutable, while a separate
pre-update bank supports rollback. Later external changes can prevent automatic
recovery; all banks remain available for inspection.

For an interrupted update, `restore --recover` recovers the pre-update
composition. For a completed update, `restore` recovers the original layout
only when doing so preserves settings outside the bar. Divergent user data
causes refusal. Update receipts require this new helper; older helpers refuse
them. Native bar routing, positioning, focus and audio have separate gates.

On 2026-10-12, the unmodified final helper passed apply → disable → normal original-layout restore → fresh plan/apply on one Plasma 6.7.5/Wayland screen at DPR 2. Disable retained only the independent dock; restore recovered the original panels; reapply committed the managed bar with the five-module order verified. Visual observation confirmed the clock without a date and the dock hidden with the cursor away. No new crash was observed in this cycle. Earlier intermittent crashes during rapid Plasma shutdown/restart remain a separate experimental risk; the startup-rate guard does not establish their resolution.

Global Menu depends on applications exporting menus; audio/network use native tray controls. The experimental shared Control Center requires one compatible Orla Dock owner; its bar entry is unavailable without that owner. Real session actions, application-menu actions, audio/network, the shared bar route, other environments, multiple monitors and complete T1–T4 acceptance remain open. The Orla Menu check below covers the separate applet.

### Tests and limits

With Python 3/PySide6 and Qt Quick Controls installed, from the checkout root:

```sh
python3 bar/run_tests.py
# Optional, with the KDE style installed:
python3 bar/run_tests.py --style org.kde.desktop
```

The wrapper runs 18 injected-backend tests and an optional PlasmaCore window-adapter test when the module is installed. It uses offscreen/software Qt, temporary XDG directories and unavailable owned D-Bus addresses; it executes no real session actions. All 19 tests passed in Fusion and KDE, with independent Source review. Production uses a Plasma menu window opening below the button and a separate tooltip so feedback does not cover the button in a short panel.

On 2026-10-12, a real top-panel check verified hover, clicking, the complete menu, two openings and Down/Escape navigation on one DPR 2 monitor. Across-application focus return, real actions/confirmation dialogs, multiple monitors, RTL, other scales and complete module/matrix acceptance remain unqualified. T1/T2 remain partial; T3/T4 remain open. See the [roadmap](../ROADMAP.md).
