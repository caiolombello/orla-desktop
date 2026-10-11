# Central de Controle (Source experimental)

Os assets publicados da alpha 0.2.9 continuam imutáveis: eles entregam a fatia
CC0 de estado e atalhos, sem controles diretos. O Source atual acrescenta a
primeira fatia CC1-A experimental para áudio. Essa mudança ainda não integra
uma nova release.

Ative **Mostrar Central de Controle no dock (global)** em **Widgets** para
exibir o botão opcional. A preferência herdada de CC0 é global, começa
desligada, é salva imediatamente e permanece fora dos perfis.

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

Os títulos, valores, detalhes e erros livres usam as cores `foreground` e
`muted` da aparência do Orla. Controles como botões e o seletor de saída mantêm
a paleta interna do estilo Qt/KDE, evitando texto escuro herdado sobre o fundo
escuro do card sem recolorir os controles nativos.

CC1 continua parcial. Microfone, brilho, Não perturbe e os gates reais do
serviço de áudio ainda estão abertos; rede, Bluetooth e energia pertencem às
fatias seguintes. Instalação, módulo privado do Plasma-PA, Pulse/PipeWire,
barramento da sessão, compositor, seat, hardware, popup nativo e painel
instalado permanecem sem validação.

Veja a [validação Source de áudio](validation/control-center-audio-source.md) e
o [registro da alpha 0.2.9](validation/control-center-peripherals-0.2.9.md).
