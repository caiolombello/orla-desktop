# Orla Desktop

![Orla Desktop — native dock for KDE Plasma](website/assets/share.png)

**Um dock pessoal para o KDE Plasma, com identidade costeira e espaço para crescer.**

O Orla Dock é um applet de código aberto para fixar aplicativos, alternar entre janelas abertas e manter algumas ferramentas por perto. Ainda está em alpha: o dock funciona hoje. O checkout de código também tem primeiros componentes experimentais para menu da barra opcional e launcher; integração completa, apresentações de notificação, Central de Controle e várias integrações continuam planejadas.

> [Site do projeto](https://orla-desktop.sunlit-duck-7687.chatgpt.site) · [English](README.md) · [Roadmap](ROADMAP.md) · [Guia de identidade](docs/brand.md)

O checkout de código também inclui um [launcher independente experimental](https://github.com/caiolombello/orla-desktop/blob/main/launcher/README.md) para aplicativos e cálculos locais. Ele exige build separado C++/Qt/KF6. A release 0.2.5 não o empacota nem instala; foco global no Wayland e integração completa do launcher continuam pendentes.

O checkout inclui o [Menu Orla, primeiro componente experimental da barra](https://github.com/caiolombello/orla-desktop/blob/main/bar/README.md), com menu do sistema e nome do aplicativo ativo para Plasma 6.7.x. Exige instalação manual separada e não faz parte da release 0.2.5. Diálogos reais de sessão, painel/foco e composição em vários monitores continuam sem teste. Menu Global, bandeja e relógio serão widgets KDE irmãos.

O bundle da release 0.2.5 inclui uma [CLI experimental de consulta de updates](docs/updates.md). Ela consulta releases oficiais estáveis/beta quando invocada, compara uma versão explícita e distingue falhas de rede. Execute pelo bundle extraído; o `.plasmoid` sozinho não contém CLI nem interface de updates. Cache e atualização com recuperação continuam planejados.

## O que funciona hoje

- Fixar, reordenar, abrir e remover aplicativos; alternar para janelas abertas ou minimizá-las. Abrir menus com Menu ou Shift+F10; Escape fecha o menu.
- Partir dos temas Glass, Midnight ou Paper e pré-visualizar cores, opacidade, espaçamento, cantos, ícones e movimento reduzido. Aplicar salva; Cancelar, Escape ou fechar descarta a prévia. Desfazer restaura a aparência aplicada anterior uma vez por sessão.
- Usar relógio, Pomodoro, calendário do KDE e controles MPRIS com seleção de player, faixa/artista e botões conforme as capacidades anunciadas.
- Ativar nas configurações o widget opcional de bateria do sistema (desligado por padrão) para ler o agregado do UPower; o PeriGauge continua separado para periféricos.
- Ler snapshots locais opcionais do QuotaLantern, PeriGauge e FalaTrace quando esses projetos gravam arquivos de estado compatíveis.
- Criar e selecionar explicitamente perfis manuais para apps fixados, aparência, ordem/visibilidade dos widgets, eventos do calendário e filtro de janelas pela área atual. O Pomodoro permanece compartilhado.
- Manter o dock em um painel Plasma e ajustar posição e visibilidade pelas configurações do Plasma.

O calendário usa a mesma seleção de calendários dos componentes do KDE. O Orla não conecta o Google Agenda sozinho. Para ver eventos do Google, primeiro adicione e configure uma conta Google pelo KOrganizer/KDE PIM e depois ative os eventos sincronizados nas configurações do Orla. A configuração e sincronização dependem dos recursos KDE PIM instalados no sistema.

Os controles de mídia compartilham um único modelo MPRIS nativo do Plasma. Preferem inicialmente o Spotify quando descoberto e mantêm a escolha manual de player durante a sessão. Play, Pause, Anterior e Próxima respeitam as capacidades do player selecionado; faixa e artista aparecem como texto simples e limitado. Uma fixture D-Bus privada qualificou o modelo nativo com dois players sintéticos, sem validar o cliente real do Spotify ou reprodução de áudio. Capa, progresso e abertura do cliente continuam planejados.

A bateria do sistema lê somente o dispositivo agregado do UPower, a cada 30 segundos enquanto ativada, com timeout de cinco segundos. Uma leitura real de 0% permanece visível; dados ausentes ou indisponíveis têm estado neutro. Energia externa, carga e tempo estimado aparecem somente quando informados. O widget não controla hardware nem enumera baterias de periféricos. Veja a [validação de bateria e mídia](docs/validation/battery-media-0.2.4.md) para cobertura e limites. As integrações com projetos locais leem arquivos de estado existentes; elas não iniciam os outros aplicativos nem chamam suas APIs online.

A aparência usa um override separado e preserva as preferências anteriores de tema, ícones e animação. Restaurar prepara essas preferências para prévia e exige Aplicar. O [kit experimental de temas](docs/theme-format.md) valida e empacota dados comunitários; importar/aplicar esses arquivos continua no roadmap. Veja a [validação da aparência](docs/validation/appearance-0.2.3.md) para cobertura e limites nativos.

## Usar perfis

Abra as configurações do dock e escolha **Perfis**, ao lado de **Aparência** e **Widgets**. **Criar Trabalho, Pessoal e Jogos** copia suas preferências salvas para três perfis e mantém **Preferências anteriores** ativo. Escolha um perfil e pressione **Usar perfil**; apenas mudar o seletor não ativa a escolha. Para copiar a apresentação salva do perfil ativo, digite um nome único e pressione **Criar e usar**. Aplique ou cancele a prévia de aparência antes de criar ou trocar o perfil.

Em **Widgets**, visibilidade, ordem, eventos do calendário e filtro de janelas salvam imediatamente no perfil ativo; Cancelar aparência não desfaz essas opções. Organizar a ordem exige um perfil. Volte a **Preferências anteriores** para usar as preferências originais. Não há migração automática. Veja o [guia de perfis](docs/profiles.md) e a [validação](docs/validation/profiles-0.2.5.md), com prova privada de KConfig/reinício. Associação a Activities/desktops, escolha de barra/launcher/eventos e qualificação de popup/foco nativo continuam pendentes.

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

Os comandos abaixo apontam para a [prerelease alpha 0.2.5 publicada](https://github.com/caiolombello/orla-desktop/releases/tag/v0.2.5). Baixe seu `.zip`, verifique o checksum usando o `SHA256SUMS` publicado e extraia o arquivo. O pacote inclui o helper junto com o applet:

```bash
cd ~/Downloads
sha256sum --ignore-missing -c SHA256SUMS
unzip orla-dock-0.2.5.zip
cd orla-dock-0.2.5
python3 scripts/orla.py doctor
python3 scripts/orla.py install orla-dock-0.2.5.plasmoid
```

O helper registra o serviço local quando a bridge e as dependências opcionais estão disponíveis. `doctor` identifica as dependências opcionais ausentes. Após instalá-las, reinstale o mesmo pacote para ativar as integrações. Uma falha ao atualizar o D-Bus gera aviso e preserva o dock instalado. O helper não precisa de acesso de administrador. Depois, adicione **Orla Dock** pela interface Adicionar Widgets do Plasma. Guarde o diretório extraído caso queira executar o helper novamente.

Para compilar e instalar a partir do código-fonte:

```bash
git clone https://github.com/caiolombello/orla-desktop.git
cd orla-desktop
python3 scripts/orla.py doctor
python3 scripts/orla.py build
python3 scripts/orla.py install dist/orla-dock-0.2.5.plasmoid
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

Perfis manuais do dock e organização de widgets são o incremento parcial P1/C1 publicado na 0.2.5. A leitura da bateria do sistema e o incremento de seleção/controle de players fazem parte da 0.2.4; os marcos B1/M1 completos continuam abertos para qualificação de hardware e cliente real. A barra completa inspirada no macOS, a Central de Controle, a integração completa do launcher inspirado no Raycast, Dynamic Island/HUD/toasts, capa/progresso/abertura do Spotify, Steam, associação de perfis a Activities/desktops, troca de área de trabalho/Activity, atualizações automáticas e integrações mais completas com os projetos estão no roadmap. Temas comunitários, SDK versionado, addons vendidos pelos próprios autores e integrações opcionais de IA também estão planejados. Esses recursos não fazem parte da versão atual.

Veja o [roadmap completo](ROADMAP.md) para sequência, dependências e critérios de aceite, com propostas de [UX/UI](docs/UX_UI.md), [temas e extensões](docs/EXTENSIONS.md), [acesso e provedores de IA](docs/AI_INTEGRATIONS.md) e [experiência de desenvolvimento](docs/DX.md). Temas declarativos vêm antes de plugins executáveis; adaptadores de IA usam as rotas de autorização oferecidas por cada provedor. O núcleo continua útil sem conta Orla, addon pago ou assinatura de IA. Checkout de marketplace e SDK ainda não foram implementados.

## Licença

Orla Desktop é distribuído sob a [licença MIT](LICENSE).
