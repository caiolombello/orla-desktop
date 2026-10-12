# Menu Orla — experimental optional bar component

[Português](#português) · [English](#english)

## Português

O **Menu Orla (experimental)** é um applet separado (`org.orla.bar`, versão 0.1.0) para **Plasma 6.7.x**. É o primeiro componente da barra opcional, disponível somente no checkout de código. **Não está nos assets publicados da release 0.2.5.** O dock continua independente.

### O que o código oferece

- Botão com ícone próprio Orla ou sem ícone, label configurável e opção de mostrar o nome do aplicativo ativo.
- Nome em texto simples e limitado; preserva a apresentação desde o início da abertura do menu até seu fechamento completo. Aplicativo ativo sem nome aparece como **Aplicativo**; sem aplicativo ativo, **Área de trabalho**. Não mostra o título do documento/janela.
- Ações explícitas de informações do sistema, configurações do KDE e configuração deste applet. Sobre o sistema abre o módulo nativo de informações da distribuição.
- Bloquear, suspender, sair, reiniciar e desligar conforme as capacidades disponíveis. Navegação e hover não executam ações. Sair/reiniciar/desligar usam `ForcePrompt` para solicitar confirmação nativa; envio aceito não comprova que a ação terminou e não há retry automático.

A ponte privada `org.kde.plasma.private.sessions` fica em um componente isolado por Loader. Os adaptadores nativos só são carregados em hosts identificados como 6.7.x; fora dessa faixa, ficam indisponíveis. As APIs/fontes foram verificadas em Plasma 6.7.5, Qt 6.11.2, Fedora 44. A faixa 6.7.x é um limite do código, não uma matriz nativa validada.

### Instalação manual opcional

Requer uma sessão Plasma 6.7.x e `kpackagetool6`. Estes comandos são instruções para uma instalação iniciada por você; **instalação no usuário e uso real no painel ainda não foram testados**. Na raiz do checkout:

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

Não há instalador Orla, preset de barra superior ou autostart para este componente. Menu Global, bandeja e relógio serão widgets KDE nativos separados; a composição com eles ainda não foi qualificada. Central de Controle e aplicativos recentes permanecem no roadmap.

### Testes e limites

Com Python 3/PySide6 e Qt Quick Controls instalados, na raiz do checkout:

```sh
python3 bar/run_tests.py
# Opcional, com o estilo KDE instalado:
python3 bar/run_tests.py --style org.kde.desktop
```

O wrapper executa dez testes com backends injetados, Qt offscreen/software, diretórios XDG temporários e endereços D-Bus próprios indisponíveis. Não instancia os adaptadores nativos nem executa ações de sessão. Fusion/KDE passaram, e uma revisão independente repetiu dez testes KDE e aprovou publicação experimental do código. Quatro componentes compilaram sem erros e sem instanciação nativa; isso não prova comportamento real.

**UNRUN:** diálogos nativos/Cancelar, ações reais, abertura de configurações, gestos/foco/grab, applet completo em painel, dois monitores e composição com widgets irmãos. T1/T2/T3 continuam abertos. Veja o [roadmap](../ROADMAP.md).

## English

**Orla Menu (experimental)** is a separate applet (`org.orla.bar`, version 0.1.0) for **Plasma 6.7.x**. It is the first optional bar component, available only in the source checkout. **It is excluded from the published 0.2.5 release assets.** The dock remains independent.

### What the source provides

- An Orla icon or text-only menu button, configurable label and optional active application name.
- A bounded plain-text application name, preserved from the start of menu opening until it fully closes. An unnamed active application shows **Aplicativo**; no active application shows **Área de trabalho**. Document/window titles are not displayed.
- Explicit system information, KDE settings and applet configuration actions. System information opens KDE's distribution information module.
- Capability-aware lock, suspend, logout, reboot and shutdown. Hover/navigation performs no action. Logout/reboot/shutdown use `ForcePrompt` to request native confirmation; accepted dispatch does not prove completion, and there is no automatic retry.

The private `org.kde.plasma.private.sessions` bridge is isolated behind a Loader. Native adapters load only on hosts identified as 6.7.x; outside that range they stay unavailable. Sources/APIs were checked against Plasma 6.7.5, Qt 6.11.2, Fedora 44. The 6.7.x guard is a code boundary, not a validated native version matrix.

### Optional manual installation

Requires a Plasma 6.7.x session and `kpackagetool6`. These instructions describe a user-initiated install; **installation in the user's account and real panel use remain untested**. From the checkout root:

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

There is no Orla installer, top bar preset or autostart for this component. Global Menu, tray and clock are future native KDE sibling widgets; their composition remains unqualified. Control Center and recent applications remain on the roadmap.

### Tests and limits

With Python 3/PySide6 and Qt Quick Controls installed, from the checkout root:

```sh
python3 bar/run_tests.py
# Optional, with the KDE style installed:
python3 bar/run_tests.py --style org.kde.desktop
```

The wrapper runs ten injected-backend tests with offscreen/software Qt, temporary XDG directories and unavailable owned D-Bus addresses. It does not instantiate native adapters or execute session actions. Fusion/KDE passed; independent review repeated ten KDE tests and approved experimental source publication. Four components compiled without errors, without native instantiation; this does not prove real behavior.

**UNRUN:** native dialogs/Cancel, real actions, opening settings, human gestures/focus/grab, the full applet in a panel, two monitors and sibling-widget composition. T1/T2/T3 remain open. See the [roadmap](../ROADMAP.md).


A barra no fonte oferece **Mostrar nome do menu**, **controles compactos (28 px)**
e o preset **Aplicar estilo inspirado no Mac**. O preset mantém o texto
personalizado e permite alterar cada controle depois. Os menus usam a janela
transiente do Qt e abrem abaixo do botão, com visual próprio e navegação por
teclado. Os 16 testes isolados passaram; foco e posição no Wayland dependem da
validação no painel real. A composição completa da barra e sua Central de
Controle continuam em andamento.
