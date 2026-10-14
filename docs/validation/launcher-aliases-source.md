# Launcher: aliases editáveis de aplicativos

Código `4cf638f`, de 14/10/2026. **Ações → Adicionar alias…** guarda um nome
curto para o aplicativo selecionado. **Gerenciar aliases…** também funciona
com consulta vazia e permite renomear ou remover alvos indisponíveis. A busca
exata oferece a origem **Alias salvo por você**; digitar ou abrir preferências
não executa o aplicativo. Enter/clique encaminha somente o alvo escolhido.

A interface usa os tokens existentes, controles de 40 px, foco de 2 px e texto
PT-BR limitado. Escape fecha primeiro o popover e devolve foco à busca. Tab
revela os controles quando a lista de 16 entradas precisa rolar. O ID técnico
aparece para aplicativos indisponíveis ou nomes iguais de IDs diferentes;
um aplicativo normal mostra seu nome. O footer de um alias diz **Abrir**.

## Contrato e verificação Source

O formato local `0.1-experimental` guarda somente alias e ID estável de
aplicativo, até 16 entradas de 1–32 caracteres. Leituras não criam nem reparam
arquivos. Dados inválidos, versões desconhecidas e caminhos inseguros são
preservados. Escritas conferem revisão, usam lock cooperativo e publicação
atômica; isso não é CAS contra escritores que ignoram o lock nem garantia de
durabilidade após falha de energia.

KService/KRunner 6.30 e 6.31 receberam provas privadas de resolução exata:
dois aplicativos com o mesmo nome, pesquisa passiva, reinício, alterações do
descritor, alvos ausentes/ocultos e renomeação/remoção. O encaminhamento usa
o runner permitido atual, sem armazenar Exec ou um ID temporário do resultado.
O retorno do runner admite o pedido; não confirma a abertura assíncrona de
uma janela. Getter de apresentação permanece passivo.

Na versão imutável final, os oito CTests passaram com Fusion em **102,424 s**
e `org.kde.desktop` em **106,595 s**, Qt 6.11.2/KF6 6.30. Os testes existentes
foram preservados; o novo caso cobre 440/660 px, caracteres não BMP, colisão,
estado somente leitura, leitura ao reabrir, recusa de cliques antigos, busy e
fechamento. Dois slots da suíte geral exigem fixtures externas e são pulados;
o teste de aplicativo próprio roda separadamente. Design check: zero problemas;
sete testes do design passaram.

A composição privada KF6 6.31 compilou todos os 52 passos, passou 17 testes
do pacote e dois do seletor isolado. A primeira execução teve **6/8 PASS**:
o runner de preparação omitiu `--init`, presente na receita da CI. Um novo
container com `--init`, mesmos binários/Source e watchdogs, passou somente os
dois testes que falharam, em **44,249 s**. Os resultados anteriores foram
preservados; esta é uma união delimitada, não uma nova execução completa verde.
Os dois containers foram parados. Não se atribui a falha a zombies originais
sem observação, nem se declara CI de base limpa aprovada.

Foram renderizadas 22 capturas sintéticas: Fusion/sistema escuro e KDE/sistema
claro, 440/660 px, sem warnings. O launcher permanece escuro nos dois esquemas.

| Superfície | Captura |
|---|---|
| Lista, sistema escuro, 660 px | [Aliases](../screenshots/launcher-aliases/manager-dark-660.png) |
| Lista, sistema claro, 440 px | [Lista estreita](../screenshots/launcher-aliases/manager-light-440.png) |
| Editor e foco | [Editar](../screenshots/launcher-aliases/editor-dark-660.png) |
| Dados indisponíveis preservados | [Estado indisponível](../screenshots/launcher-aliases/unavailable-light-440.png) |

## Instalação local e limites

A instalação trocou somente o caminho do ELF no wrapper e reiniciou
`orla-launcher.service`. A cópia de runtime contém os 302 arquivos-fonte
conferidos, sem permissão de escrita. O serviço ficou ativo, sem reinícios
automáticos, com o ELF esperado. Permaneceram exatos os 1.396 guards de
arquivos e 234 de diretórios, incluindo configurações, dock/barra, bancos,
CLI e a ausência do arquivo pessoal de aliases. Teclas, defaults, owners de
Meta e owner do daemon de atalhos foram iguais antes/depois. A recuperação
não foi provocada na sessão real.

A [primeira prova nativa](launcher-aliases-native.md), de 14/10, passou consulta
de nomes iguais, abertura centralizada do editor, cancelamento e Salvar pelo
mouse sem executar os aplicativos. O acompanhamento da saída foi interrompido;
reinício, execução, edição/remoção, retorno de foco, esquema claro nativo,
acessibilidade, outras escalas e monitores continuam sem qualificação. L2/UX2
permanecem parciais; favoritos, comandos internos e o setup completo seguem
no roadmap. Assets públicos 0.2.9 permanecem inalterados.
