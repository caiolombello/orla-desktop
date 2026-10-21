# Núcleo experimental de complementos — validação

Registro de 21/10/2026. O escopo é o host de dados e seu instalador,
correspondentes aos bytes incorporados até `5b840f7`. O formato continua
`0.1-experimental`. Este registro não encerra a entrega da interface ou do
ecossistema de plugins.

## Source e testes privados

- Parser, armazenamento e CLI: 33 testes do projeto e 12 probes independentes
  passaram. A revisão independente não encontrou bloqueadores nesse escopo.
- Serviço e worker: 24 testes do projeto e nove probes independentes passaram,
  com barramento simulado e processos confiáveis do próprio host.
- As quatro suites do núcleo incorporado passaram juntas: 57 testes.
- Instalador: 61 testes do projeto e 12 probes independentes passaram. Os
  61 testes também passaram após a incorporação no checkout principal.
- O pacote `.plasmoid` foi construído e seus cinco módulos Python do host
  conferidos por hash. Não contém manifesto de complemento de produtor.

Os testes verificam aprovação dos bytes exatos, consentimento separado,
atualização/rollback desativados, recusa de estado corrompido, campos e arquivos
limitados, falhas antes/depois da publicação, geração, saída privada, prazo,
encerramento do worker e rejeição de callbacks antigos. Eles não demonstram
recuperação após queda de energia nem isolamento contra outro processo malicioso
do mesmo usuário.

## D-Bus real, isolado

Em Fedora 44, Python 3.14.8 e PySide6/Qt 6.11.2, foi criado um barramento privado
com HOME e diretórios XDG temporários. Nenhuma chamada usou o barramento da
sessão do desktop ou um coletor real.

A introspecção mostrou somente os oito métodos previstos na interface
`org.orla.Addons1`: ListAddons, InspectAddonFile, InstallAddon, EnableAddon,
DisableAddon, RemoveAddon, RollbackAddon e SnapshotFor. Argumentos e retorno
string corresponderam ao contrato; o QDBusMessage de contexto não apareceu
como argumento público. Não apareceu interface adicional de métodos internos.

Quatorze chamadas reais cobriram listagem, inspeção, instalação desativada,
ativação explícita, leitura sintética de 0%, desativação, atualização, rollback,
remoção, seleção vazia e recusa de seleção inválida. Uma alteração no código
instalado temporário encerrou o processo antigo, que foi recolhido.

A primeira execução recusou corretamente uma pasta sintética de produtor
criada por engano com modo 0755. O diagnóstico identificou `export_invalid` /
`unsafe`. Uma execução nova com a pasta 0700 passou sem alteração no serviço;
a falha original foi preservada como falha de preparação da fixture.

## Transporte QML real, isolado

Uma execução separada usou Plasma Workspace 6.7.5, PySide6/Qt 6.11.2,
o candidato `AddonTransport.qml` e o mesmo núcleo, em outro barramento privado.
Treze chamadas cobriram os oito métodos, com as assinaturas `()`, `(s)`,
`(ss)` e `(as)`. O teste verificou a resposta string real, sua representação
no tipo QML e a extração por `ThemeFile.replyText`, incluindo seleção vazia,
instalação desativada, leitura sintética de 0%, atualização, rollback e remoção.
A recusa de seleção inválida retornou o envelope previsto; um serviço ausente
acionou o callback de erro. Não houve avisos QML; o serviço foi recolhido.

As duas falhas anteriores de preparação — cópia incompleta do serviço e pasta
sintética com permissão 0755 — foram preservadas. A execução corrigida mudou
somente a preparação privada, sem alterações no código do produto.

O transporte é candidato de uma camada posterior. Esta verificação não cobre
seu gerenciador de estado, seletor de arquivos, coordenação com Settings,
interface instalada ou compatibilidade com Qt 6.12.

## Instalação e ativação sob demanda reais

O pacote foi instalado com `kpackagetool6` em XDG temporário cujo caminho
continha espaços. A instalação registrou o host sem iniciá-lo e sem registrar
a ponte legada opcional. A primeira ListAddons ativou o serviço.

O argv do processo ativado confirmou o interpretador esperado, `-I -B`, o
caminho instalado completo e `--serve`. Assim, o teste verificou a interpretação
real de Exec e a propagação do ambiente de ativação, além da representação
textual do comando.

Uma atualização real preservou os bytes e mtime do registro de ativação,
substituiu o Source instalado e encerrou seu processo antigo. A chamada
seguinte ativou outro processo e retornou o mesmo catálogo privado. A remoção
real apagou o pacote e o registro próprio; preservou integralmente o registro
de complementos e as preferências sintéticas.

## Limites da validação original do núcleo

Não houve instalação na sessão de uso, interação com o seletor de arquivos,
validação de foco Plasma/Wayland, coleta de hardware, execução do PeriGauge,
acesso a contas, teste de login/reboot ou publicação de release. A composição
da interface, a coordenação de seus pedidos concorrentes, a validação do
produtor e a instalação local completa são etapas separadas.

Os limites experimentais de retenção e recuperação estão no
[guia de extensões](../EXTENSIONS.md).


## Cliente e coordenação — prova privada de 21/10

A camada de interface acrescenta gerenciamento de complementos em
Configurações → Widgets: escolher arquivo, conferir metadados, instalar,
ativar leitura, desativar, remover com confirmação e voltar à versão anterior.
Instalação, atualização e rollback mantêm a leitura desativada. Não há pacote
de produtor distribuído por padrão, código comunitário executável ou catálogo.

Uma prova separada usou o transporte KDE real, o serviço real, o gerenciador
QML, o coordenador e o adaptador de dados de produção, em D-Bus privado,
com manifesto e exportação sintéticos. Treze chamadas diretas cobriram os
oito métodos tipados; outras 16 chamadas passaram pelo fluxo coordenado.
As seis mutações do gerenciador foram confirmadas. A abertura aguardou a
leitura fisicamente pendente antes de listar metadados, retomou uma leitura
válida de 0% após fechar e limpou os dados ao desativar/remover. Não houve
avisos QML; o serviço foi recolhido e os 545 arquivos de entrada permaneceram
iguais. Isso não usou o barramento da sessão de uso nem hardware.

Essa composição exigiu normalizar a string encapsulada na resposta nativa do
Qt, proteger notificações anteriores à conclusão do componente e cancelar
callbacks da apresentação antes de acessar objetos já destruídos. Os
resultados anteriores com falha foram preservados. Cancelar/Recarregar
reservam espaço para o contorno de foco completo no viewport real, em vez
de alterar fontes, alvos ou o orçamento do popup.

O encerramento do coordenador também tem regressões próprias: resultados
atrasados e duplicados são ignorados após sua destruição, inclusive quando
um observador o retira durante a publicação. A instância substituta continua
operante, mantém seu foco e aceita uma nova leitura válida. Essas provas
usam objetos Qt reais e transporte simulado; o teste de interoperabilidade
privada acima cobre a instância viva, sem promover esse caso de destruição
a uma prova de fechamento nativo do Plasma.

O bloco portátil proposto do CI passou localmente em Qt/PySide 6.12.0 e
Python 3.14.8: 129 testes do núcleo, 38 do cliente e 117 de apresentação,
coordenação portátil e dados, sem falhas ou skips. Os nove testes do painel
real exigem os módulos KDE e ficam na validação local com Qt 6.11.2;
não são omitidos por um novo skip. O resultado local não é CI hospedado.

Capturas sintéticas do componente pai, com dados fictícios e renderização
offscreen, mostram os contornos de foco nas duas paletas:

![Recarregar complementos no esquema escuro](../screenshots/addon-manager/addons-dark-reload.png)
![Cancelar espera no esquema claro e viewport curto](../screenshots/addon-manager/addons-light-wait.png)

## PeriGauge — ciclo UPower privado de 21/10

O executável revisado do produtor completou um único ciclo real privado,
com UPower: coleta e cache, consentimento separado, publicação da projeção,
leitura exata pelo host, reutilização sem renovar a validade, expiração real
de 30 segundos e desativação com remoção da exportação. O estado inicial e
final permaneceu desativado. O host privado também confirmou ausência de
leitura para pacote não instalado, desativado ou oculto pelo perfil, e
completou desativação/remoção. Os 19 processos próprios foram recolhidos.

A configuração e o serviço instalados do produtor não foram alterados.
As leituras privadas foram retidas somente para diagnóstico local; nenhum
nome ou identificador de hardware integra este registro ou as capturas.
Esse ciclo não qualifica HID, Buds, notificações, saúde do hardware, operação
oculta da interface, uso contínuo, atualização do produtor instalado ou a
interface Orla na sessão de uso. Esses gates continuam separados.

O seletor/modalidade, foco e acessibilidade nativos, troca de perfis em uso,
escala/monitores, reinício/login e atualização completa ainda precisam das
suas provas na instalação. X4, I1 e DX4 permanecem parciais; o formato
continua experimental.


## Instalação local — 21/10

O runtime de `948b4fa` foi instalado na sessão de uso com backup do pacote
anterior. Os 91 arquivos instalados coincidiram com o pacote verificado
(`6b93b96c0606169622605484eb5f9ed5e8ec213683b8e3de9fc34cb8322d7c67`).
Os registros de ativação lazy de temas e addons corresponderam ao instalador;
o registro legado permaneceu igual. O catálogo de complementos ainda não
existia no armazenamento, sem pacote de produtor instalado ou ativado por esta
atualização.

O Plasma foi recarregado uma vez e voltou ativo. O registro desse período não
mostrou erro de carregamento QML, erro de lifetime do coordenador ou saída por
crash. A dock renderizou ao ser mostrada temporariamente, e o auto hide original
foi restaurado no mesmo painel/applet. Isso não qualifica revelar pela borda:
a rota absoluta do dispositivo virtual de teste não foi estabelecida.

A entrada virtual foi encerrada diante de atividade simultânea na sessão,
preservando o foco mais recente. Seletor, modalidade, popups e teclado na
instalação continuam sem qualificação desta rodada. Não houve atualização do
PeriGauge instalado, ativação de exportação, migração de recibos de layout,
reinício do KWin ou reboot. O pacote anterior também foi reconstruído e
conferido para reversão; essa reversão não foi executada.
