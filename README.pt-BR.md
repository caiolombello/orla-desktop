# Orla Desktop

![Orla Desktop — native dock for KDE Plasma](website/assets/share.png)

**Um dock pessoal para o KDE Plasma, com identidade costeira e espaço para crescer.**

O Orla Dock é um applet de código aberto para fixar aplicativos, alternar entre janelas abertas e manter algumas ferramentas por perto. Ainda está em alpha: o dock funciona hoje; a barra superior opcional, o launcher, as apresentações de notificação, os controles do sistema e várias integrações continuam planejados.

> [Site do projeto](https://orla-desktop.sunlit-duck-7687.chatgpt.site) · [English](README.md) · [Roadmap](ROADMAP.md) · [Guia de identidade](docs/brand.md)

## O que funciona hoje

- Fixar, reordenar, abrir e remover aplicativos; alternar para janelas abertas ou minimizá-las.
- Escolher entre os temas Glass, Midnight e Paper, ajustar o tamanho dos ícones e ativar ou desativar animações.
- Usar relógio, Pomodoro, calendário do KDE e controles de mídia compatíveis com MPRIS.
- Ler snapshots locais opcionais do QuotaLantern, PeriGauge e FalaTrace quando esses projetos gravam arquivos de estado compatíveis.
- Manter o dock em um painel Plasma e ajustar posição e visibilidade pelas configurações do Plasma.

O calendário usa a mesma seleção de calendários dos componentes do KDE. O Orla não conecta o Google Agenda sozinho. Para ver eventos do Google, primeiro adicione e configure uma conta Google pelo KOrganizer/KDE PIM e depois ative os eventos sincronizados nas configurações do Orla. A configuração e sincronização dependem dos recursos KDE PIM instalados no sistema.

Os controles de mídia usam MPRIS e funcionam com players compatíveis. O comportamento específico do Spotify, capa e reprodução ainda não foi validado. As integrações com projetos locais leem arquivos de estado existentes; elas não iniciam os outros aplicativos nem chamam suas APIs online.

## Requisitos

- KDE Plasma 6.7 ou mais recente.
- Python 3.10 ou mais recente para o helper de empacotamento e as integrações locais.
- PySide6 com QtDBus para o instalador e o serviço de integração local. O applet pode funcionar sem as integrações com projetos, mas o helper oficial de instalação verifica essas dependências.
- KOrganizer e o recurso de calendário KDE PIM apropriado para sincronizar calendários externos.

Em um Fedora que já tenha Plasma 6.7+, instale as dependências do helper pelos pacotes da distribuição e execute `doctor` dentro da sua sessão gráfica:

```bash
sudo dnf install kf6-kpackage python3-pyside6 systemd
```

A base atual de validação é Fedora 44, Plasma 6.7.5, Qt 6.11.2 e Wayland. Outras distribuições, versões do Plasma, sessões X11 e configurações com vários monitores ainda precisam de validação.

## Instalar uma versão publicada

Baixe o `.zip` da versão na página de [releases do GitHub](https://github.com/caiolombello/orla-desktop/releases), verifique o checksum usando o `SHA256SUMS` publicado e extraia o arquivo. O pacote inclui o helper junto com o applet:

```bash
cd ~/Downloads
sha256sum --ignore-missing -c SHA256SUMS
unzip orla-dock-0.2.1.zip
cd orla-dock-0.2.1
python3 scripts/orla.py doctor
python3 scripts/orla.py install orla-dock-0.2.1.plasmoid
```

Se a bridge de integração estiver no pacote, o helper registra o serviço local opcional. Não é necessário acesso de administrador. Depois, adicione **Orla Dock** pela interface Adicionar Widgets do Plasma. Guarde o diretório extraído caso queira executar o helper novamente.

Para compilar e instalar a partir do código-fonte:

```bash
git clone https://github.com/caiolombello/orla-desktop.git
cd orla-desktop
python3 scripts/orla.py doctor
python3 scripts/orla.py build
python3 scripts/orla.py install dist/orla-dock-0.2.1.plasmoid
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

A barra de menus inspirada no macOS, a Central de Controle, o launcher inspirado no Raycast, Dynamic Island/HUD/toasts, suporte específico ao Spotify, bateria do sistema, Steam, perfis, troca de área de trabalho/Activity, atualizações automáticas e integrações mais completas com os projetos estão no roadmap. Esses recursos não fazem parte da versão atual. Veja [ROADMAP.md](ROADMAP.md) para sequência e critérios de aceite.

## Licença

Orla Desktop é distribuído sob a [licença MIT](LICENSE).
