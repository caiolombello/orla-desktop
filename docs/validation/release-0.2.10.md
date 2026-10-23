# Alpha 0.2.10 — registro da release

**Estado:** publicada como prerelease alpha (`latest=false`) em 23/10/2026 00:10:45 UTC,
a partir do `main` depois dos PRs 23–114.
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
- duas builds de release do mesmo commit, comparadas byte a byte;
- cada um dos 57 módulos `tests/test_*.py` incluídos no ZIP, rodado de dentro do
  pacote extraído, um processo por módulo, com Qt offscreen e estilo Fusion.

Essa rodada pelo pacote achou testes que dependiam de pastas que ficam fora do
ZIP: `addons/`, `bar/`, `layouts/`, `workspace/` e dois helpers de updates do
desktop. Agora a pasta `addons/` entra no ZIP e o teste da barra fica de fora.
Os quatro casos que precisam das outras pastas pulam só quando elas faltam e
continuam rodando no checkout e na CI. Os pulos restantes já existiam: KDE
ausente no calendário e casos nativos de TaskManager.

## Não qualificado

- Instalação e atualização em uma conta limpa e em outras distribuições.
- Vários monitores, escala fracionária e o esquema claro nativo.
- Hardware de rede/Bluetooth (CC2 ainda não começou) e as transferências da
  Central com áudio pendente.
- Barra, launcher e Workspace, que não fazem parte dos assets.

## Publicação e artefatos

A preparação entrou pelo [PR 115](https://github.com/caiolombello/orla-desktop/pull/115),
merge `534011993019e91716779ebaaf5d11f14eb03169`, que é o alvo da tag `v0.2.10`. A
primeira CI do PR falhou num teste que fixava a versão 0.2.9; depois da correção, o
[run 39871861622](https://github.com/caiolombello/orla-desktop/actions/runs/39871861622)
passou os dois jobs. A árvore do merge é idêntica à do último commit do PR.

Duas builds do merge exato produziram os mesmos bytes. O applet também é idêntico às
builds candidatas anteriores; o ZIP delas era diferente porque ainda não tinha as
correções de teste. Os três downloads anônimos retornaram HTTP 200 e são idênticos
às builds do merge; o `SHA256SUMS` publicado valida o applet e o ZIP.

| Asset | Tamanho | SHA-256 |
|---|---:|---|
| [Applet `.plasmoid`](https://github.com/caiolombello/orla-desktop/releases/download/v0.2.10/orla-dock-0.2.10.plasmoid) | 234,709 bytes | `0344cee25da2c8a8273f6fee173be4a070c878db93747be1b9892e72f2c169c7` |
| [Bundle ZIP](https://github.com/caiolombello/orla-desktop/releases/download/v0.2.10/orla-dock-0.2.10.zip) | 8,245,835 bytes | `c93a848ee674302262abc6d953c682a1cba043e9ad4df3607a1f09f874c887a1` |
| [`SHA256SUMS`](https://github.com/caiolombello/orla-desktop/releases/download/v0.2.10/SHA256SUMS) | 179 bytes | `aab90f6730d7275180d288987c936c090e8cfe0051e166e9b80e3c2de8ca1c46` |

O ZIP cresceu em relação à 0.2.9 porque carrega as capturas sintéticas claro/escuro
de `docs/`.

## Instalação a partir dos assets publicados

Pela primeira vez numa release, o caminho do README rodou com os arquivos baixados.
O ZIP foi extraído; `scripts/orla.py doctor` aprovou Python, `kpackagetool6`, `busctl`,
PySide6, a sessão D-Bus e o Plasma 6.7.5. Em seguida, `scripts/orla.py install
orla-dock-0.2.10.plasmoid` atualizou a dock deste usuário, que antes rodava o mesmo
código do `main` com a versão 0.2.9.

O que foi verificado depois da instalação:

- os arquivos instalados são idênticos ao `.plasmoid` publicado;
- os três serviços D-Bus gerenciados (integrações, complementos e temas) ficaram
  byte a byte iguais;
- depois de reiniciar o `plasmashell`, a leitura somente leitura do Plasma
  respondeu `{"docks":["0.2.10"]}`, sem erro da dock no journal;
- a CLI de updates do ZIP 0.2.9, consultada anonimamente no canal beta, respondeu
  `update_available` com a versão 0.2.10.

Isso cobre uma atualização numa conta já configurada. Instalação limpa, outra
distribuição e remoção continuam sem prova nesta release.
