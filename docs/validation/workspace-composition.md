# Composição opcional — validação de código e interface

20/10/2026. PySide6/Qt 6.11.2, renderização offscreen/software. Este registro
qualifica a janela e a ligação ao gerenciador existente com runtime sintético.
O incremento do bundle abaixo qualifica também a carga sem checkout. Não qualifica
o comportamento nativo de Plasma/Wayland. A instalação gerenciada privada tem
um incremento separado ao final, ainda em revisão independente.

## Comportamento verificado

- Ler, selecionar, revisar e abandonar não alteram configuração, bancos ou journal.
- Uma confirmação consome um plano em memória; dupla confirmação, plano antigo e
  drift de bytes/modos, inventário, recibo, serviço e raízes são recusados.
- O host Qt executa apply → disable → restore nas funções reais, usando FileStore
  e arquivos privados com FakeRuntime; recupera os bytes originais e despacha uma
  aplicação e uma remoção. Há cobertura adicional de schema2 e falha/recuperação.
- Fechamento pendente bloqueia novos trabalhos até join. Falhas não expõem caminhos
  ou identificadores privados. Erros de compatibilidade e widgets têm orientação.
- Inserção, reordenação e remoção de monitores mantêm seleção visual e alvo iguais.
- Em 350×240, o conteúdo continua rolável e o controle com foco é revelado após
  layout/redimensionamento. O teste preserva a falha histórica encontrada em KDE.
- Uma transação registrada com leitura final indisponível, ou Plasma parado,
  não anuncia barra ativa nem oferece ações normais; releitura não repete execute.

## Verificações

```sh
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_QUICK_CONTROLS_STYLE=Fusion \
  python3 -B -m unittest discover -s tests -p 'test_workspace*.py'
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software QT_QUICK_CONTROLS_STYLE=org.kde.desktop \
  python3 -B -m unittest discover -s tests -p 'test_workspace*.py'
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
  python3 -B -m unittest discover -s tests -p 'test_panel_layout*.py'
PYTHONPATH=tests QT_QPA_PLATFORM=offscreen \
  python3 -B -m unittest test_package_cli test_release test_design_system
python3 scripts/design.py check
```

Resultados: 31 testes de composição em cada estilo; 177 do backend; 50 de CLI,
bundle e design. Todos passaram. Design check: zero problemas. O build do plasmoid
continua com o mesmo SHA256 do pacote anterior; nenhum payload novo foi instalado.

A galeria usa `Gallery.workspace` do gerador existente: 36 capturas, nove por
combinação de estilo/esquema, sem warnings QML. As capturas finais foram vistas;
foco, legibilidade e geometria foram também medidos pelos testes. Foram corrigidos
viewport colapsado, foco invisível após resize, alvo de monitor divergente e rótulo
cortado. A revisão independente final não encontrou bloqueadores neste escopo.

## Capturas sintéticas

![Seleção escura](../screenshots/workspace-composition/workspace-dark-selection-350.png)
![Revisão clara](../screenshots/workspace-composition/workspace-light-review-420.png)
![Foco em janela baixa](../screenshots/workspace-composition/workspace-dark-committed-short-focus.png)
![Leitura final indisponível](../screenshots/workspace-composition/workspace-light-unverified.png)

## Ainda aberto

Não foram executados NativeRuntime, IPC real, recarga de plasmashell ou ciclo
completo desta janela na sessão do usuário. Os gates próprios anteriores de
SIGINT/SIGTERM/Window.close exercitaram o controller com uma Session bloqueada e
loop Qt real em filhos privados; não provam o ciclo nativo. Entrada instalada no
desktop na sessão do usuário, criação aditiva e reativação direta permanecem no
[roadmap](../../ROADMAP.md). Reativação atual exige restore → novo plano/apply.

## Incremento de distribuição: ZIP relocável

O bundle separado fecha a árvore de imports da janela: 16 arquivos regulares 0644
e manifesto. A verificação cobre determinismo, hashes/commit externos, schema,
entradas duplicadas/extras/ausentes, modos, symlinks e limites de expansão. Os
testes usam fixtures sintéticas para adulterações e o payload real para integração.

O payload real foi extraído de bytes verificados, movido para um caminho com
espaços/Unicode e aberto de outro diretório. `--version` e `--diagnose` passaram;
a árvore permaneceu idêntica, sem bytecode novo. Um teste Bubblewrap ocultou o
repositório e removeu a rede: o diagnóstico carregou a interface real sem fallback
para Source. Esse teste é explicitamente pulado quando Bubblewrap está ausente.

Pacotes instalados com os nomes `workspace` e `scripts` não substituem os imports
locais do bundle; o teste preserva a colisão encontrada na inspeção final.
Um Python privado sem Qt ainda consulta versão e informa `qt_runtime_missing`.
Versão Qt incompatível impede iniciar o host; erros de inicialização são
sanitizados. O diagnóstico usa XDG privado, barramentos ausentes e controller
inerte: não instancia NativeRuntime nem testa a sessão Plasma. As configurações
XDG do chamador foram preservadas. A resolução de estado relativo também passou
com os defaults do usuário, antes de construir a interface.

Verificação do incremento pelos comandos acima: 60 testes de composição em
Fusion e 60 em KDE; 177 do backend; 50 de CLI/release/design; design check sem
problemas. Os processos das suítes Qt registraram um `ResourceWarning` de sete
objetos Python não coletáveis ao terminar; não houve falha de teste. Nenhum QML
foi alterado neste incremento; a galeria anterior continua sendo a referência visual.
A revisão independente final não encontrou bloqueadores: 96 testes focados
passaram, além de cinco variantes de colisão com pacotes instalados. Remover
qualquer um dos dois marcadores de pacote em cópias privadas reproduziu a falha;
no bundle final, todos os helpers inspecionados vieram da árvore local. Esse
resultado substitui o aceite inicial, que não havia detectado a colisão.

Não foram instalados bundle, atalho ou serviço na sessão do usuário. O ZIP não
inclui Qt ou widgets; hashes do manifesto não autenticam o autor. O instalador
com ownership, seletor de geração, update/rollback e barreira de fechamento
é tratado no incremento abaixo, separado do ciclo nativo completo.

## Incremento de distribuição: instalação própria

O gerenciador experimental oferece install/status/doctor/launch/update/rollback/
recover/uninstall, ferramentas locais fixadas, wrappers e entrada no menu. A
implementação passou em 59 testes focados de instalação, pacote e entrada. Os
casos incluem colisões e drift, checkpoints de recuperação, histórico imutável,
update com uma geração anterior, quoting de caminhos e sinais/lease com filhos
sintéticos. A revisão independente encontrou uma falha reproduzida em escrita
parcial de registros imutáveis. A correção publica somente registros completos
e sincronizados, sem substituir histórico existente; falhas parciais de recibo,
intent e conclusão passaram em recuperação/retry ou replay conforme a fase.
Os 69 testes focados passaram após a correção. Root executou também a descoberta
completa `test_workspace*.py`: 100 testes em Fusion passaram, sem falhas ou skips,
com XDG privado e barramentos ausentes. A nova revisão independente aprovou o
contrato delimitado, sem achados restantes: repetiu os 69 testes focados e
acrescentou três testes com dez cenários de falha, além da prova instalada sem
Source/Qt. Registros finais realmente corrompidos continuam sendo recusados.

Root instalou o ZIP real do commit `5b0ab82b023ad1d2ef4b12c2bc63f288454c29ea`
em diretórios privados dentro de Bubblewrap, com Source oculto, rede ausente e
barramentos ausentes. Após remover bootstrap e ZIP, os comandos instalados
status, doctor, recover sem pendência e uninstall passaram. Doctor carregou a
interface real offscreen em Qt/PySide6 6.11.2; informou runtime ready,
serviceContacted=false e nativeValidated=false. Configuração, bancos e auditoria
sintéticos preservaram conteúdo, modo e identidade. Esse fluxo foi repetido com
as ferramentas corrigidas e passou novamente. O teste de release passou
com a nova suíte excluída do arquivo específico do plasmoid.

Duas tentativas anteriores do harness foram preservadas: a primeira recusou um
ancestral com UID remapeado pelo namespace; a segunda não criou um mountpoint
sobre a raiz somente leitura. A execução final usou um bind privado sobre um
mountpoint existente, sem relaxar verificações do instalador ou mudar o produto.

Não há promessa de recuperar toda instrução interrompida: criação anterior ao
checkpoint de identidade recusa adoção, e remoção parcial das ferramentas exige
o par confiável original. Não foram testados falta de energia, filesystem remoto
ou execução em Python mínimo. Não houve instalação na sessão do usuário, recarga
de Plasma ou validação do fechamento real da janela instalada.

O driver/provision passou em revisão independente com 28 testes privados. O
supervisor foi corrigido e aprovado após 69 testes simulados: exige EOF, valida
registros a cada leitura e preserva a primeira falha diante de problemas posteriores
de transporte, log e limpeza. Os 101 arquivos de Source e os 110 arquivos do ISO
foram reconferidos; imagem Fedora e checksum assinado também passaram antes do boot.

O primeiro boot de preparação da VM foi executado. O provisionamento falhou com
status 153 após a conferência do payload, e o supervisor preservou a falha e encerrou
seu próprio processo QEMU. A tentativa levou 15,551 s; a imagem resultante e os logs
foram mantidos, sem retry ou reparo dessa tentativa. A causa ainda depende do log
interno de provisionamento. Não foram executados NativeRuntime nem a interface de
composição dentro da VM. Não há aceite nativo ou preparação bem-sucedida.

A CI do PR do instalador revelou uma condição da fixture de colisão: o Qt estava
somente no venv que executava os testes e não era herdado pelo venv aninhado. A
fixture passou a fornecer explicitamente os caminhos do runtime ativo. Uma regressão
reproduziu a falha antes da correção; os nove testes de entrada passaram depois,
assim como a revisão independente e os dois controles de colisão por remoção de
marcadores. O código de produção e as exigências de diagnóstico não foram alterados.
O resultado da nova CI permanece separado desses testes locais.
