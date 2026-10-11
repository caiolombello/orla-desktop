# Central de Controle — áudio CC1-A no Source

**Estado:** o comportamento de áudio round 4 foi aprovado por revisão
independente para Source e mocks. O freeze atual acrescenta uma correção visual
Source/mock, ainda sem admissão nativa, de serviço ou hardware e sem integrar
uma release. Os assets públicos da alpha 0.2.9 permanecem CC0, sem controles
diretos.

## Contrato verificado

O card experimental trabalha com volume normalizado de 0% a 100%, mudo
explícito e escolha da saída padrão. No contrato do Orla, abrir o popup não
envia um ajuste. Escritas ocorrem exclusivamente por `Slider.moved`, botão de
mudo ou ativação explícita do seletor; mover o volume não altera o mudo e a
fatia não move streams de aplicativos.

Cada operação guarda o ID da saída alvo e aguarda readback. Tipos diferentes de
operação são serializados, enquanto movimentos sucessivos do mesmo drag podem
substituir o volume desejado para o mesmo alvo. Um snapshot que coincide com o
valor pedido prova apenas convergência observada: o backend não fornece um ID
de operação que permita atribuir causalidade à resposta.

Falha de despacho, timeout, remoção e mudança externa têm apresentação local
explícita. Se uma tentativa posterior do mesmo drag falha, o pedido anterior
continua supervisionado e a interface volta ao último valor aceito. Se a saída
padrão muda de A para B durante um pending de A, B e seu volume confirmado são
mostrados sem redirecionar qualquer write; readback ou timeout de A termina sua
supervisão separadamente. Perda de writability também volta à apresentação
confirmada. Remoção do alvo encerra o pending com erro de saída ausente.

Backend ausente afeta somente o card de áudio. O atalho para o KCM de Som
continua sendo um fallback acionado pelo usuário e seu retorno significa apenas
dispatch, não abertura confirmada ou alteração aplicada.

## Evidência Source/mock

Os dez caminhos do freeze Source/mock atual são:

```text
package/contents/ui/AudioControlState.qml
package/contents/ui/NativePulseAudio.qml
package/contents/ui/DockView.qml
package/contents/ui/ControlCenter.qml
tests/AudioControlHarness.qml
tests/test_audio_control.py
tests/ControlCenterHarness.qml
tests/QmlHarness.qml
tests/test_qml.py
tests/test_control_center.py
```

A verificação do autor registrou **24 testes PASS** com Fusion e **11 PASS** com
o estilo KDE Desktop, ambos offscreen e com renderização software. O caso novo
substitui `foreground` e `muted` por `QQmlProperty.write`: títulos, percentual,
estado e erros seguem as cores do Orla sobre fundo escuro, enquanto botões e
ComboBox preservam `palette.buttonText`. A revisão independente round 4 já
aprovou os gestos de mudança de alvo, rejeição de supersessão e rollback, além
de executar um subconjunto próprio de quatro testes de rollback, todos PASS.

Em um ambiente portátil com Qt 6.12.0, `tests.test_audio_control` registrou
**11 PASS em 0,858 s**. O núcleo de estado pode ser reproduzido sem carregar a
UI KDE:

```bash
env -u WAYLAND_DISPLAY \
  PYTHONPATH=tests \
  QT_QPA_PLATFORM=offscreen \
  QT_QUICK_BACKEND=software \
  QT_QUICK_CONTROLS_STYLE=Fusion \
  python3 -B -m unittest tests.test_audio_control
```

A cobertura portátil adicionada à CI para esta fatia é deliberadamente
limitada a esse módulo de estado de áudio; ela não transforma os testes de UI
KDE ou os gates nativos abaixo em PASS.

Uma tentativa portátil combinada preservou esses 11 PASS e falhou nos quatro
testes de `test_control_center` porque o ambiente Qt 6.12.0 não continha o
módulo `org.kde.kirigami`. As quatro falhas ocorreram ao carregar o componente,
antes dos cenários de UI, e registram uma dependência ausente; não são PASS nem
evidência de regressão comportamental.

## Limite do adaptador nativo

`NativePulseAudio.qml` concentra o import privado do Plasma-PA. Ele deve ser
carregado de forma lazy somente enquanto o popup está aberto e não existe um
backend de teste. O singleton do módulo pode conectar ou ativar o serviço de
áudio, e esse serviço pode continuar em execução após destruir o `Loader`.
Portanto, importar ou instanciar o módulo não é uma inspeção passiva e não foi
usado como prova Source.

Continuam **UNRUN**: import e instanciação do módulo privado, PulseAudio,
`pipewire-pulse`, PipeWire, barramento do usuário, compositor, seat, hardware,
áudio audível, popups nativos, instalação e painel real. Também permanecem
abertos microfone, brilho, Não perturbe e os gates completos de serviço. CC1 é
parcial até essas fatias e provas serem concluídas.
