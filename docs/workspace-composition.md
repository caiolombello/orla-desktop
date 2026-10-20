# Composição opcional do desktop

[Validação e capturas](validation/workspace-composition.md) registram o escopo
verificado e os gates nativos/distribuição ainda abertos.

## Resultado e limites desta fatia

Uma janela optativa permite escolher monitor e painéis, revisar a composição e
usar o gerenciador transacional existente para aplicar, desativar ou restaurar a
barra. A dock continua independente. A janela roda em processo separado para
acompanhar as recargas do Plasma; a qualificação nativa desse ciclo segue aberta.
Só a confirmação explícita despacha uma operação; leitura, revisão e abandono do
plano não escrevem configurações, bancos ou recibos.

Primeira entrada: `python3 scripts/orla.py layout setup --service UNIT`, no checkout
completo, com PySide6 e os widgets necessários já instalados. Não há botão no
plasmoid apontando para um caminho do desenvolvedor. O pacote público atual não
é um kit autônomo deste companion; distribuição e instalação continuam abertas.

O pré-requisito Menu Orla segue a [instalação manual da barra](../bar/README.md).
Também são necessários Menu Global, espaçador, bandeja, áudio/rede e relógio do
Plasma. A janela não instala widgets. `UNIT` é o nome literal do serviço Plasma
do usuário atual, verificado pelo helper; não há escolha automática de serviço.
Os comandos `layout status --service UNIT` e `layout setup --help` podem ser
consultados antes de abrir a janela.

O backend exige Plasma 6.7.5 e pelo menos um painel existente, escolhido pelo
usuário, para substituição. Painéis com a dock são recusados. Não há criação
aditiva nem reativação direta após desativar: restaurar o original e revisar uma
nova composição são operações distintas. Os widgets novos usam os defaults do
preset; nenhuma bandeja é reaproveitada silenciosamente.

## Interface e contrato

Herdar a identidade costeira, os tokens canônicos, Card, OrlaButton e controles
nativos. Uma coluna rolável, cabeçalho conciso, revisão com IDs e módulos reais,
ações sempre alcançáveis a 350/420 px e viewport curto. Claro/escuro seguem o
sistema. Texto PT-BR simples; foco visível, nenhuma animação decorativa.

`CompositionSession` mantém um único plano em memória, descarta revisões antigas
e consome uma confirmação antes do despacho. Confere identidade, journal e
bytes/modos da configuração revisada antes da transação; o backend continua a
validar inventário, propriedade e recuperação. Status não promete restaurabilidade.

O host Qt possui uma operação por vez, numa thread, sem acesso concorrente ao
session. Fechar/SIGINT/SIGTERM bloqueiam novos trabalhos e aguardam a conclusão;
não significam cancelamento ou rollback. Erros visíveis não expõem exceções ou
dados pessoais. Falha exige nova leitura; recuperação só ocorre após revisão.
Fase registrada e observação ao vivo são distintas: falha na leitura final ou
Plasma parado não anunciam barra ativa nem habilitam ações normais. A recuperação
de uma transação interrompida continua sujeita ao backend, inclusive com shell parado.

O host usa `QThread.run` para o trabalho síncrono e aguarda o término antes de
publicar disponibilidade, seguindo o [contrato do Qt](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html).
O [evento de fechamento](https://doc.qt.io/qt-6/qml-qtquick-window.html#closing-signal)
da janela permanece recusado enquanto houver uma operação.

## Sequência e verificação

1. Provar seleção/revisão/abandono sem mutação e confirmação vinculada ao plano.
2. Consumir apply → disable → restore → novo plano com FileStore real e runtime
   sintético, incluindo drift e falhas sem retry automático.
3. Provar ownership/fechamento do host, interações Qt, foco e galeria claro/escuro
   em Fusion/KDE. Offscreen não prova seat nem comportamento nativo do painel.
4. Qualificar o fluxo no ambiente isolado e, separadamente, distribuição sem
   Source e elegibilidade de atualização local; não relaxar hashes de recibos.

Recomendação de execução: Sol 6.1, medium; backend existente limita a implementação. Escalar
raciocínio se uma transição não puder preservar os bancos e o primeiro erro.
Implementação inicial executada com evidência sintética; criação aditiva, reativação direta,
distribuição autônoma e aceite nativo permanecem incrementos posteriores.
