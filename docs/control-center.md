# Central de Controle (Source experimental)

Os assets publicados da alpha 0.2.9 continuam imutáveis: eles entregam a fatia
CC0 de estado e atalhos, sem controles diretos. O Source atual acrescenta a
primeira fatia CC1-A experimental para áudio. Essa mudança ainda não integra
uma nova release.

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

Além dos cards compartilhados de mídia MPRIS e bateria, o card de áudio do
Source atual permite:

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

CC1 continua parcial. Microfone e os gates reais do
serviço de áudio ainda estão abertos; rede, Bluetooth e energia pertencem às
fatias seguintes. Instalação, módulo privado do Plasma-PA, Pulse/PipeWire,
barramento da sessão, compositor, seat, hardware, popup nativo e painel
instalado permanecem sem validação.

Veja a [validação Source de áudio](validation/control-center-audio-source.md) e
o [registro da alpha 0.2.9](validation/control-center-peripherals-0.2.9.md).
