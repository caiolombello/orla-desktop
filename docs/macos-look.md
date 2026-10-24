# Visual macOS em um passo (opcional, experimental)

`scripts/macos_look.py` reúne os ajustes do Orla que aproximam a sessão do KDE
do macOS e os desfaz do mesmo jeito:

| Parte | O que muda | Guia |
|---|---|---|
| Tema Plasma Orla | barra, popups, notificações e dicas em vidro com desfoque; dock e popups do Orla foscos | [plasma-theme.md](plasma-theme.md) |
| Decoração Orla | semáforos à esquerda, título central, cantos e sombra | [window-decoration.md](window-decoration.md) |
| Alternador de janelas | Alt+Tab com ícones grandes e um item por aplicativo, sem escurecer as outras janelas (como o Cmd+Tab) | — |
| Minimizar | efeito "lâmpada mágica" em vez de "encolher" (parecido com o Gênio) | — |

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

Os testes (`tests/test_macos_look.py`) rodam a ida e a volta completas com
`kwriteconfig6`, `kreadconfig6`, `plasma-apply-desktoptheme` e `busctl` falsos,
num diretório pessoal temporário.
