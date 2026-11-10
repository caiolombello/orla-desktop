# Paridade com o macOS — conferência nativa de 09–10/11/2026

**Estado:** observações delimitadas, feitas na sessão do mantenedor depois dos
PRs 163–170. Nenhum gate do roadmap fecha só com este registro.

**Ambiente:** Fedora 44, Plasma 6.8.2, KWin Wayland, uma tela 4K em escala 1,45,
esquema escuro, tema Plasma Orla ativo. Dock e barra instaladas a partir do
`main` (dock com o PR 170), `macos_look.py apply` reaplicado.

## Como foi feito

- Cliques por um ponteiro virtual (uinput), só com a sessão ociosa e sem mídia
  tocando. Capturas recortadas na região observada e apagadas em seguida.
- Ações sobre janelas só em **janelas de teste descartáveis**: uma janela Qt de
  cor sólida por app, cada uma com seu `app_id` e em seu próprio escopo systemd.
  As ações que alcançariam as janelas do mantenedor ("Ocultar outros") não foram
  acionadas.
- O estado das janelas veio do KWin (`getWindowInfo`: `minimized`, `pid`) e da
  saída dos processos, não da aparência.

Uma armadilha ficou registrada: uma janela aberta por um processo filho de um
AppImage herda `APPDIR`, e o KDE a identifica como janela desse aplicativo. As
primeiras janelas de teste apareceram na barra com o nome do aplicativo que as
lançou; "Encerrar" teria alcançado as janelas dele. Elas foram relançadas sem
essas variáveis antes de qualquer ação.

## O que foi observado

| Área | Observação |
|---|---|
| Barra em Plasma 6.8 (PR 168) | Antes: "Área de trabalho" com uma janela ativa. Depois: o nome do aplicativo ativo. Nenhum erro de QML da barra no journal |
| Menu do aplicativo na barra (PR 169) | O nome em negrito abre o menu abaixo dele, com "Ocultar" e "Encerrar" nomeando o app ativo; Esc fecha. **Mostrar tudo** restaurou a janela de teste minimizada e ficou desativado na abertura seguinte. **Ocultar** minimizou a janela de teste ativa e não tocou na outra, de outro app. **Encerrar** fechou a janela ativa (o processo saiu) e deixou a outra aberta |
| Menu da dock (PR 166) | O botão direito num app com janela mostra o nome do app e as linhas "Mostrar todas as janelas", "Ocultar" e "Encerrar"; com uma só área de trabalho, "Opções" não aparece. **Mostrar todas as janelas** ativou o efeito `windowview` do KWin e Esc saiu dele. **Ocultar** minimizou a janela de teste |
| Popups da dock no vidro do tema (PR 170) | Antes: borda de baixo reta, cantos inferiores quadrados (calendário e menu de tarefas). Depois: os quatro cantos arredondados e a margem inferior igual à superior, com o vão acima da dock |
| Pilha de Downloads (PR 159) | O ícone aparece ao lado da Lixeira com `showDownloads` ligado |
| Visual em um passo (PRs 160, 163) | `status` depois de `apply`: cantos ativos gravados, `FreeFloating=true` no `krunnerrc` e `minimize: "magiclamp"` (o KWin respondeu que o efeito carregou) |

## O que não foi observado

- A animação de minimizar chegando ao ícone da dock (PR 167). Só há a resposta
  do KWin de que a lâmpada mágica carregou.
- "Ocultar outros" na barra e "Encerrar" e "Mover para a área de trabalho" na
  dock. "Encerrar" na dock usa o mesmo pedido de fechamento observado na barra.
- O Menu Orla aberto: ações de sessão, "Recentes" e o selo de atualizações em
  Plasma 6.8.
- O KRunner flutuante aberto e os cantos ativos em uso.
- O launcher com as novas fontes de busca (PR 165): não foi reinstalado.
- Esquema claro, mais de uma tela, outra escala, X11 e leitor de tela.
