# Alpha 0.2.11 — registro da release

**Estado:** preparada a partir do `main` depois dos PRs 117–139. A publicação
como prerelease alpha (`latest=false`) acontece depois do merge.
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
