# Orla Launcher — componente opcional experimental

Janela Qt Quick própria para aplicativos e calculadora locais, usando as APIs públicas de KRunner. Digitar consulta; Enter ou clique executa a seleção. ↑/↓ navegam, Tab alcança as ações e Esc limpa/cancela e fecha. Calculadora oferece a ação explícita de copiar; digitar não altera o clipboard. O core usa KConfig anônimo e desliga o histórico do runner. Não há histórico de consultas do Orla, contexto automático, runner de shell, integrações de conta ou rede.

## Experimento de compatibilidade com provedores de IA — somente no fonte

O código do launcher inclui um painel experimental **IA**. Ele é separado do dock, começa desligado e não faz parte dos assets publicados 0.2.5–0.2.8. Abrir o painel não inicia helper nem cliente. **Verificar clientes instalados** é uma ação local explícita: consulta uma lista fixa (Codex, Claude Code, OpenCode, Ollama e LM Studio) e mantém todos desativados. Ollama é apenas detecção de presença, pois consultar sua versão pode contatar um servidor.

A ação separada **Testar compatibilidade anônima** exige consentimento próprio e testa somente uma troca limitada `initialize`/`initialized` do Codex para uma versão reconhecida. Não autentica, reutiliza sessão conectada, envia texto/contexto pessoal, inicia modelo, turno ou geração, nem informa uso. Não há chat, fluxo de texto selecionado, cofre de credenciais ou handoff para terminal. Cancelar/fechar é tratado pelo controlador; o resultado permanece no estado da sessão e não vira configuração persistente.

No checkout de fonte, a operação explícita de detecção local pode ser inspecionada com `python3 -I -B scripts/ai.py detect`, a partir da raiz do repositório. O teste do protocolo anônimo fica deliberadamente como ação separada de consentimento na interface do launcher. CLI reconhecida ou troca mínima bem-sucedida não demonstra autorização do provedor, elegibilidade de conta, acesso a modelo, API suportada ou prontidão para inferência.

A fatia Source recebeu aprovação independente e tem evidências sintéticas e one-shot delimitadas, resumidas no [registro de validação](../docs/validation/ai-provider-source.md). Ela ainda não tem versão, PR/CI ou bundle público. Autenticação, inferência, semântica de cancelamento, uso, pedidos pagos, procedência do cliente instalado, isolamento de namespace/rede e comportamento nativo Wayland/QML permanecem sem qualificação.

## Compilar e testar

Requer compilador C++17, CMake ≥3.24, Qt ≥6.11.2 (Core, Gui, Widgets, Qml, Quick; Test/DBus para testes), KF6 ≥6.30 (Runner, Config, GlobalAccel, WindowSystem) e runners `krunner_services` e `calculator` do Plasma. Ambiente validado: Fedora 44, Qt 6.11.2, KF6 6.30.0, Plasma 6.7.5. O Qt Quick Controls também deve estar disponível em runtime. Os testes exigem Python 3, `dbus-daemon` e `gdbus`. No Fedora, os headers vêm de `qt6-qtbase-devel`, `qt6-qtdeclarative-devel`, `kf6-krunner-devel`, `kf6-kconfig-devel`, `kf6-kglobalaccel-devel` e `kf6-kwindowsystem-devel`; os runners instalados foram fornecidos por `plasma-workspace-libs`.

```sh
cmake -S launcher -B build/launcher -G Ninja -DBUILD_TESTING=ON
cmake --build build/launcher
ctest --test-dir build/launcher --output-on-failure
build/launcher/orla-launcher --no-global-shortcut
```

Sem atalho global, Esc encerra o processo. Na execução normal, o componente tenta registrar **Ctrl+Alt+Super+O** apenas durante a sessão do processo; `--shortcut 'Ctrl+Alt+Meta+F12'` escolhe outra combinação. Uma combinação ocupada não é substituída e a janela continua utilizável. Esc oculta a janela enquanto o atalho está registrado; fechar pelo X ou Ctrl+Q encerra e remove o registro próprio. Não há autostart, instalação automática, alteração de painel ou integração de menu nesta pasta.

## Limites de qualificação

Build, busca real por aplicativos/calculadora, cancelamento, proteção contra callbacks antigos e execução exclusiva de uma fixture própria foram verificados. Os testes de teclado Qt simulam eventos dentro da própria janela; não comprovam atalhos globais nem foco real no compositor. Todos os CTests usam bus D-Bus privado sem diretórios de ativação de serviços e XDG/runtime temporários próprios. O processo Qt verifica o ID desse bus antes de construir RunnerManager. O teste de fixture cria um `.desktop` e recibo próprios; tudo é removido ao terminar, e nenhum aplicativo pessoal é lançado automaticamente. O runner do Plasma pode registrar o acesso ao aplicativo explicitamente aberto em serviços do desktop, como KActivities; desligar o histórico do Orla não desliga esses serviços.

**Atalho por gesto real, foco global após o atalho e retorno do foco no Wayland permanecem UNRUN.** O caminho usa `KWaylandExtras::xdgActivationToken` e `KWindowSystem::activateWindow`, com callbacks canceláveis; KWin decide conceder foco. A janela continua visível para clique se o compositor recusar. A fonte KWin 6.7.5 ainda documenta o limite de passar seat/serial por KGlobalAccel a clientes sem foco. Não há solicitação de interfaces privilegiadas ou inspeção das janelas de outros apps. O primeiro probe manual terminou sem gesto. No segundo, a pessoa confirmou “Abriu e o foco voltou”, mas os eventos shortcut/↓/Escape não apareceram no recibo instrumentado. Esse relato humano foi preservado e não foi convertido em PASS nativo. As duas janelas da fixture pertenciam ao mesmo processo; não houve qualificação entre aplicativos, e a admissão L0 ampla permanece aberta.

As releases públicas 0.2.5–0.2.8 não incluem este componente em seus bundles. O painel experimental de IA permanece apenas no fonte e não é qualificado para uso diário; empacotamento e instalação opcional do launcher seguem pendentes.

## Fontes verificadas

- [ResultsModel e construtor com grupos próprios — KF6 6.30](https://github.com/KDE/krunner/blob/v6.30.0/src/model/resultsmodel.h), [implementação do contexto/cancelamento](https://github.com/KDE/krunner/blob/v6.30.0/src/model/runnerresultsmodel.cpp).
- [RunnerManager: whitelist e histórico — KF6 6.30](https://github.com/KDE/krunner/blob/v6.30.0/src/runnermanager.h), [KConfig em memória](https://github.com/KDE/kconfig/blob/v6.30.0/src/core/kconfig.h).
- [Atalho de sessão — kglobalacceld 6.7.5](https://github.com/KDE/kglobalacceld/blob/v6.7.5/src/globalshortcut.cpp), [KGlobalAccel 6.30](https://github.com/KDE/kglobalaccel/blob/v6.30.0/src/kglobalaccel.h).
- [KWaylandExtras 6.30](https://github.com/KDE/kwindowsystem/blob/v6.30.0/src/kwaylandextras.h), [política de token — KWin 6.7.5](https://github.com/KDE/kwin/blob/v6.7.5/src/xdgactivationv1.cpp).
- [TextField](https://doc.qt.io/qt-6.11/qml-qtquick-controls-textfield.html), [Text.PlainText/elide](https://doc.qt.io/qt-6.11/qml-qtquick-text.html), [Keys](https://doc.qt.io/qt-6.11/qml-qtquick-keys.html), [QQuickWindow](https://doc.qt.io/qt-6.11/qquickwindow.html) — Qt 6.11.2.
