# Prontidão da busca após Windows/Meta

Baseline delimitado de 13/10/2026 sobre `8d0902b`, em Plasma 6.7.5/Wayland,
Qt 6.11.2, na sessão local. Esta medição complementa a prova de atribuição,
execução e recuperação descrita no [guia do launcher](../../launcher/README.md).
Não encerra L0/L2 ou UX0.

## Método

Uma cópia privada do fonte recebeu instrumentação observacional: entrada do
atalho, visibilidade, pedido/resposta de token, callback de atividade, foco do
campo, primeiro callback de frame e comprimento/igualdade da consulta sintética
`orlaprobe`. A ativação e o QML permaneceram iguais ao fonte publicado. Nenhuma
alteração de comportamento foi instalada.

A janela anterior era um campo próprio, em tela cheia, em processo separado.
O emissor usou dispositivos virtuais temporários, sem ler ou capturar dispositivos
físicos. Cada tentativa enviou Meta, esperou o intervalo indicado e digitou a
consulta; nenhum resultado foi executado. Foram 12 tentativas intercaladas no
primeiro processo e três em novos processos. A primeira tentativa do grupo era
a primeira apresentação da janela: o agrupamento correto é **11 reaberturas e
quatro primeiras apresentações**.

Os tempos usam o relógio monotônico do mesmo host e começam na conclusão da
emissão de soltura de Meta. Emissão não é entrega pelo compositor. O estado
pronto exige janela ativa e foco no campo, juntos. Os eventos do launcher foram
guardados em memória e gravados ao encerrar; o snapshot de controle foi amostrado a cada
50 ms, sem sincronização de disco. Todos os registros e imagens permaneceram
privados; este relatório contém apenas dados sintéticos e agregados.

## Todas as tentativas

Tempo até o callback `activeChanged` observar janela ativa com foco na busca:

| Tentativa | Apresentação | Intervalo solicitado | Tempo até atividade + foco | Consulta completa | Caracteres no campo anterior |
|---|---|---:|---:|---|---:|
| 1 | Primeira | 0 ms | 57,19 ms | Não | 4 |
| 2 | Reabertura | 100 ms | 19,17 ms | Sim | 0 |
| 3 | Reabertura | 50 ms | 9,08 ms | Sim | 0 |
| 4 | Reabertura | 500 ms | 21,68 ms | Sim | 0 |
| 5 | Reabertura | 50 ms | 15,18 ms | Sim | 0 |
| 6 | Reabertura | 0 ms | 23,50 ms | Não | 1 |
| 7 | Reabertura | 500 ms | 15,15 ms | Sim | 0 |
| 8 | Reabertura | 100 ms | 15,15 ms | Sim | 0 |
| 9 | Reabertura | 500 ms | 20,01 ms | Sim | 0 |
| 10 | Reabertura | 50 ms | 8,22 ms | Sim | 0 |
| 11 | Reabertura | 100 ms | 14,85 ms | Sim | 0 |
| 12 | Reabertura | 0 ms | 14,90 ms | Não | 1 |
| 13 | Primeira, novo processo | 500 ms | 56,56 ms | Sim | 0 |
| 14 | Primeira, novo processo | 500 ms | 48,28 ms | Sim | 0 |
| 15 | Primeira, novo processo | 500 ms | 84,84 ms | Sim | 0 |

Mediana/máximo nas 11 reaberturas: **15,15/23,50 ms**. Nas quatro primeiras
apresentações: **56,87/84,84 ms**. As medianas usam os tempos sem arredondamento
das linhas da tabela. São amostras pequenas de uma máquina e de uma
janela anterior própria em tela cheia; não são p95, orçamento geral ou garantia
de digitação a 50 ms em todos os ambientes.

## Causa observada e decisão

Nas três tentativas a 0 ms, a emissão da primeira tecla começou **antes** da
entrada do callback do atalho. Sua entrega foi observada no campo anterior,
após essa entrada e antes de a janela Orla ficar ativa. Todos os nove caracteres
se dividiram entre os dois campos: 4 + 5, 1 + 8 e 1 + 8. Isso localiza a perda
na transição de foco entre processos.

Nenhum callback de atividade ativa observado tinha a busca sem foco. O pedido
KF foi concluído e sua ativação submetida antes da atividade em todas as
tentativas. O primeiro callback de frame veio antes da atividade; ele foi
entregue ao thread GUI por uma conexão Qt automática, portanto não mede emissão
do frame ou apresentação física na tela.

A revisão independente confirmou que o baseline **não demonstra** um gargalo
de pedidos duplicados ou um atraso de foco local do campo. Preservou-se a
ativação atual. Nenhuma alternativa foi instalada ou anunciada como melhoria
de latência. O cliente não pode recuperar uma tecla entregue a outro processo.

Isso é compatível com as fontes fixadas: [Qt 6.11.2 solicita ativação ao mostrar
a janela](https://github.com/qt/qtbase/blob/v6.11.2/src/plugins/platforms/wayland/qwaylandwindow.cpp);
[KF 6.30 transmite o timestamp na rota QAction](https://github.com/KDE/kglobalaccel/blob/v6.30.0/src/kglobalaccel.cpp);
[KWin 6.7.5 decide a ativação e pode aguardar prontidão para pintura](https://github.com/KDE/kwin/blob/v6.7.5/src/xdgactivationv1.cpp).
Token não vazio, sozinho, não prova concessão de foco.

## Encerramento e próximos gates

As tentativas fecharam por Escape, voltando ao campo próprio. Os processos de
observação terminaram, os dispositivos virtuais foram liberados e o serviço
instalado foi restaurado ativo, sem reinícios automáticos. Os wrappers ficaram
byte-idênticos; Meta continuou atribuída ao Orla. Plasma não foi recarregado.
Os dois checks de `8d0902b` passaram; os sete CTests anteriores continuam
evidência daquela revisão. Não foram repetidos para esta atualização documental.

Continuam abertos: outros monitores/escalas, desktop anterior comum, cargas
distintas, atalho inibido, reinício do daemon e orçamento de abertura/primeiro
resultado. Uma futura indicação de prontidão deve depender de atividade real
da janela **e** foco do campo. Qualquer otimização exige nova comparação nativa
com o mesmo método, incluindo primeira apresentação, janela já visível/inativa,
fechamento pendente, execução de app e recuperação do atalho. L0/L2 seguem parciais.
