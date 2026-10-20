# Composição opcional — validação de código e interface

20/10/2026. PySide6/Qt 6.11.2, renderização offscreen/software. Este registro
qualifica a janela no checkout e a ligação ao gerenciador existente com runtime
sintético. Não qualifica o comportamento nativo de Plasma/Wayland nem distribuição.

## Comportamento verificado

- Ler, selecionar, revisar e abandonar não alteram configuração, bancos ou journal.
- Uma confirmação consome um plano em memória; dupla confirmação, plano antigo e
  drift de bytes/modos, inventário, recibo, serviço e raízes são recusados.
- O host Qt executa apply → disable → restore nas funções reais, usando FileStore
  e arquivos privados com FakeRuntime; recupera os bytes originais e despacha uma
  aplicação e uma remoção. Há cobertura adicional de schema2 e falha/recuperação.
- Fechamento pendente bloqueia novos trabalhos até join. Falhas não expõem caminhos
  ou identificadores privados. Erros de compatibilidade e widgets têm orientação.
- Inserção, reordenação e remoção de monitores mantêm seleção visual e alvo iguais.
- Em 350×240, o conteúdo continua rolável e o controle com foco é revelado após
  layout/redimensionamento. O teste preserva a falha histórica encontrada em KDE.
- Uma transação registrada com leitura final indisponível, ou Plasma parado,
  não anuncia barra ativa nem oferece ações normais; releitura não repete execute.

## Verificações

```sh
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_QUICK_CONTROLS_STYLE=Fusion \
  python3 -B -m unittest discover -s tests -p 'test_workspace*.py'
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_QUICK_CONTROLS_STYLE=org.kde.desktop \
  python3 -B -m unittest discover -s tests -p 'test_workspace*.py'
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
  python3 -B -m unittest discover -s tests -p 'test_panel_layout*.py'
PYTHONPATH=tests QT_QPA_PLATFORM=offscreen \
  python3 -B -m unittest test_package_cli test_release test_design_system
python3 scripts/design.py check
```

Resultados: 31 testes de composição em cada estilo; 177 do backend; 50 de CLI,
bundle e design. Todos passaram. Design check: zero problemas. O build do plasmoid
continua com o mesmo SHA256 do pacote anterior; nenhum payload novo foi instalado.

A galeria usa `Gallery.workspace` do gerador existente: 36 capturas, nove por
combinação de estilo/esquema, sem warnings QML. As capturas finais foram vistas;
foco, legibilidade e geometria foram também medidos pelos testes. Foram corrigidos
viewport colapsado, foco invisível após resize, alvo de monitor divergente e rótulo
cortado. A revisão independente final não encontrou bloqueadores neste escopo.

## Capturas sintéticas

![Seleção escura](../screenshots/workspace-composition/workspace-dark-selection-350.png)
![Revisão clara](../screenshots/workspace-composition/workspace-light-review-420.png)
![Foco em janela baixa](../screenshots/workspace-composition/workspace-dark-committed-short-focus.png)
![Leitura final indisponível](../screenshots/workspace-composition/workspace-light-unverified.png)

## Ainda aberto

Não foram executados NativeRuntime, IPC real, recarga de plasmashell ou ciclo
completo desta janela na sessão do usuário. Os gates próprios anteriores de
SIGINT/SIGTERM/Window.close exercitaram o controller com uma Session bloqueada e
loop Qt real em filhos privados; não provam o ciclo nativo. Distribuição sem Source,
entrada instalada no desktop, criação aditiva e reativação direta permanecem no
[roadmap](../../ROADMAP.md). Reativação atual exige restore → novo plano/apply.
