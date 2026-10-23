# Tema Plasma Orla (opcional, experimental)

O tema Orla dá ao Plasma o vidro do macOS onde o KDE desenha molduras:

- **barra superior**: translúcida, com desfoque real e saturação, sem sombra,
  como a barra de menus do macOS;
- **popups e notificações** (calendário, bandeja, notificações, diálogos do
  Plasma): vidro arredondado (16 px), contorno fino e sombra suave;
- **dicas**: cantos de 8 px;
- **cabeçalhos dos popups**: sem a faixa do Breeze, só uma linha fina.

O desfoque é feito pelo KWin; o tema só define a forma, a transparência e os
parâmetros de contraste (`saturation=1.8`). Cores seguem o esquema do sistema
(claro ou escuro), porque o tema não traz arquivo `colors`. Todo o resto
(botões, barras de rolagem, ícones do Plasma) vem do tema padrão do KDE.

## Usar e desfazer

```sh
python3 scripts/plasma_theme.py install   # grava em ~/.local/share/plasma/desktoptheme/orla
python3 scripts/plasma_theme.py apply     # lembra o tema atual e troca para Orla
python3 scripts/plasma_theme.py status    # tema ativo e para qual voltaria
python3 scripts/plasma_theme.py restore   # volta ao tema lembrado
```

`apply` e `restore` usam `plasma-apply-desktoptheme`; não é preciso reiniciar o
Plasma. A troca também pode ser feita em Configurações do sistema → Cores e
temas → Tema do Plasma. `build DIR` gera o mesmo tema num diretório, com bytes
idênticos entre builds.

## Limites

- Sem efeito de desfoque (KWin sem composição ou com o efeito desligado), o
  Plasma usa as variantes quase opacas do tema.
- A dock e os popups do próprio Orla ainda desenham o vidro Orla, sem desfoque.
- A barra mantém as margens de 4 px do Breeze, que os testes de encaixe da barra
  supõem.
- Os testes (`tests/test_plasma_theme.py`) conferem a geração: peças com limites
  exatos, máscara de desfoque, margens, sombra fora do vidro e build
  determinístico. A aparência foi observada em Plasma 6.7.5/Wayland, escala
  1,45, esquema escuro; esquema claro nativo, outras escalas e múltiplos
  monitores não foram observados.
