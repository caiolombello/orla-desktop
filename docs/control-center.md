# Central de Controle (experimental)

A alpha 0.2.9 entregou a fatia CC0 de estado e atalhos, sem controles diretos.
A alpha 0.2.10 acrescenta os controles diretos experimentais descritos abaixo:
áudio (CC1-A), brilho (CC1-B), Não perturbe (CC1-C) e microfone (CC1-D).

Ative **Mostrar Central de Controle no dock (global)** em **Widgets** para
exibir o botão opcional. A preferência herdada de CC0 é global, começa
desligada, é salva imediatamente e permanece fora dos perfis.

O Source S1 também oferece **Mostrar Central de Controle na barra**. Uma
instância separada do módulo `control-center` no preset fica à direita,
depois da bandeja e antes do relógio; o módulo começa desativado. Essa instância
usa `showOrlaMenu=false`, `showApplicationName=false` e `showControlCenter=true`.
A instância do Menu Orla permanece independente à esquerda. Para alterar o
layout, prepare e revise o plano com o helper `orla layout` antes de aplicar.
Para uma barra gerenciada existente com recibo original v1, `layout plan-update`
e `layout update` acrescentam essa entrada preservando a configuração atual e
o primeiro banco de recuperação. Veja os [comandos e limites](../bar/README.md#adicionar-a-central-à-barra-existente).

As duas entradas usam a mesma Central e o mesmo estado de áudio do dock.
Desativar/remover a entrada da barra preserva dock, pins e perfis; ocultar o
botão do dock não fecha uma abertura originada pela barra. A rota experimental
exige uma única Orla Dock compatível; falta/ambiguidade deixa a entrada
indisponível. A qualificação da barra na sessão real ainda é o gate S2, conforme
o [registro Source compartilhado](validation/shared-control-center-source.md).

Além dos cards compartilhados de mídia MPRIS e bateria, o card de áudio
permite:

- ajustar o volume da saída padrão entre 0% e 100%;
- silenciar ou reativar o som por ação explícita, sem ligar ou desligar o mudo
  implicitamente ao mover o volume;
- escolher entre as saídas elegíveis e solicitar uma nova saída padrão.

No contrato do Orla, abrir o popup não solicita uma mudança de áudio. Cada
escrita exige mover o slider, acionar o botão de mudo ou escolher uma saída. O
controle acompanha mudanças externas e só considera uma operação concluída
quando um snapshot posterior converge para o valor solicitado. Essa
convergência prova o estado observado, mas não a origem ou causalidade da
mudança. Carregar o adaptador nativo ainda pode ativar o serviço de áudio; esse
efeito exige o gate nativo descrito na validação.

Enquanto uma alteração aguarda confirmação, o card mostra estado pendente. Uma
falha imediata, remoção do alvo ou timeout produz erro local e restaura uma
apresentação confirmada ou ainda supervisionada, conforme o alvo. O ID da saída
é capturado no gesto: trocar a saída padrão durante um drag não redireciona a
escrita para o novo dispositivo. Não há movimentação de streams individuais.

Se o backend de áudio estiver ausente, somente o card correspondente fica
indisponível. O atalho explícito **Abrir Som no KDE** permanece disponível como
fallback. Seu despacho não comprova que a janela abriu nem que uma configuração
mudou.

Os títulos, valores, detalhes e erros usam o esquema do popup
(`dock.popupScheme`), que acompanha a luminosidade do sistema. Cards e controles
herdam a paleta correspondente; as cores personalizadas do dock permanecem no
seu vidro, conforme [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md). A mudança visual não
qualifica os serviços ou hardware nativos.

## Layout em grade, inspirado no macOS

A Central organiza os módulos como no macOS. Com largura para duas colunas
(300 px ou mais), a primeira linha junta Wi-Fi e Bluetooth num módulo, ao lado
de **Tocando agora**. A segunda traz **Não perturbe** e **Microfone** lado a
lado. Abaixo ficam os módulos de largura total: **Tela**, **Som** e **Energia**,
e no fim **Ajustes do sistema…**. Em larguras menores, a mesma ordem vira uma
coluna, com rolagem e foco visível no controle ativo.

Os módulos são compactos para caber sem rolagem mesmo quando o Plasma limita
o popup a cerca de 720 px: **Tocando agora** põe a arte ao lado do texto ("Nada
tocando" quando não há player), **Som** dispensa a legenda da saída (o seletor
mantém o nome acessível) e **Energia** põe o perfil na mesma linha da bateria.

Cada linha de rádio tem o botão redondo, que liga ou desliga, e o nome com o
estado. Nas linhas de Wi-Fi e Bluetooth, o nome é um botão que abre a página
do KDE correspondente. Ele mostra realce ao passar o mouse, anel de foco e uma
dica. Som e Energia levam o atalho para o KDE como uma seta no título do módulo.
O popup não tem título visível; o nome acessível continua sendo "Central de
Controle". Nenhuma regra de confirmação mudou: os estados seguem os mesmos
serviços e as mesmas mensagens descritas abaixo.

Capturas sintéticas: [escuro](screenshots/control-center-grid/dark.png) e
[claro](screenshots/control-center-grid/light.png).

## Brilho da tela — CC1-B

O card **Tela** mostra um slider por tela com brilho ajustável (até quatro),
com o nome da tela quando houver mais de uma. Os valores vêm do mesmo modelo do
applet de brilho do Plasma (`org.kde.plasma.private.brightnesscontrolplugin`,
PowerDevil) e acompanham mudanças feitas fora do Orla, como teclas de brilho.
O adaptador só é carregado no painel real, enquanto a Central está aberta.

Cada escrita vem de mover o slider por arraste ou teclado. Ela vai ao serviço por
`org.kde.ScreenBrightness.Display.SetBrightnessWithContext`, sem o indicador do
Plasma e com contexto próprio do Orla. A alteração só conta como concluída quando
o PowerDevil anuncia o novo valor. Por isso o Orla não usa o `setBrightness` do
modelo: ele atualiza o próprio modelo antes do serviço e descarta o eco. Há uma
alteração em voo por tela; durante um arraste, só o valor mais recente aguarda a
confirmação anterior. Recusa do serviço ou ausência de confirmação em 3 segundos
mostra erro no card e volta ao valor atual. O mínimo é 1%, para não apagar painéis
internos que desligam em zero.

Sem tela ajustável, ou com o serviço indisponível, só esse card fica desativado e
diz o motivo; sem o módulo do PowerDevil o card não aparece. A Central passou a
caber em até 620 px de altura para mostrar todos os módulos sem rolagem em telas
comuns, e o orçamento do popup continua limitando telas baixas.

Na sessão Plasma 6.7.5 deste registro, com um monitor externo por DDC/CI, o
card leu 100%. Duas setas para a esquerda pelo teclado levaram o monitor a 98%
(9800 de 10000, conferido no D-Bus) sem erro após o prazo; duas para a direita
voltaram a 100%. Uma mudança feita por fora apareceu no card sem escrita do Orla.
A primeira versão, que escrevia pelo modelo, foi recusada nessa prova: mostrava
o valor certo, mas acusava falta de confirmação. Tela interna, várias telas,
Wayland com escala diferente e o applet de brilho aberto ao mesmo tempo não foram
exercitados.

## Não perturbe — CC1-C

O card **Não perturbe** usa as mesmas configurações e regras do applet de
notificações do Plasma (`org.kde.notificationmanager`). Ligar pelo Orla ou pelo
Plasma é um único estado, e o card mostra o motivo: sem prazo, até uma data, por
um aplicativo ou por uma regra do KDE (tela cheia, espelhamento).

Ligar grava o prazo de um ano usado pelo próprio toggle do Plasma; desligar limpa
o prazo e revoga inibições de aplicativos, também como o Plasma. A mudança só
conclui quando o servidor de notificações publica o novo estado, calculado pelo
applet. Se uma regra do KDE mantiver o modo ativo, o card diz isso após 3 segundos
em vez de mostrar sucesso; o Orla não sobrepõe essas regras. Sem o servidor de
notificações, só este card fica desativado. O botão continua focável durante a
confirmação, e um segundo pedido é ignorado até a primeira resposta.

Na sessão Plasma 6.7.5 deste registro, Espaço no botão ligou o modo (`Inhibited`
verdadeiro no D-Bus) e mostrou “Ativado até você desativar”; outro Espaço desligou.
O `plasmanotifyrc` terminou idêntico ao anterior. A primeira versão desativava o
botão durante a confirmação e perdia o foco do teclado; a prova nativa mostrou o
defeito, corrigido e coberto por teste.

CC1 continua parcial. O microfone está na seção seguinte; os gates reais do
serviço de áudio ainda estão abertos; rede, Bluetooth e energia pertencem às
fatias seguintes. Instalação, módulo privado do Plasma-PA, Pulse/PipeWire,
barramento da sessão, compositor, seat, hardware, popup nativo e painel
instalado permanecem sem validação.

Veja a [validação Source de áudio](validation/control-center-audio-source.md) e
os registros das alphas [0.2.9](validation/control-center-peripherals-0.2.9.md) e
[0.2.10](validation/release-0.2.10.md).

## Microfone — CC1-D

O card **Microfone** silencia e reativa a entrada padrão do servidor de áudio,
lida pelo mesmo módulo Plasma-PA do applet de volume. Só a entrada padrão muda,
porque é dela que os aplicativos gravam quando não escolhem outra. Um monitor de
saída ou a fonte nula não contam como microfone.

A alteração só conclui quando o serviço de áudio publica o novo estado para a
mesma entrada. Uma escrita recusada, a falta de confirmação em 3 segundos ou a
troca da entrada padrão durante o pedido mostram um erro em vez de um mudo que
não aconteceu. Abrir a Central não grava nada. Sem microfone ou sem o serviço de
áudio, só este card fica desativado, e mudanças feitas fora do Orla aparecem como
estão. O botão continua focável durante a confirmação, como no Não perturbe.

Na sessão Plasma 6.7.5 deste registro, com nenhum aplicativo gravando, o card
mostrou a entrada padrão real como ligada. Um clique silenciou (`pactl
get-source-mute` respondeu sim) e Espaço reativou. Silenciar e reativar pelo
`pactl` apareceram no card. O microfone terminou ligado, como estava antes, e o
journal não registrou erro da dock.

Com o microfone, todos os cards básicos do CC1 existem e passaram por uma prova
nativa nesta máquina. O aceite completo continua aberto: outros ambientes,
hardware ausente de verdade e as transferências com áudio pendente.

## Perfil de energia — CC2-A

O card **Energia** ganhou uma lista **Perfil de energia** com os perfis que o
sistema oferece: Economia de energia, Equilibrado e Desempenho. Ela usa o mesmo
serviço do applet de bateria do Plasma (PowerDevil, que repassa ao
`power-profiles-daemon` ou ao `tuned-ppd`), então escolher no Orla ou no Plasma é
um único estado. A leitura só acontece com a Central aberta.

O Orla fala com o PowerDevil direto pelo D-Bus, sem o `PowerProfilesControl` do
applet. Esse controle marca o perfil como ativo assim que a chamada responde, antes
de o serviço aplicar. O Orla só conclui a troca quando o PowerDevil anuncia o novo
perfil. Se o anúncio se perder, ele lê o perfil atual do serviço depois da resposta.
Uma recusa ou a falta de confirmação em 3 segundos mostram erro e voltam ao perfil
real. A lista continua focável durante a confirmação, e uma segunda escolha é
ignorada até a primeira terminar.

Quando o serviço informa um motivo, o Desempenho fica indisponível e o card explica
por quê: computador no colo ou quente demais. Com o Desempenho ativo e reduzido, o
card avisa. Um perfil mantido por um aplicativo, como o GameMode, mostra quem o
mantém. Perfis com nomes desconhecidos não aparecem. Sem serviço de perfis, só a
lista some; o resumo da bateria e **Abrir Energia no KDE** continuam.

Na sessão Plasma 6.7.5 deste registro, com `tuned-ppd` atendendo o serviço de
perfis, a lista abriu com os três perfis e mostrou Desempenho, o perfil atual.
A primeira prova falhou: o card disse que o serviço recusou a troca, sem fingir
sucesso. A captura do D-Bus mostrou o motivo: o `setProfile` saiu sem argumento,
porque o módulo D-Bus do Plasma só envia argumentos com a assinatura entre
parênteses (`(s)`). Depois da correção, coberta pelo teste do adaptador:

- um clique em Equilibrado levou o PowerDevil e o daemon a `balanced`;
- com o foco de teclado visível na lista, a seta para baixo pediu Desempenho, e o
  foco ficou na lista;
- duas trocas feitas por fora, pelo `busctl`, apareceram no card;
- Escape fechou a Central.

A dock fez uma chamada `setProfile` por ação, com o argumento certo. O perfil
terminou em Desempenho, como estava antes, e o journal não registrou erro da dock.
Desempenho bloqueado (computador no colo ou quente), perfis mantidos por apps e um
sistema sem daemon de perfis só foram exercitados nos testes.

## Wi-Fi — CC2-B

O card **Wi-Fi** liga e desliga o rádio Wi-Fi pela mesma biblioteca do applet de
rede do Plasma (`plasma-nm`, sobre o NetworkManager). Ele mostra a rede
conectada, “Ligado · sem conexão” ou “Desligado”. Uma chave do computador ou um
bloqueio de rádio aparece como “Desligado por uma chave do computador”; nesse caso
o Orla não tenta ligar e explica por quê. **Abrir Rede no KDE** abre as
configurações de rede do sistema.

A troca só conclui quando o NetworkManager publica o novo estado do rádio. O Orla
não marca a mudança por conta própria: a biblioteca só pede a alteração, e o estado
mostrado vem dos avisos do serviço. Uma recusa ou a falta de confirmação em 3
segundos mostram erro, por exemplo quando uma política nega a mudança. O botão
continua focável durante a confirmação, e um segundo pedido é ignorado até a
resposta. Sem adaptador Wi-Fi, só este card fica desativado. A leitura só acontece
com a Central aberta.

Na sessão Plasma 6.7.5 deste registro, com o computador ligado à rede por cabo e
o Wi-Fi sem rede conectada, o card mostrou “Ligado · sem conexão”:

- um clique desligou o rádio, e o `nmcli` confirmou;
- Espaço religou;
- desligar e religar pelo `nmcli` apareceu no card;
- com Tab, o contorno de foco ficou visível no botão, e Escape fechou a Central.

O Wi-Fi terminou ligado, como estava, e o journal não registrou erro da dock.
Chave de hardware, política que nega a mudança e um computador sem Wi-Fi só foram
exercitados nos testes. **Abrir Rede no KDE** foi testado só pelo despacho.

Escolher e conectar redes, inclusive com senha pelo fluxo de autenticação do KDE,
fica para a próxima fatia.

## Redes Wi-Fi — CC2-D

Como no macOS, clicar no nome **Wi-Fi** abre a página de redes dentro da
própria Central. A página tem:

- o botão de voltar e o interruptor do rádio;
- as redes ao alcance: a conectada primeiro, depois as salvas e as demais por
  intensidade do sinal, até 12, com ícone de sinal e cadeado nas protegidas;
- **Ajustes de Rede…**, que abre a página do KDE.

Cada abertura da Central volta aos módulos. A página só pede uma nova busca de
redes (`requestScan`); abrir a lista não conecta nem desconecta nada.

Escolher uma rede pede a conexão ao NetworkManager pelo `plasma-nm`:

- uma rede salva é reativada (`activateConnection`);
- uma rede nova é adicionada (`addAndActivateConnection`). Se ela tiver senha,
  quem pergunta é o agente de segredos do próprio KDE: o Orla nunca vê nem
  guarda senhas.

A conexão só aparece como feita quando o NetworkManager relata a rede
conectada. A comparação é pelo nome, porque a rede nova muda de identificador
ao ser salva. Durante a espera, o card mostra "Conectando a…" e outra escolha é
ignorada.

Há três formas de falha, e nenhuma parece sucesso:

- recusa imediata;
- falha relatada pelo NetworkManager, cuja mensagem aparece como texto simples
  e limitado;
- falta de resposta em 45 s. Nesse caso o aviso lembra de concluir a senha no
  diálogo do KDE.

O botão de ejetar na rede conectada desconecta (`deactivateConnection`), também
com espera pela confirmação. Redes ocultas, sem nome, ficam para as
configurações do KDE.

Prova: os testes cobrem lista, ordem, foco, conectar, desconectar e falhas,
com fixtures sintéticas. Uma leitura nativa offscreen, só de leitura, conferiu
o adaptador contra o `plasma-nm` real (rede conectada, protegida, salva) sem
registrar nomes. Conectar e desconectar não foram executados na sessão real,
para não derrubar a conexão em uso.

Capturas sintéticas: [escuro](screenshots/control-center-wifi-networks/dark.png)
e [claro](screenshots/control-center-wifi-networks/light.png).

## Aparelhos Bluetooth — CC2-E

Clicar no nome **Bluetooth** abre a página de aparelhos, no mesmo padrão da de
Wi-Fi. Ela tem:

- o botão de voltar e o interruptor do rádio;
- os aparelhos **pareados** (até 12), conectados primeiro, com o ícone que o
  BlueZ informa e a bateria quando o aparelho a relata;
- **Ajustes de Bluetooth…**, onde continua o pareamento de aparelhos novos.

Escolher um aparelho chama `connectToDevice` do BluezQt; o botão de ejetar
chama `disconnectFromDevice`. O resultado só aparece quando o BlueZ relata o
aparelho conectado ou desconectado. Há três formas de falha, e nenhuma parece
sucesso:

- recusa imediata;
- erro devolvido pelo BlueZ, em texto simples e limitado. O erro de outro
  aparelho não encerra a espera;
- falta de resposta em 20 s.

O card mostra "Conectando …" durante a espera. As linhas da Wi-Fi e do
Bluetooth usam o mesmo componente, `ControlCenterListRow`.

Prova: testes com fixtures sintéticas cobrem lista, foco, conectar, falhas,
tempo esgotado e descarte de linhas inválidas. Uma leitura nativa só de leitura
(offscreen, BluezQt real) listou dois aparelhos pareados (mouse conectado com
bateria e teclado desconectado) sem registrar nomes. Conectar e desconectar não
foram executados na sessão real, para não desligar seus periféricos.

Capturas sintéticas: [escuro](screenshots/control-center-bluetooth-devices/dark.png)
e [claro](screenshots/control-center-bluetooth-devices/light.png).

## Bluetooth — CC2-C

O card **Bluetooth** liga e desliga o rádio Bluetooth do mesmo jeito que o applet
de Bluetooth do Plasma: pelo BluezQt, retirando ou aplicando o bloqueio de rádio
(`rfkill`) e ligando ou desligando cada adaptador. Ele mostra o aparelho conectado,
quantos estão conectados ou “Ligado · nenhum dispositivo conectado”. Com o rádio
desligado, nenhum aparelho aparece. **Abrir Bluetooth no KDE** abre as
configurações de Bluetooth do sistema.

A troca só conclui quando o BlueZ informa o novo estado. As escritas só pedem a
mudança ao BlueZ e ao `rfkill`; os valores mudam quando os serviços avisam. Como
religar retira o bloqueio antes de ligar o adaptador, a confirmação espera até 5
segundos. Uma recusa ou a falta de confirmação mostram erro. Sem o serviço BlueZ
ou sem adaptador, só este card fica desativado. O botão continua focável durante a
confirmação, e a leitura só acontece com a Central aberta.

Na sessão Plasma 6.7.5 deste registro, sem nenhum aparelho conectado, o card
mostrou “Ligado · nenhum dispositivo conectado”:

- um clique desligou: o `bluetoothctl` respondeu `Powered: no`, e o `rfkill` mostrou
  bloqueio por software, como faz o applet do Plasma;
- Espaço religou em menos de meio segundo, sem bloqueio e com o adaptador ligado;
- desligar e religar pelo `bluetoothctl` apareceu no card;
- o contorno de foco ficou visível com Tab, e Escape fechou a Central.

O Bluetooth terminou ligado e sem bloqueio, como estava, e o journal não registrou
erro da dock. Aparelhos conectados, falta de adaptador e serviço parado só foram
exercitados nos testes. **Abrir Bluetooth no KDE** foi testado só pelo despacho.
Conectar e desconectar aparelhos fica para uma fatia seguinte.
