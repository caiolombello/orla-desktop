# Visual macOS em um passo (opcional, experimental)

`scripts/macos_look.py` reúne os ajustes do Orla que aproximam a sessão do KDE
do macOS e os desfaz do mesmo jeito:

| Parte | O que muda | Guia |
|---|---|---|
| Tema Plasma Orla | barra, popups, notificações e dicas em vidro com desfoque; dock e popups do Orla foscos | [plasma-theme.md](plasma-theme.md) |
| Decoração Orla | semáforos à esquerda, título central, cantos e sombra | [window-decoration.md](window-decoration.md) |
| Alternador de janelas | Alt+Tab com ícones grandes e um item por aplicativo, sem escurecer as outras janelas (como o Cmd+Tab) | — |
| Minimizar | efeito "lâmpada mágica" em vez de "encolher" (parecido com o Gênio); se o KWin não carregar a lâmpada, fica "encolher" | abaixo |
| Cantos ativos | canto superior esquerdo abre a Visão Geral (como o Mission Control); canto inferior direito mostra a área de trabalho. O superior direito fica livre para a Central de Controle e o relógio da barra | — |
| Busca (Spotlight provisório) | KRunner flutuante no alto, ao centro, como o Spotlight | abaixo |
| Relógio da barra | data ao lado da hora, como na barra de menus ("dom. 25 out. 11:24") | abaixo |
| Notificações | banners no estilo macOS no canto superior direito e central agrupada por app | abaixo |
| Bandeja | brilho (já na Central de Controle) e área de transferência (Meta+V) passam para a seta | abaixo |

```sh
python3 scripts/macos_look.py apply     # aplica tudo e guarda o estado anterior
python3 scripts/macos_look.py status
python3 scripts/macos_look.py restore   # volta a cada configuração anterior
```

O tema e a decoração guardam o próprio estado. As sete chaves do KWin
(`[TabBox] LayoutName`, `ApplicationsMode` e `HighlightWindows`; `[Plugins]
magiclampEnabled` e `squashEnabled`; `[Effect-overview] BorderActivate=7` e
`[ElectricBorders] BottomRight=ShowDesktop`) e a do KRunner (`krunnerrc
[General] FreeFloating`) ficam salvas em `~/.local/state/orla/macos-look.json`
antes da primeira mudança. `restore` regrava cada uma ou apaga as que não
existiam, e os efeitos de minimizar trocam na hora (`loadEffect`/`unloadEffect`).
Aplicar de novo mantém o primeiro estado salvo, e restaurar de novo não muda
nada. Um estado salvo antes de o KRunner fazer parte do visual ganha a chave
dele no próximo `apply`; sem ela, `restore` não toca no `krunnerrc`. `plasma_theme.py
restore` sem estado salvo agora recusa, em vez de trocar para o tema padrão.

## Minimizar

Depois de ligar a lâmpada mágica, `apply` pergunta ao KWin se ela carregou
(`isEffectLoaded` em `org.kde.KWin /Effects`). Se o KWin responder que não (uma
versão sem o efeito ou uma GPU sem suporte), `apply` volta para "encolher",
avisa no terminal e grava `"minimize": "squash"` no estado; `status` mostra o
mesmo campo. `"unverified"` indica que o KWin não respondeu, e então nada é
trocado. O estado original salvo não muda, então `restore` volta aos valores de
antes do primeiro `apply`. Quando a lâmpada voltar a carregar, um novo `apply`
a liga de novo.

## Busca (Spotlight provisório)

Enquanto o Orla não tem a própria busca no lugar do Spotlight, `apply` deixa o
KRunner do KDE flutuante (`FreeFloating=true`): ele abre no alto, ao centro da
tela, em vez de descer da borda. O histórico e a busca anterior já vêm ligados
no KDE; quem os desligou continua com essa escolha, porque `apply` não mexe
neles.

A chave é gravada com `kwriteconfig6 --notify`, que avisa os programas que
observam o `krunnerrc`. Pelo código do KDE, um KRunner em execução relê o grupo
`[General]` ao receber esse aviso, sem reiniciar; se não reler, a posição nova
vale na próxima vez que ele abrir. Isso não foi observado numa sessão real, só
nos testes com ferramentas falsas.

Os atalhos globais não mudam. No KDE, Alt+Espaço (e Alt+F2) abre o KRunner; a
tecla Meta sozinha abre o lançador do painel, que busca com os mesmos módulos
do KRunner, mas não nessa janela flutuante. Meta+Espaço, o mais parecido com o
Cmd+Espaço, pode conflitar com a troca de layout de teclado do IBus; se for
usá-lo, ajuste em Configurações do sistema → Atalhos.

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

## Notificações

O applet **Notificações Orla** (`notifications/`, `org.orla.notifications`)
mostra as notificações do serviço do próprio Plasma no formato do macOS:

- **Banner:** ícone do app à esquerda, nome do app e hora em cima, título em
  negrito e texto simples abaixo. O mais novo fica em cima e empurra os outros
  para baixo, no canto superior direito, até 80% da altura da tela. Ao passar o
  mouse, aparecem o botão de fechar (canto superior esquerdo, como no macOS) e
  as ações. A contagem do tempo pausa enquanto o banner é lido. Tarefas (cópias
  de arquivo) mostram barra de progresso, pausar e cancelar.
- **Central:** ao clicar no ícone da bandeja, lista por app (até três por
  grupo), "Limpar", "Limpar tudo" e a chave de Não perturbe.

O servidor, o histórico, as ações, as respostas e o Não perturbe continuam do
KDE. As regras são as do applet do KDE 6.7.5: expiração, notificações
residentes, ação padrão ou janela do app, som, inibição por app, tela cheia e
telas espelhadas. Só a apresentação muda. Para não haver popups em dobro, o
applet **substitui** o de notificações do KDE na bandeja, no mesmo lugar e com
a mesma escolha de exibir ou ocultar:

```sh
python3 scripts/macos_notifications.py install   # instala/atualiza o applet deste checkout
python3 scripts/macos_notifications.py apply     # troca o applet do KDE pelo Orla na bandeja
python3 scripts/macos_notifications.py status
python3 scripts/macos_notifications.py restore   # devolve as listas da bandeja salvas
```

As listas da bandeja (`extraItems`, `hiddenItems`, `shownItems`,
`knownItems`) ficam em `~/.local/state/orla/macos-notifications.json` antes da
primeira troca. A troca passa pelos scripts do Plasma, e a bandeja carrega e
descarrega os applets na hora. O applet também aparece em "Mostrar
alternativas…" do applet de notificações do KDE (`X-Plasma-Provides`).

Atualizar ou remover o pacote de um applet da bandeja faz a bandeja esquecê-lo.
Por isso `install` recoloca o Orla depois de atualizá-lo, e `apply` repara uma
bandeja que o perdeu. `status` mostra `null` quando não há nenhum applet de
notificações. Antes de remover o pacote, rode `restore` para voltar ao do KDE.

Testes: `tests/test_notifications.py` cobre o texto simples, os tempos, o
empilhamento, o agrupamento, o banner (teclado, foco, expiração e progresso) e a
central. `tests/test_macos_notifications.py` roda o script da bandeja num
QJSEngine. Em Plasma 6.7.5/Wayland (uma tela, escala 1,45, esquema escuro) foram
observados o banner, o empilhamento, a expiração, a ausência de popup duplicado
e a inibição por app. A central aberta pela bandeja e as ações ao passar o
mouse foram verificadas só fora da sessão. Arrastar arquivos do banner ainda
não existe.

**Resposta e miniatura.** Quando o app oferece resposta (como o KDE Connect),
"Responder" abre um campo no próprio banner. Enter envia o texto, Esc fecha sem
enviar, e o banner fica enquanto você escreve. Só nesse momento a janela do
banner aceita o teclado. Quando a notificação traz uma imagem local (por
exemplo, uma captura do Spectacle), ela aparece como miniatura à direita.

Os testes (`tests/test_macos_look.py`) rodam a ida e a volta completas com
`kwriteconfig6`, `kreadconfig6`, `plasma-apply-desktoptheme` e `busctl` falsos,
num diretório pessoal temporário, incluindo o KRunner (com e sem valores
anteriores), aplicar duas vezes e a volta para "encolher".

## Bandeja

`scripts/menu_bar_tray.py apply|status|restore` deixa a bandeja da barra tão
enxuta quanto a do macOS. O brilho, que já está na Central de Controle, e a
área de transferência, que abre com Meta+V, passam para a seta da bandeja e
continuam funcionando ali. Itens que você fixou como "sempre visíveis" não
mudam. `restore` volta a mostrar só os itens que `apply` ocultou e preserva
outras mudanças feitas depois. A lista anterior fica em
`~/.local/state/orla/menu-bar-tray.json`; `tests/test_menu_bar_tray.py` cobre
os casos.

## Pilha de Downloads

Opcional e global, em **Widgets › Mostrar os Downloads ao lado da Lixeira**.
Como no Dock do macOS, um ícone de pasta fica antes da Lixeira, depois do mesmo
divisor. Um clique abre um popup com até 12 itens mais recentes da pasta
Downloads (do mais novo para o mais antigo), com miniatura para imagens e ícone
por tipo para o resto. Downloads em andamento (`.part`, `.crdownload` e afins)
e arquivos ocultos não aparecem. Um clique num item o abre no aplicativo
padrão; **Abrir a pasta Downloads** abre a pasta. Tab e as setas passam pelos
itens, com o anel de foco visível. A pilha só lê a pasta: não move, apaga nem
renomeia nada.
