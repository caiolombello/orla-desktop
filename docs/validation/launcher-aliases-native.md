# Aliases: primeira prova por gestos no KDE

Em 14/10/2026, o launcher de produção do código `4cf638f` passou a primeira
parte do fluxo real de aliases. A consulta mostrou dois aplicativos próprios
com o mesmo nome; cancelar preservou a ausência do arquivo e Salvar pelo
mouse gravou somente o ID do aplicativo selecionado. **Reinício, execução,
renomeação/remoção e retorno de foco continuam sem qualificação nesta prova.**
L2/UX2 permanecem parciais.

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

O próximo teste deve registrar saída normal antes de retirar o fundo próprio,
provar foco com digitação salva no mesmo documento, pesquisar o alias depois
de reiniciar e confirmar A=1/B=0 somente após Enter. Edição/remoção com alvo
disponível e ausente, esquema claro, outras escalas e monitores seguem abertos.
Esta prova não mudou código funcional, instalação nem assets públicos 0.2.9.
