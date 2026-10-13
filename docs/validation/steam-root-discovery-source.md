# Descoberta opcional de pastas Steam — Source

Incremento de S1 em 13/10/2026, empilhado sobre os presets de aparência.
Abrir Steam no launcher continua passivo. **Localizar pastas do Steam** consulta
quatro entradas conhecidas, resolve aliases e preenche raízes canônicas sem
duplicatas. Não enumera jogos, lê arquivos, inicia helper ou abre o cliente.
**Carregar jogos** continua sendo uma ação explícita separada.

Sem resultados, o campo manual é preservado. A mensagem da descoberta é
independente do estado do inventário; localizar depois de uma consulta não apaga
jogos, revisão ou status. Durante operação ou fechamento, a ação fica bloqueada.
O campo, os controles nativos e o contorno de foco seguem o sistema visual Orla.

## Verificação

- Checkout integrado: configure e build completos com Qt 6.11.2 passaram.
  CTest Steam passou, 1/1 em 15,79 s; as 24 entradas QtTest incluem localização,
  deduplicação, entradas inválidas, isolamento, scan e encerramento do helper.
- Dois casos da UI compilada passaram nos estilos Fusion e `org.kde.desktop`
  (quatro entradas por estilo, incluindo início/fim). Cobrem carregamento
  explícito, Escape e bloqueio das ações concorrentes.
- Vinte testes Python Steam e sete design guards passaram; design check sem
  issues. A galeria KDE completa foi revisada nas schemes clara e escura.
  O launcher mantém sua scheme escura nas duas.
- Revisão independente aprovada: 24 entradas Fusion e quatro KDE passaram;
  arquivos congelados permaneceram iguais. O recibo privado corrigido esclarece
  o hash do inventário sem alterar o candidato ou apagar o recibo anterior.
- No candidato isolado, os testes do painel em 440/660 px e as capturas focadas
  passaram nos dois estilos. A galeria Fusion completa falhou duas vezes antes
  de alcançar Steam, em `StopIteration` do render da dock não alterada.
  Essa falha permanece registrada; não há PASS agregado da galeria Fusion.

| Fusion — 440 px | KDE — 440 px |
|---|---|
| ![Descoberta Fusion](../screenshots/steam-discovery/steam-fusion-440.png) | ![Descoberta KDE](../screenshots/steam-discovery/steam-kde-440.png) |

Capturas sintéticas offscreen, com o botão focado e o estado sem pastas.
Não mostram bibliotecas pessoais nem a sessão KDE real.

## Limites e próximo gate

Os demais CTests e a UI completa do launcher não foram repetidos nesta fatia.
Descoberta real, instalação deste incremento, foco Plasma/Wayland, cliente,
handler, conta, execução de jogos e disco externo permanecem UNRUN.
Presença da pasta não comprova instalação do cliente, conectividade ou
titularidade. As quatro consultas síncronas podem demorar em filesystem
indisponível; esta fatia não oferece deadline de descoberta.

Próximo gate: instalar um build com helpers versionados, exercitar o gesto de
localizar/carregar na sessão KDE e conferir seleção por teclado sem executar
jogos. Depois, qualificar separadamente dois jogos e a matriz de bibliotecas.
S1 continua parcial; este incremento não modifica os assets públicos 0.2.9.
