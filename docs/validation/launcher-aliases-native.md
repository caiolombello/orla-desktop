# Aliases: primeira prova por gestos no KDE

Em 14/10/2026, o launcher de produção do código `4cf638f` passou a primeira
parte do fluxo real de aliases. A consulta mostrou dois aplicativos próprios
com o mesmo nome; cancelar preservou a ausência do arquivo e Salvar pelo
mouse gravou somente o ID do aplicativo selecionado. Uma rodada posterior
confirmou consulta após reinício e retorno de foco, com dois marcadores salvos.
**Enter fechou o launcher, mas o aplicativo próprio não executou: A=0/B=0.**
Naquela rodada, execução e renomeação/remoção ficaram abertas. A seção final
registra a prova após a correção; L2/UX2 permanecem parciais.

O ambiente tinha pacotes Plasma/KWin 6.7.5, Qt 6.11.2 e KF6 6.30 instalados,
Wayland, uma saída de 3840×2160 e escala observada 1,45. O ELF instalado tinha
SHA256 `0781d70ee2391f166064b43863c9d8bb45f9f15e26de72e0ea5edaaa00038004`.
As janelas usaram o renderer nativo, sem backend offscreen. O launcher foi
aberto com `--no-global-shortcut`; o atalho pessoal Windows/Meta não foi
requalificado aqui.

## Fluxos observados

Foi criado um perfil privado HOME/XDG, um bus sem ativação de serviços e uma
janela KWrite com documento sintético. Dois descritores próprios tinham nome
igual, descrições A/B, ícones diferentes e IDs estáveis distintos. A leitura
KService conferiu cache e arquivos físicos nos caminhos exatos, com os
metadados de lançamento correspondentes. Não houve invocação direta de
callbacks QML, métodos de salvar/executar ou propriedades do controlador.

| Ação real | Resultado delimitado |
|---|---|
| F11 no KWrite | A mesma janela passou a fullscreen e serviu de fundo próprio |
| Digitar o nome compartilhado | Dois resultados visíveis, A selecionado e B separado |
| Ctrl+K, Enter | Menu de ações e editor de alias centralizados; campo recebeu foco |
| Digitar um rascunho, Escape | Editor fechou, launcher continuou vivo, nenhum arquivo de aliases criado |
| Reabrir, digitar `ornativea`, mover e clicar em Salvar | Ponteiro medido no botão; arquivo 0600 com somente `ornativea` → `org.orla.AliasNativeA.desktop` |
| Conferir execuções após Salvar | A=0 e B=0; consultar/editar não executou os descritores |

As capturas incluem somente a janela do launcher sobre o documento próprio.
O observador retornou geometria/UUID das duas janelas próprias e indicadores
de segurança do recorte, sem títulos ou dados dos demais aplicativos.
As cópias publicáveis removem metadados textuais do PNG, incluindo o nome da
saída e timestamps; os chunks de pixels comprimidos permanecem idênticos aos
recortes nativos privados.

| Captura nativa, esquema escuro | Imagem |
|---|---|
| Aplicativos de nome igual | [Busca](../screenshots/launcher-aliases/apps-native-dark.png) |
| Editor antes do clique real | [Criar alias](../screenshots/launcher-aliases/create-native-dark.png) |

As capturas tiveram verificações antes/depois; isso não prova visibilidade
contínua entre elas. A imagem inteira temporária ficou em RAM e foi removida.
O executável carregado do KWin não pôde ser inspecionado pelo usuário da
sessão. Seu owner D-Bus, PID, UID e start tick foram conferidos, assim como a
ABI dos getters utilizados; não se declara verificada sua cadeia de binários.
Os demais processos tiveram identidade de executável e época conferidas.

## Interrupção e conservação

Uma primeira preparação foi encerrada antes de abrir o launcher: três módulos
vazios da biblioteca D-Bus instalada tinham hard links e o guard os recusou.
Foi usada uma nova tentativa com cópias privadas dos 24 arquivos Python,
hashes iguais, single-link e sem bytecode; o pacote instalado ficou preservado.

Na segunda tentativa, depois de Escape, a rotina de acompanhamento falhou com
`FileNotFoundError`. A limpeza observou saída zero do launcher, KWrite e bus,
sem término forçado ou erros, e A=0/B=0. O arquivo salvo permaneceu no perfil
privado. A falta do recibo normal de saída e do marcador no documento impede
qualificar o retorno de foco. A corrida entre poll e leitura do processo foi
reproduzida com mocks na rotina de teste e corrigida numa preparação separada:
se o processo desaparecer, um único novo poll do mesmo handle precisa confirmar
sua saída. Permissão recusada, drift e código anormal continuam falhas. Os 30
testes puros passaram e a revisão independente qualificou essa preparação;
o fluxo nativo ainda precisa ser repetido. Isso não confirma retrospectivamente
a causa deste episódio nem aponta uma falha no código funcional do launcher.

Os dispositivos temporários de input foram liberados, seus handles fechados
e o bridge saiu zero. Os plugins de observação usados nas leituras/capturas
foram descarregados. A limpeza conservou os 1.402 guards de arquivos e 233
de diretórios desta tentativa, incluindo Source, instalação, atalhos,
configurações e bancos de layout. O arquivo pessoal de aliases continuou
ausente; somente o perfil privado recebeu o alias de teste.

Preparação e revisão também preservaram dois harnesses incorretos que fizeram
lookup inadvertido de existência em `/proc` para PIDs de fixture. Esses logs
não provam recusa de permissão; foram substituídos por contrastes com `os.stat`
interceptado. Não se usa esses primeiros resultados como aceite nativo.

## Reinício e foco: rodada posterior

Uma nova rodada usou Source `f448ac3`, o mesmo ELF funcional `4cf638f`, a rotina
de acompanhamento corrigida e um novo perfil, nonce, bus, cache e KWrite.
Os bytes 0600 do alias criado pelo mouse na rodada anterior foram copiados
exclusivamente para esse novo perfil, com origem, destino e hashes registrados.
Isso foi preparação de dados próprios; não representa nova criação pela UI
nem continuação dos processos ou recibos anteriores. Nenhuma API do controlador
foi usada para salvar ou executar.

O preflight voltou a conferir os dois descritores físicos e o cache nos
caminhos exatos. O primeiro processo novo mostrou `ornativea` como alias do
aplicativo A. Escape produziu recibo normal de saída zero, retirou a janela do
launcher e devolveu o foco ao mesmo UUID do KWrite. Digitação e Ctrl+S gravaram
uma vez o primeiro marcador no documento sintético.

O segundo processo novo, usando o mesmo perfil desta rodada, voltou a mostrar
o alias. Antes de executar, A=0/B=0. Um único Enter fechou o launcher com saída
zero e devolveu o foco; um segundo marcador distinto foi salvo uma vez no mesmo
documento. Porém, não surgiu nenhum recibo de execução dos aplicativos próprios:
A e B continuaram zero até a limpeza. O fechamento não comprova abertura do app.
O log registra indisponibilidade do portal e fallback de lançamento do KIO no
bus privado; a causa da ausência de execução ainda não foi isolada.

A terceira fase, de editar/remover, não começou: seu gate exigia A=1/B=0 e foi
mantido. A limpeza encerrou os quatro filhos próprios com saída zero, sem
término forçado, sinais externos ou erros; os dois bridges de input liberaram
os dispositivos e saíram zero. Os 1.405 guards de arquivos e 233 de diretórios
ficaram exatos. A configuração pessoal de aliases permaneceu ausente.

Naquela etapa, o próximo passo era isolar a ausência de dispatch, incluindo o término do modo
`--no-global-shortcut` e o lançamento assíncrono no bus sem ativação. Esse
resultado não prova falha no modo gerenciado que permanece vivo após ocultar.
Execução A=1/B=0, edição/remoção com alvo disponível e ausente, esquema claro,
outras escalas e monitores ficaram abertos naquela etapa. As rodadas não mudaram código
funcional, instalação nem assets públicos 0.2.9.

## Lançamento, edição e fechamento após a correção

O Source `dd02b7b` corrigiu a saída do modo sem atalho global: o encerramento
agora respeita o quit lock do Qt e não permite reabrir uma sessão que já pediu
saída definitiva. Seis casos no `main` real falharam antes da correção; os sete
casos da regressão e os oito CTests completos passaram em Fusion e KDE depois.
O build permanente foi instalado, com serviço ativo e ELF conferido. Apenas o
caminho do executável no wrapper mudou; configurações, bancos de layout,
preferências pessoais e semântica de Meta/atalhos ficaram exatos.

Uma primeira rodada com esse build confirmou A=1/B=0 e edição/remoção, mas o
supervisor perdeu a confirmação do último fechamento com `FileNotFoundError`.
Ela permanece parcial: ausência posterior do PID não foi convertida em saída
zero nem em retorno de foco. A corrida foi reproduzida com handles falsos e
corrigida na rotina privada de acompanhamento; 41 testes puros e revisão
independente passaram. A rotina só aceita o resultado do mesmo handle próprio,
com espera limitada; uma identidade ausente não autoriza sinal por PID.

A rodada seguinte começou com novos pins, nonce, perfil, bus, cache e KWrite,
sem reaproveitar processos ou recibos. Os dados próprios criados pela UI foram
copiados novamente como preparação, com bytes e modo conferidos. Os dois apps
tinham o mesmo nome, IDs e comandos distintos, e descritores físicos/cache
conferidos antes dos gestos.

- O primeiro launcher mostrou o alias e fechou com Escape, saída zero e retorno
  ao KWrite. O primeiro marcador foi salvo uma vez no documento sintético.
- Após reiniciar no mesmo perfil desta rodada, um único Enter abriu A, com
  A=1/B=0. O launcher saiu zero; o segundo marcador confirmou o retorno de foco.
- No terceiro processo, Ctrl+K abriu o gerenciador. Editar e Salvar pelo mouse
  persistiram o novo nome com o mesmo ID de A. Os cliques foram medidos na
  captura própria e conferidos pela posição real do cursor.
- Após retirar o descritor próprio de A, o alias apareceu indisponível. Enter
  manteve a janela aberta e A=1/B=0, sem escolher B pelo nome. Remover pelo
  gerenciador publicou a lista vazia; dois Escapes fecharam popup e launcher.
  A saída foi zero e o terceiro marcador foi salvo uma vez no mesmo KWrite.

Os três retornos chegaram ao mesmo UUID da janela anterior, em fullscreen.
A limpeza terminou zero, sem término forçado, sinais externos ou erros;
os dispositivos temporários foram liberados. Os 1.430 guards de arquivos e
236 de diretórios ficaram exatos ao encerrar. O serviço instalado continuou
com o mesmo PID/ELF, sem reinícios, e o arquivo pessoal de aliases permaneceu
ausente.

As capturas publicadas contêm somente a janela própria do launcher. Os chunks
de imagem foram preservados; metadados textuais e de horário foram retirados.
A verificação da cena aconteceu antes/depois da captura, sem prova contínua.

| Fluxo real, esquema escuro | Captura |
| --- | --- |
| Editor antes de Salvar | [Editar no KDE](../screenshots/launcher-aliases/native-r5-edit.png) |
| Alias ausente antes de Remover | [Indisponível no KDE](../screenshots/launcher-aliases/native-r5-missing.png) |

Esse aceite é limitado ao build instalado e ao perfil privado nesta máquina,
em uma saída de escala 1,45. Não qualifica o fluxo de aliases no perfil pessoal,
atalho global nesta rodada, esquema claro nativo, acessibilidade, outras
escalas/monitores ou todos os lançadores do KRunner. Favoritos, comandos internos
e a conclusão de L2/UX2 permanecem abertos. As rodadas anteriores e os assets
públicos 0.2.9 foram preservados.
