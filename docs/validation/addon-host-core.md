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

## Limites da evidência

Não houve instalação na sessão de uso, interação com o seletor de arquivos,
validação de foco Plasma/Wayland, coleta de hardware, execução do PeriGauge,
acesso a contas, teste de login/reboot ou publicação de release. A composição
da interface, a coordenação de seus pedidos concorrentes, a validação do
produtor e a instalação local completa são etapas separadas.

Os limites experimentais de retenção e recuperação estão no
[guia de extensões](../EXTENSIONS.md).
