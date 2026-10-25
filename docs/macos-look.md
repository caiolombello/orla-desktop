# Visual macOS em um passo (opcional, experimental)

`scripts/macos_look.py` reúne os ajustes do Orla que aproximam a sessão do KDE
do macOS e os desfaz do mesmo jeito:

| Parte | O que muda | Guia |
|---|---|---|
| Tema Plasma Orla | barra, popups, notificações e dicas em vidro com desfoque; dock e popups do Orla foscos | [plasma-theme.md](plasma-theme.md) |
| Decoração Orla | semáforos à esquerda, título central, cantos e sombra | [window-decoration.md](window-decoration.md) |
| Alternador de janelas | Alt+Tab com ícones grandes e um item por aplicativo, sem escurecer as outras janelas (como o Cmd+Tab) | — |
| Minimizar | efeito "lâmpada mágica" em vez de "encolher" (parecido com o Gênio) | — |
| Relógio da barra | data ao lado da hora, como na barra de menus ("dom. 25 out. 11:24") | abaixo |

```sh
python3 scripts/macos_look.py apply     # aplica tudo e guarda o estado anterior
python3 scripts/macos_look.py status
python3 scripts/macos_look.py restore   # volta a cada configuração anterior
```

O tema e a decoração guardam o próprio estado. As cinco chaves do KWin
(`[TabBox] LayoutName`, `ApplicationsMode` e `HighlightWindows`; `[Plugins]
magiclampEnabled` e `squashEnabled`) ficam salvas em
`~/.local/state/orla/macos-look.json` antes da primeira mudança. `restore`
regrava cada uma ou apaga as que não existiam, e os efeitos de minimizar trocam
na hora (`loadEffect`/`unloadEffect`). Aplicar de novo mantém o
primeiro estado salvo, e restaurar de novo não muda nada. `plasma_theme.py
restore` sem estado salvo agora recusa, em vez de trocar para o tema padrão.

## Relógio da barra

`scripts/menu_bar_clock.py apply|status|restore` muda só o relógio do KDE que
está num painel superior junto do Menu Orla (`org.orla.bar`). Os relógios da
área de trabalho e de outros painéis ficam como estão. A mudança passa pela API
de scripts do Plasma, então aparece na hora, sem reiniciar. São quatro chaves do
grupo `Appearance`: `showDate=true`, `dateFormat=custom`,
`customDateFormat=ddd d MMM` e `dateDisplayFormat=1` (ao lado da hora). Os
nomes do dia e do mês seguem o idioma do sistema.

Os valores anteriores ficam em `~/.local/state/orla/menu-bar-clock.json`, e
aplicar de novo mantém os primeiros. Como os scripts do Plasma não apagam
chaves, `restore` regrava os valores lidos antes. Para uma chave que não
existia, isso é o padrão do KDE, com o mesmo resultado na tela. Sem Plasma em
execução ou sem barra Orla, `macos_look.py apply` segue sem o relógio.

Assim como qualquer ajuste feito pelo próprio Plasma, isso altera o arquivo de
configuração dos painéis. Um `layout restore` do arquivo inteiro já recusa
quando esse arquivo mudou depois do recibo, e continua recusando.

Os testes (`tests/test_menu_bar_clock.py`) rodam o script do Plasma de verdade
num QJSEngine, com painéis falsos.

Os testes (`tests/test_macos_look.py`) rodam a ida e a volta completas com
`kwriteconfig6`, `kreadconfig6`, `plasma-apply-desktoptheme` e `busctl` falsos,
num diretório pessoal temporário.
