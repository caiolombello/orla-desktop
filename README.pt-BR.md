# Orla Desktop

![Orla Desktop — native dock for KDE Plasma](website/assets/share.png)

**Um dock pessoal para o KDE Plasma, com identidade costeira e espaço para crescer.**

O Orla Dock é um applet de código aberto para fixar aplicativos, alternar entre janelas abertas e manter algumas ferramentas por perto. Ainda está em alpha: o dock funciona hoje. O checkout de código também tem componentes experimentais para menu da barra, launcher e uma primeira fatia da Central de Controle; integração completa, apresentações de notificação e várias integrações continuam planejadas.

> [Site do projeto](https://orla-desktop.sunlit-duck-7687.chatgpt.site) · [English](README.md) · [Roadmap](ROADMAP.md) · [Guia de identidade](docs/brand.md)

O checkout inclui um [launcher independente experimental](launcher/README.md) para aplicativos e cálculos locais, compilado separadamente com C++/Qt/KF6. Uma verificação local atual em uma tela Plasma 6.7.5/Wayland comprovou ativação por Ctrl+Alt+Meta+O, busca, seleção com ↓ e Escape retornando o foco à mesma janela de teste. Execução de aplicativos, provedores reais de IA e vários monitores continuam sem qualificação. O Source inclui [atribuição reversível de Meta ao Orla Search](launcher/README.md), opt-in e com recuperação da configuração anterior; o baseline de foco mantém limites de prontidão registrados. O painel opcional de compatibilidade com IA não autentica nem gera respostas; o Source experimental posterior acrescenta um painel de texto Ollama opt-in, cujo comportamento com provedor real continua sem qualificação. Veja a [validação Source de IA](docs/validation/ai-provider-source.md).

O [Menu Orla](bar/README.md) é o applet experimental da barra opcional. O helper de layout no Source compõe esse menu com Menu Global, espaçador, bandeja nativa e relógio KDE em um preset inspirado no macOS. Exige **Plasma 6.7.5**, escolhas explícitas de serviço/monitor/painéis e revisão do plano. `layout disable` remove somente a barra Orla própria; `layout restore` recupera o layout original a partir de backups verificados. O dock independente continua disponível no modo dock-only. Uma verificação local com o helper sem modificações aprovou aplicar, desativar a barra própria, restaurar normalmente o layout original e reaplicar em uma tela Plasma 6.7.5/Wayland com DPR 2. Outros ambientes, vários monitores e o aceite completo da barra continuam abertos; veja os [comandos e limites](bar/README.md). Desligamentos/reinícios rápidos do Plasma já expuseram crashes intermitentes; a proteção contra o limite de partidas não resolve esse risco experimental separado. Launcher, barra e helper de layout ficam fora dos assets publicados 0.2.5–0.2.10, que permanecem inalterados.

A direção do produto é uma composição Orla opcional que pode substituir os painéis KDE explicitamente selecionados e preservar a recuperação do layout original. Configure Auto Hide do dock nas configurações do painel Plasma; o helper preserva o dock independente. O Source inclui uma Central de Controle compartilhada experimental na barra e atribuição reversível de Meta ao Orla Search; qualificação nativa completa e marketplace de módulos de projetos opt-in permanecem no roadmap. Os adaptadores locais vêm desligados por padrão; a integração atual por arquivos de estado é distinta do futuro marketplace de plugins.

O bundle da release inclui uma [CLI experimental de consulta de updates](docs/updates.md). Ela consulta releases oficiais estáveis/beta quando invocada, compara uma versão explícita e distingue falhas de rede. Execute pelo bundle extraído; o `.plasmoid` sozinho não contém CLI nem interface de updates. Cache e atualização com recuperação continuam planejados.

O ZIP da prerelease alpha inclui a CLI experimental de inventário local do Steam. Ela lê metadados limitados de bibliotecas em raízes informadas explicitamente e distingue estados parciais/desconhecidos; não inicia jogos, acessa contas nem comprova titularidade. Busca/favoritos no dock e validação com Steam real continuam planejados. Os assets da 0.2.5 permanecem inalterados e não incluem a CLI. Os ZIPs 0.2.6 a 0.2.10 também a incluem; o `.plasmoid` sozinho não contém a CLI. Veja o [guia do Steam](docs/steam.md).
A [Central compartilhada S1 no Source](docs/validation/shared-control-center-source.md) acrescenta uma entrada opcional à direita da barra, usando a view e o áudio do dock. O módulo começa desligado, recusa falta ou ambiguidade de dono e preserva o dock ao ser removido. Pacote ativo, posição/foco nativos e áudio real mantêm gates próprios.


## O que funciona hoje

A alpha 0.2.11 aproxima a dock do macOS. `scripts/macos_look.py apply` aplica, e `restore` desfaz, o tema Plasma Orla com vidro fosco, a decoração de janelas Orla, o alternador de apps e o efeito de minimizar no estilo macOS, banners de notificação no estilo macOS com uma central de notificações (o applet opcional [Notificações Orla](docs/macos-look.md#notificações), que substitui o applet de notificações do KDE na bandeja para nunca duplicar popups) e uma bandeja mais enxuta. A Central de Controle ganha a grade no estilo macOS, perfis de energia, redes Wi-Fi e aparelhos Bluetooth pareados; a dock ganha uma Lixeira opcional e o cartão "Tocando agora" com capa e progresso. Veja o [changelog](CHANGELOG.md) e o [registro de validação da 0.2.11](docs/validation/release-0.2.11.md).

A alpha 0.2.10 amplia a Central de Controle experimental: um botão global opcional no dock, desligado por padrão, com estado de mídia e bateria, volume/mudo/saída de som, brilho da tela, Não perturbe e mudo do microfone. Cada mudança só conta depois que o serviço do sistema confirma, e um serviço ausente desativa somente o próprio card. O comportamento nativo foi exercitado em uma sessão Plasma 6.7.5/Wayland; outros ambientes e hardware continuam sem qualificação. Veja o [guia da Central de Controle](docs/control-center.md) e o [registro de validação da 0.2.10](docs/validation/release-0.2.10.md).

- Fixar, reordenar, abrir e remover aplicativos; alternar para janelas abertas ou minimizá-las. Abrir menus com Menu ou Shift+F10; Escape fecha o menu.
- Partir dos temas Glass, Midnight ou Paper e pré-visualizar cores, opacidade, espaçamento, cantos, ícones e movimento reduzido. Aplicar salva; Cancelar, Escape ou fechar descarta a prévia. Desfazer restaura a aparência aplicada anterior uma vez por sessão.
- Usar relógio, Pomodoro, calendário do KDE e controles MPRIS com seleção de player, faixa/artista e botões conforme as capacidades anunciadas.
- Ativar nas configurações o widget opcional de bateria do sistema (desligado por padrão) para ler o agregado do UPower; o PeriGauge continua separado para periféricos.
- Ler snapshots locais opcionais do QuotaLantern, PeriGauge e FalaTrace quando esses projetos gravam arquivos de estado compatíveis.
- Criar e selecionar explicitamente perfis manuais para apps fixados, aparência, ordem/visibilidade dos widgets, eventos do calendário e filtro de janelas pela área atual. O Pomodoro permanece compartilhado.
- Manter o dock em um painel Plasma e ajustar posição e visibilidade pelas configurações do Plasma, incluindo Auto Hide para revelar pela borda.

O calendário usa a mesma seleção de calendários dos componentes do KDE. O Orla não conecta o Google Agenda sozinho. Para ver eventos do Google, primeiro adicione e configure uma conta Google pelo KOrganizer/KDE PIM e depois ative os eventos sincronizados nas configurações do Orla. A configuração e sincronização dependem dos recursos KDE PIM instalados no sistema.

O [aviso local do Pomodoro](docs/local-events.md), incluído na alpha 0.2.7, é uma preferência opt-in em **Widgets**, global entre perfis e desligada por padrão. Ele dura até oito segundos dentro de uma área reservada do dock e só sinaliza a conclusão de uma etapa de foco ou pausa do Pomodoro. HUD/ilha e integração com notificações do KDE continuam fora do escopo. Consulte o [registro de validação 0.2.7](docs/validation/local-events-0.2.7.md) para evidências e limites.

Os controles de mídia compartilham um único modelo MPRIS nativo do Plasma. Preferem inicialmente o Spotify quando descoberto e mantêm a escolha manual de player durante a sessão. Play, Pause, Anterior e Próxima respeitam as capacidades do player selecionado; faixa e artista aparecem como texto simples e limitado. Uma fixture D-Bus privada qualificou o modelo nativo com dois players sintéticos, sem validar o cliente real do Spotify ou reprodução de áudio. Capa, progresso e abertura do cliente continuam planejados.

A bateria do sistema lê somente o dispositivo agregado do UPower, a cada 30 segundos enquanto ativada, com timeout de cinco segundos. Uma leitura real de 0% permanece visível; dados ausentes ou indisponíveis têm estado neutro. Energia externa, carga e tempo estimado aparecem somente quando informados. O widget não controla hardware nem enumera baterias de periféricos. Veja a [validação de bateria e mídia](docs/validation/battery-media-0.2.4.md) para cobertura e limites. As integrações com projetos locais leem arquivos de estado existentes; elas não iniciam os outros aplicativos nem chamam suas APIs online.

A aparência usa um override separado e preserva as preferências anteriores de tema, ícones e animação. Restaurar prepara essas preferências para prévia e exige Aplicar. Desde a 0.2.10, **Tema JSON experimental** aceita um arquivo JSON local por **Importar arquivo…** ou texto colado no formato `0.1-experimental`. A importação preenche o editor; a prévia mostra dez tokens em memória e Aplicar salva somente a aparência normal do perfil atual. O recurso não instala pacotes de tema nem salva os metadados declarados. Formato e consumidor continuam experimentais; veja o [guia de temas](docs/theme-format.md) e a [validação do consumidor](docs/validation/theme-consumer-0.2.6.md) para cobertura e limites nativos.

## Usar perfis

Abra as configurações do dock e escolha **Perfis**, ao lado de **Aparência**, **Widgets** e **Contextos**. **Criar Trabalho, Pessoal e Jogos** copia suas preferências salvas para três perfis e mantém **Preferências anteriores** ativo. Escolha um perfil e pressione **Usar perfil**; apenas mudar o seletor não ativa a escolha. Para copiar a apresentação salva do perfil ativo, digite um nome único e pressione **Criar e usar**. Aplique ou cancele a prévia de aparência antes de criar ou trocar o perfil.

Em **Widgets**, visibilidade, ordem, eventos do calendário e filtro de janelas salvam imediatamente no perfil ativo; Cancelar aparência não desfaz essas opções. Organizar a ordem exige um perfil. Volte a **Preferências anteriores** para usar as preferências originais. Não há migração automática. Veja o [guia de perfis](docs/profiles.md) e a [validação](docs/validation/profiles-0.2.5.md), com prova privada de KConfig/reinício. A prerelease alpha pública 0.2.8 adiciona a primeira aba experimental **Contextos** para associar explicitamente a Activity ou área virtual atual a um perfil gerenciado existente. Ela não troca contextos nem seleciona perfis automaticamente. Consulte o [guia de Contextos](docs/contexts.md) e a [validação 0.2.8](docs/validation/contexts-0.2.8.md). P2 continua parcial, W1 ainda não começou e a qualificação da sessão nativa permanece pendente.

## Requisitos

- KDE Plasma 6.7 ou mais recente.
- Python 3.10 ou mais recente para o helper de empacotamento e as integrações locais.
- `kpackagetool6` para instalação. PySide6 com QtDBus, `busctl` e sessão D-Bus são requisitos opcionais das integrações locais com projetos. A ausência deles não bloqueia a instalação do dock.
- KOrganizer e o recurso de calendário KDE PIM apropriado para sincronizar calendários externos.

Em um Fedora que já tenha Plasma 6.7+, instale a ferramenta de pacotes. Adicione as dependências opcionais se quiser os widgets dos projetos e execute `doctor` dentro da sua sessão gráfica:

```bash
sudo dnf install kf6-kpackage
# Integrações locais opcionais com projetos:
sudo dnf install python3-pyside6 systemd
```

A base atual de validação é Fedora 44, Plasma 6.7.5, Qt 6.11.2 e Wayland. Outras distribuições, versões do Plasma, sessões X11 e configurações com vários monitores ainda precisam de validação.

## Instalar uma versão publicada

Os comandos abaixo apontam para a [prerelease alpha 0.2.11](https://github.com/caiolombello/orla-desktop/releases/tag/v0.2.11). Baixe seu `.zip`, verifique o checksum usando o `SHA256SUMS` publicado e extraia o arquivo. O pacote inclui o helper junto com o applet:

```bash
cd ~/Downloads
sha256sum --ignore-missing -c SHA256SUMS
unzip orla-dock-0.2.11.zip
cd orla-dock-0.2.11
python3 scripts/orla.py doctor
python3 scripts/orla.py install orla-dock-0.2.11.plasmoid
```

As integrações de projetos ficam desligadas por padrão. Para habilitar explicitamente os adaptadores experimentais incluídos, acrescente `--with-integrations` ao comando de instalação. Instalar/atualizar sem essa opção preserva serviços e preferências existentes sem habilitar novos adaptadores. `doctor` identifica dependências opcionais ausentes. Uma falha ao atualizar o D-Bus gera aviso e preserva o dock instalado. O helper não precisa de acesso de administrador. Depois, adicione **Orla Dock** pela interface Adicionar Widgets do Plasma. Guarde o diretório extraído caso queira executar o helper novamente.

Para compilar e instalar a partir do código-fonte:

```bash
git clone https://github.com/caiolombello/orla-desktop.git
cd orla-desktop
python3 scripts/orla.py doctor
python3 scripts/orla.py build
python3 scripts/orla.py install dist/orla-dock-0.2.11.plasmoid
```

Para verificar a configuração local ou remover os arquivos gerenciados pelo Orla:

```bash
python3 scripts/orla.py doctor
python3 scripts/orla.py uninstall
```

Remova o Orla Dock dos painéis antes de desinstalar. O comando remove o applet e o serviço de integração gerenciado, preservando as configurações salvas do widget no Plasma para uma reinstalação futura. Ele não pede confirmação; execute somente quando quiser remover esses arquivos.

## Desenvolvimento

Execute os testes portáteis e verifique a compilação com Python:

```bash
python3 -m unittest discover -s tests -p 'test_integrations.py' -v
python3 -m unittest discover -s tests -p 'test_package_cli.py' -v
python3 scripts/orla.py build
```

Os testes de interação QML precisam de uma sessão gráfica KDE em execução. CI portátil não cobre comportamento no painel nativo, foco no Wayland, menus globais, notificações ou vários monitores. Ao abrir uma issue, informe a versão exata do Plasma e o tipo de sessão.

Leia [CONTRIBUTING.md](CONTRIBUTING.md) antes de abrir um pull request. Para assuntos de segurança, siga [SECURITY.md](SECURITY.md).

## Estado do projeto

Orla Desktop é um projeto alpha. O componente atual mantém o identificador Plasma `org.caiodock.dock` e o serviço D-Bus `org.caiodock.Integrations` para preservar instalações e configurações existentes. O nome exibido às pessoas é Orla Dock; esses identificadores internos existem por compatibilidade.

Perfis manuais do dock e organização de widgets são o incremento parcial P1/C1 publicado na 0.2.5. A versão 0.2.6 acrescenta o primeiro consumidor experimental de tema por colagem e inclui a CLI experimental do Steam. A 0.2.7 mantém essa CLI no ZIP e acrescenta um aviso local opt-in para conclusão de foco ou pausa do Pomodoro. A prerelease 0.2.8 publica a primeira fatia experimental de associação explícita de Activity/área a perfis existentes; P2 continua parcial, W1 ainda não começou e a qualificação nativa permanece pendente. A alpha 0.2.9 publicou a primeira fatia opcional da Central de Controle; a 0.2.10 acrescenta controles diretos de áudio, brilho, Não perturbe e microfone, sistema visual unificado, reordenação por arraste, presets de aparência, perfis automáticos opt-in, troca de área de trabalho e um host experimental de complementos. CC1 continua parcial e a qualificação nativa cobre uma única sessão. A qualificação em ambientes reais continua pendente. A leitura da bateria do sistema e o incremento de seleção/controle de players fazem parte da 0.2.4; os marcos B1/M1 completos continuam abertos para qualificação de hardware e cliente real. A qualificação nativa completa da barra opcional inspirada no macOS, a Central de Controle compartilhada pela barra, a integração completa do launcher inspirado no Raycast, autenticação/inferência de IA e fluxo de texto escolhido, Dynamic Island/HUD/toasts, capa/progresso/abertura do Spotify, integração Steam no dock, comportamento de contextos por monitor, troca de Activity, atualizações automáticas e integrações mais completas com os projetos estão no roadmap. Formato estável de temas, galeria, SDK versionado, addons vendidos pelos próprios autores e integrações opcionais de IA também estão planejados.

Veja o [roadmap completo](ROADMAP.md) para sequência, dependências e critérios de aceite, com propostas de [UX/UI](docs/UX_UI.md), [temas e extensões](docs/EXTENSIONS.md), [acesso e provedores de IA](docs/AI_INTEGRATIONS.md) e [experiência de desenvolvimento](docs/DX.md). Temas declarativos vêm antes de plugins executáveis; adaptadores de IA usam as rotas de autorização oferecidas por cada provedor. O núcleo continua útil sem conta Orla, addon pago ou assinatura de IA. Checkout de marketplace e SDK ainda não foram implementados.

## Licença

Orla Desktop é distribuído sob a [licença MIT](LICENSE).
