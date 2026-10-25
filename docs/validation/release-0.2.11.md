# Alpha 0.2.11 — registro da release

**Estado:** publicada como prerelease alpha (`latest=false`) em 25/10/2026 19:23:53 UTC,
a partir do `main` depois dos PRs 117–139.
Nenhum marco do roadmap fica concluído só por esta publicação. Os registros de
cada funcionalidade continuam sendo a fonte das provas e dos limites.

## O que entra nos assets

O `.plasmoid` contém a dock (`org.caiodock.dock`) com:

- a Central de Controle em grade no estilo macOS, com perfil de energia
  (CC2-A), rádios Wi-Fi e Bluetooth (CC2-B, CC2-C), página de redes Wi-Fi
  (CC2-D) e de aparelhos Bluetooth pareados (CC2-E);
- o vidro do tema Plasma Orla na dock, nos popups e na etiqueta do app;
- a Lixeira opcional;
- o cartão "Tocando agora" (capa, álbum, progresso, abrir o player);
- a quota agrupada como no QuotaLantern e as baterias de periféricos que
  escondem aparelhos desconectados e mostram nomes compartilhados.

O ZIP acrescenta:

- o helper `scripts/`, com `macos_look.py`, `plasma_theme.py`,
  `window_decoration.py`, `macos_notifications.py`, `menu_bar_tray.py` e
  `menu_bar_clock.py`;
- os testes, a documentação, os temas (`themes/`, com a decoração de janelas),
  os complementos de dados (`addons/`) e o site;
- o applet opcional **Notificações Orla** (`notifications/`), que
  `macos_notifications.py install` instala.

Ficam fora, e continuam somente no Source:

- o launcher C++;
- o Menu Orla (incluindo os itens recentes e "Forçar encerramento…");
- a composição Workspace e sua janela de updates;
- os arquivos de layout da barra (`layouts/`).

Sem a barra Orla, o passo do relógio em `macos_look.py` não encontra um relógio
para mudar e segue sem erro.

## Provas por área

| Área | Registro | Prova nativa nesta máquina |
|---|---|---|
| Visual macOS (tema, decoração, alternador) | [macos-look-20261024.md](macos-look-20261024.md), [macos-look.md](../macos-look.md) | Sessão Plasma 6.7.5/Wayland, escala 1,45, esquema escuro |
| Notificações | [macos-look.md](../macos-look.md#notificações) | Banner, empilhamento, expiração, sem popup duplicado, inibição por app e reinício do Plasma; central só fora da sessão |
| Bandeja enxuta | [macos-look.md](../macos-look.md#bandeja) | Aplicada na barra da sessão |
| Central de Controle CC2 | [control-center.md](../control-center.md) | Rádios e páginas exercitados na sessão, conforme o guia |
| Tocando agora | [ROADMAP.md](../../ROADMAP.md) (M1) | Render sintético; Spotify real não testado |

As provas nativas usaram uma única sessão Plasma 6.7.5/Wayland. Nenhuma captura
ou log publicado contém dados pessoais; as capturas da sessão foram apagadas.

## CI e builds

Antes da publicação, rodam:

- a CI do PR de release (testes portáteis e pacote; build/CTest do launcher);
- `tests/test_release.py`, que agora exige `notifications/` no ZIP;
- duas builds de release do mesmo commit, comparadas byte a byte;
- os módulos `tests/test_*.py` incluídos no ZIP, de dentro do pacote extraído.

## Não qualificado

- Instalação e atualização em uma conta limpa e em outras distribuições.
- Vários monitores, escala fracionária diferente de 1,45 e o esquema claro nativo.
- Spotify real com áudio e segundo player; resposta inline e miniaturas nas
  notificações; a central de notificações aberta pela bandeja na sessão real.
- Hardware de rede/Bluetooth além das execuções registradas no guia da Central.

## Publicação e artefatos

A preparação entrou pelo [PR 140](https://github.com/caiolombello/orla-desktop/pull/140),
merge `d363ea726a8139136a013fbc469b7a9295029014`, que é o alvo da tag `v0.2.11`. O PR
passou os dois jobs da CI ([run 40224759447](https://github.com/caiolombello/orla-desktop/actions/runs/40224759447)),
e o `main` no merge também ([run 40225359003](https://github.com/caiolombello/orla-desktop/actions/runs/40225359003)).

Duas builds do commit do PR, feitas em worktrees limpas, produziram os mesmos bytes, e
a build do merge é idêntica a elas. Os 65 módulos `tests/test_*.py` incluídos no ZIP
passaram de dentro do pacote extraído, um processo por módulo, com Qt offscreen e
estilo Fusion; os pulos são os já declarados na 0.2.10 (calendário sem o plugin PIM
do KDE, casos nativos). Os três downloads anônimos retornaram HTTP 200, são idênticos
às builds e o `SHA256SUMS` publicado valida o applet e o ZIP.

| Asset | Tamanho | SHA-256 |
|---|---:|---|
| [Applet `.plasmoid`](https://github.com/caiolombello/orla-desktop/releases/download/v0.2.11/orla-dock-0.2.11.plasmoid) | 266,852 bytes | `7a45ca703417bb9050c6fa011150ccb920df36ca5c929c75d2c33292a9e534f6` |
| [Bundle ZIP](https://github.com/caiolombello/orla-desktop/releases/download/v0.2.11/orla-dock-0.2.11.zip) | 8,912,293 bytes | `e8892b67f4fa824dece414f468e8c6e44303f777c03a0e5f411670a379e33867` |
| [`SHA256SUMS`](https://github.com/caiolombello/orla-desktop/releases/download/v0.2.11/SHA256SUMS) | 179 bytes | `14d2b7ee5a34e959c9c3f7d650f21e3ba8920a39f9545e99a5a5f82947c62144` |

## Instalação a partir dos assets publicados

O caminho do README rodou com os arquivos baixados. O ZIP foi extraído;
`scripts/orla.py doctor` aprovou Python, `kpackagetool6`, `busctl`, PySide6, a
sessão D-Bus e o Plasma 6.7.5. Em seguida, `scripts/orla.py install
orla-dock-0.2.11.plasmoid` atualizou a dock deste usuário, que antes tinha a 0.2.10.
Os arquivos instalados são idênticos ao `.plasmoid` publicado.

Isso cobre uma atualização numa conta já configurada. Instalação limpa, outra
distribuição e remoção continuam sem prova nesta release.
