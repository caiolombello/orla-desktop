# Decoração de janela Orla (opcional, experimental)

A decoração Orla dá às janelas do KDE a barra de título do macOS:

- **semáforos à esquerda**: fechar, minimizar e maximizar em discos de 12 px a
  cada 20 px. Os glifos (×, −, +) aparecem nos três quando o ponteiro passa
  sobre qualquer um deles. Em janelas inativas os discos ficam cinza;
- **barra de 28 px na cor da janela**, com título centralizado em seminegrito;
- **cantos superiores arredondados** (10 px), contorno fino e sombra suave mais
  longa embaixo. Janelas inativas têm sombra mais leve. Janelas maximizadas
  ficam sem sombra e sem cantos.

As cores seguem o esquema do sistema (claro ou escuro). É um tema QML do Aurorae
(`themes/kwin-decoration/`), carregado pelo próprio KWin.

## Usar e desfazer

```sh
python3 scripts/window_decoration.py install   # copia para ~/.local/share/kwin/decorations
python3 scripts/window_decoration.py apply     # lembra a decoração atual e usa a Orla
python3 scripts/window_decoration.py status
python3 scripts/window_decoration.py restore   # volta exatamente às chaves anteriores
```

`apply` muda só quatro chaves do grupo `[org.kde.kdecoration2]` no `kwinrc` do
usuário (`library`, `theme`, `ButtonsOnLeft=XIA`, `ButtonsOnRight=`) e pede ao
KWin para recarregar. O estado anterior fica em
`~/.local/state/orla/window-decoration.json`. `restore` regrava os valores
guardados ou apaga as chaves que não existiam, e aí os padrões do tema global
voltam a valer. Também dá para trocar em Configurações do sistema → Cores e
temas → Decorações da janela.

O KWin guarda o QML de uma decoração em cache durante a sessão. Por isso cada
versão do conteúdo é instalada com um id próprio (`kwin4_decoration_qml_orla_<hash>`).
Assim, `install` com a decoração ativa troca para a versão nova sem precisar sair
da sessão, e as versões antigas da Orla são apagadas.

## Limites

- Aplicativos que desenham a própria barra (navegadores, Electron, GTK com
  CSD) não usam a decoração do KWin.
- Os cantos inferiores continuam retos: o conteúdo da janela é desenhado pelo
  aplicativo, por cima da decoração.
- O botão de menu da janela, "manter acima" e os demais botões extras não são
  desenhados. O menu da janela continua no clique direito da barra de título.
- Os testes (`tests/test_window_decoration.py`) carregam o QML com um dublê do
  módulo de decoração do KWin e conferem geometria, hover, janela inativa e
  maximizada. Os comandos rodam com `kwriteconfig6` e `busctl` falsos. Na sessão
  real (Plasma 6.7.5/Wayland, escala 1,45, esquema escuro) foram observados os
  semáforos, os glifos no hover e o título centralizado. A versão nova carregou
  sem sair da sessão ao trocar o id (prova feita com um id temporário). Esquema claro, outras escalas e múltiplos monitores não foram
  observados.
