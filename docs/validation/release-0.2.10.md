# Alpha 0.2.10 — registro da release

**Estado:** prerelease alpha preparada a partir do `main` depois dos PRs 23–114.
Nenhum marco do roadmap fica concluído só por esta publicação. Os registros de
cada funcionalidade continuam sendo a fonte das provas e dos limites.

## O que entra nos assets

O `.plasmoid` contém a dock (`org.caiodock.dock`) com:

- os controles diretos da Central de Controle: áudio (CC1-A), brilho (CC1-B),
  Não perturbe (CC1-C) e microfone (CC1-D);
- o sistema visual unificado;
- o arraste de widgets e apps;
- os presets e a importação de tema por arquivo;
- os perfis automáticos opt-in e a troca de área de trabalho;
- o calendário KDE;
- o host experimental de complementos de dados.

O ZIP acrescenta:

- o helper `scripts/`, testes, documentação, temas e site;
- a pasta `addons/`, com os schemas publicados e os exemplos sintéticos que os
  testes do pacote leem.

Ficam fora, e continuam somente no Source:

- o launcher C++;
- o Menu Orla;
- a composição Workspace e sua janela de updates;
- os arquivos de layout da barra (`layouts/`).

Por isso, o helper de layout do ZIP não compõe a barra sem um checkout completo.

## Provas por área

| Área | Registro | Prova nativa nesta máquina |
|---|---|---|
| Áudio da Central | [control-center-audio-source.md](control-center-audio-source.md) | Fixture isolada com o serviço real; gates de transferência abertos |
| Brilho, Não perturbe, microfone | [control-center.md](../control-center.md) | Uma sessão Plasma 6.7.5/Wayland, um monitor externo por DDC/CI |
| Central na barra | [shared-control-center-source.md](shared-control-center-source.md) | Barra fica fora dos assets |
| Presets de aparência | [appearance-presets-source.md](appearance-presets-source.md) | Instalação local delimitada |
| Perfis automáticos | [contexts-auto-installed.md](contexts-auto-installed.md) | Visita sem edição com o automático desligado |
| Troca de área | [desktop-switch-source.md](desktop-switch-source.md) | Parcial; escopo por monitor aberto |
| Importação de tema | [theme-file-import-0.2.9.md](theme-file-import-0.2.9.md) | Leitor local; galeria pendente |
| Complementos | [addon-host-core.md](addon-host-core.md) | Exportador real de quota e caminho completo pela interface |

As provas nativas usaram uma única sessão Plasma 6.7.5/Wayland com escala 2 e
dados sintéticos ou restaurados ao estado inicial. Nenhuma captura ou log
publicado contém dados pessoais.

## CI e builds

O último commit de funcionalidade, `17bc542` (PR 114), passou os dois jobs da CI
do `main` ([run 39841668296](https://github.com/caiolombello/orla-desktop/actions/runs/39841668296)):
testes portáteis e pacote, e build/CTest do launcher em Fedora 44. Em seguida, os
PRs 1 e 2 do Dependabot atualizaram `actions/checkout` para v7.0.1 e
`actions/upload-artifact` para v7.0.2; cada um passou os dois jobs depois de
refeito sobre esse `main`.

Antes da publicação, rodaram localmente:

- `tests/test_release.py`, que agora exige `addons/` no ZIP e falha sem ela;
- duas builds de release do mesmo commit, comparadas byte a byte.

## Não qualificado

- Instalação e atualização em uma conta limpa e em outras distribuições.
- Vários monitores, escala fracionária e o esquema claro nativo.
- Hardware de rede/Bluetooth (CC2 ainda não começou) e as transferências da
  Central com áudio pendente.
- Barra, launcher e Workspace, que não fazem parte dos assets.

## Publicação e artefatos

Preenchido depois da publicação, com o commit da tag, o run da CI e os hashes
dos downloads anônimos.
