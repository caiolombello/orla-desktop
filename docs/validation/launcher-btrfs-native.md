# Recuperação do launcher e busca nativa em Btrfs

Validação delimitada de 21/10/2026 na sessão KDE/Wayland local. As ferramentas
publicadas em `e515e4cf109fac843643cafb14256dd056fb2b31` usam o gerenciador
`8eedf4540fc95afbbf9f9ebdc49e28e1401486cc50fca422dc915fb3a265a71e`.
O ELF testado é o artefato anterior verificado, declarado como `4e76beab…`,
arquivo `cb6ea663…`, ELF `4994fe1b…`. Essa proveniência separa ferramentas e
payload; não afirma execução de um novo binário da CI.

## Instalação e serviço

A instalação anterior recusava a partida com `managed_parent_drift`. Os arquivos
conferiam; os seis diretórios mantinham inode, modo e proprietário, com mudança
apenas do dispositivo persistido. A recuperação explícita do operador preservou
a geração anterior e todos os seus recibos. Não houve adoção ou normalização de
pins históricos pelo instalador comum.

O ciclo de arquivos do gerenciador final passou primeiro em diretório privado:
instalar, consultar pelo controlador instalado sem o bootstrap e remover. Foram
conferidas seis provas de identidade Btrfs, igualdade do histórico e configuração sintética.
Na instalação principal, diretório de estado e o mesmo inode do lock permaneceram
no lugar. O recibo novo é `orla-launcher-install-0.2`.

A troca posterior encerrou somente o processo de recuperação identificado e
ativou o serviço normal pela API comum. O verificador confirmou geração exata,
unit e vínculo de autostart próprios, processo executando o ELF instalado e
propriedade do nome D-Bus. O serviço temporário terminou inativo. Uma preparação
anterior falhou ao procurar um relatório com nome incorreto, antes da criação do
gate e de qualquer troca de serviço; seu resultado foi preservado separadamente.

## Tecla Windows/Meta

Na geração instalada, um dispositivo virtual temporário emitiu Meta, digitou
`dolphin`, enviou Escape e reabriu/fechou a busca. A observação KWin restringiu
os dados à janela do PID próprio, sem capturar títulos de outros aplicativos.
Meta abriu a janela ativa; Escape a retirou do foco e a reabertura funcionou.
O mesmo teste passou após um restart comum somente do serviço do launcher.

Os dois ensaios preservaram byte a byte `kwinrc`, `kglobalshortcutsrc` e o novo
recibo. Os dispositivos virtuais foram fechados, sem ler dispositivos físicos.
O launcher principal terminou oculto e ativo em seu serviço normal. Esse ensaio
verifica atividade/foco da janela; não mede latência nem restauração de foco
para um aplicativo externo.

## Resultado real de aplicativo

Uma instância adicional do mesmo ELF foi aberta com `--no-global-shortcut`, HOME
e diretórios XDG privados, mantendo os aplicativos de sistema reais. Somente esse
processo recebeu a opção de acessibilidade documentada pelo
[Qt 6.11](https://doc.qt.io/qt-6.11/qaccessible.html), sem configurar propriedades
globais de leitor de tela pelo ensaio.

Após conferir foco no PID próprio, a entrada virtual digitou `dolphin`. A árvore
AT-SPI desse processo confirmou o texto exato no campo e o resultado Dolphin.
Foram visitados 41 nós próprios, sem guardar a lista de aplicativos. Escape
encerrou a instância normalmente, código zero e saídas vazias. O PID do serviço
principal e seus arquivos de atalhos permaneceram iguais. Nenhum resultado foi
executado. Um coletor anterior não obtivera a árvore da instância gerenciada;
essa falha continua registrada e não foi reinterpretada como sucesso.

## Evidência e limites

Os registros privados ficam em `.runtime/meta-search-repair-20261020/`:

- `root-private-install-r2/RESULT.json`: ciclo real de arquivos do gerenciador final.
- `root-retirement-execution-r1/RESULT.json`: instalação inerte, preservação e recuperação ativa.
- `root-handover-execution-r2/RESULT.json`: troca para proprietário novo saudável.
- `root-installed-meta-r1/` e `root-installed-meta-r2/`: Meta antes/depois do restart.
- `root-service-restart-r1/RESULT.json`: novo processo/invocação, mesmos recibo e atalhos.
- `root-native-search-result-r2/RESULT.json`: consulta e resultado real na instância isolada.
- `root-final-verification-r1/RESULT.json`: serviço/autostart e preservação da geração anterior.

Não foram testados reboot/login real, execução de um resultado, restauração de
foco para aplicativos externos, outras distribuições/ABIs, updates após mudança
de dispositivo ou recuperação transacional entre boots. O teste não qualifica
Workspace, addons ou o roadmap inteiro. A geração antiga preservada não é um
mecanismo público de migração ou rollback automático.
