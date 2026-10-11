# Descoberta local Steam experimental

`scripts/steam.py` consulta somente metadados de bibliotecas em raízes explícitas.
Esta é uma fatia de S1: favoritos, interface do dock e qualificação com dois
jogos reais continuam pendentes. O Source do launcher agora oferece provedor,
busca session-only e encaminhamento explícito das duas URIs allowlisted; isso
continua fora das releases públicas e sem qualificação nativa. A
rodada usou exclusivamente diretórios sintéticos próprios. Não houve leitura de
biblioteca pessoal nem chamada ao cliente Steam. A CLI está incluída no ZIP da
prerelease 0.2.6. Os assets da
release 0.2.5 publicada não a incluem. O Menu Orla experimental e o launcher
continuam fora dos bundles públicos até 0.2.9.

O contrato JSON é `0.1-experimental`, independente da versão do Orla. O futuro
consumidor deve tratar nomes como texto simples e distinguir inventário completo,
parcial e desconhecido. O formato dos manifestos locais não é API pública estável.

## Uso explícito

Python 3.10+ no Linux, biblioteca padrão, sem Qt, rede, credenciais ou dependências
externas. Execute a CLI em seu próprio processo; o coletor usa um worker `fork`
limitado e não deve ser chamado de dentro de um processo Qt com threads.

```bash
python3 -B scripts/steam.py scan --root native=/caminho/sintetico/Steam
python3 -B scripts/steam.py scan --root native=/caminho/sintetico/Steam --root flatpak=/caminho/sintetico/FlatpakSteam
python3 -B scripts/steam.py uri --action game --appid 42
python3 -B scripts/steam.py uri --action downloads
python3 -B -m unittest discover -s tests -p 'test_steam.py' -v
```

`uri` apenas imprime uma string. As únicas formas aceitas são
`steam://rungameid/<appid>` e `steam://open/downloads`; não há execução, shell,
argumentos de jogo, URI arbitrário nem chamada automática a outro aplicativo.
AppID precisa ser decimal ASCII canônico entre 1 e 4294967295. A geração não
comprova que o cliente, jogo ou handler de URI exista.

No launcher Source, abrir o painel Steam não executa a CLI. A pessoa cola de uma
a oito raízes no mesmo formato acima e aciona **Carregar jogos**. O controlador
inicia Python/helper absolutos com argumentos separados, valida schema, tipos,
limites, referências e correspondência do exit code antes de publicar qualquer
inventário. Recarga ou cancelamento retira resultados anteriores e incrementa a
revisão; Enter/clique revalida consulta, seleção, AppID, biblioteca e revisão.
As raízes, inventário e consulta não são gravados.

O handler do desktop só é chamado por gesto explícito e com uma URI reconstruída
da allowlist. Testes usam opener injetado; nenhum handler Steam real é registrado
ou chamado. Segundo a documentação do Qt 6.11.2, sucesso de
`QDesktopServices::openUrl` indica apenas que o pedido foi encaminhado ao sistema.

Exemplos convencionais de raízes a avaliar numa rodada real são
`/home/SEU_USUARIO/.local/share/Steam` e
`/home/SEU_USUARIO/.var/app/com.valvesoftware.Steam/data/Steam`. Estes exemplos
não foram consultados nem qualificados nesta rodada. Não há detecção automática
via `$HOME`, `~`, pacotes, processos ou Flatpak. `native`/`flatpak` é a origem
informada pelo chamador; a presença dos metadados não prova instalação do cliente.
Raízes e todos os seus componentes devem ser diretórios reais, absolutos, sem
links simbólicos, `..`, componentes vazios ou barra final; aliases como
`~/.steam/steam` podem ser links e serão rejeitados.

## Permissão e alcance da leitura

Fornecer uma raiz autoriza somente a leitura de
`steamapps/libraryfolders.vdf`, dos arquivos regulares com nome canônico
`steamapps/appmanifest_<appid>.acf` e da presença do diretório
`steamapps/common/<installdir>`. O conteúdo do jogo nunca é lido. O índice da raiz
também autoriza a consulta dos mesmos manifestos e da presença dos diretórios em
bibliotecas externas declaradas nele, inclusive em outro disco. Índices dessas
bibliotecas externas não são lidos nem seguidos recursivamente. O chamador precisa
entender essa expansão de alcance antes de fornecer uma raiz real.

Só nomes do diretório `steamapps` são enumerados. `loginusers.vdf`, configurações
de conta, `ssfn`, caches, `userdata`, saves/Cloud e outros diretórios não são
abertos. `installdir` aceita um único componente de caminho; nomes absolutos,
travessia, separadores, controles e links são rejeitados. Cada componente é aberto
por descriptor com `O_NOFOLLOW`; arquivos especiais e manifestos com hard links
são rejeitados. Bibliotecas duplicadas são consultadas uma vez. Não há escrita,
reparo, autenticação ou inferência de acesso à conta.

O parser aceita um subconjunto limitado de KV1: pares e blocos, tokens citados
ou simples, comentários `//`, UTF-8/BOM e escapes `\\`, `\"`, `\n`, `\t`, `\r`.
Chaves duplicadas, inclusive com diferenças de caixa, são rejeitadas. Diretivas,
includes, condições, escapes desconhecidos, truncamento e formatos não
reconhecidos geram erro explícito. Nunca são avaliados ou executados.
O índice aceita entradas numéricas antigas com caminho string e entradas com
bloco contendo `path`; o manifesto exige bloco `AppState`, AppID igual ao nome do
arquivo e nome/diretório válidos. Campos extras ficam fora do resultado.

## Resultado e limites

`discover([SteamRoot(path, kind)], Limits())` e a CLI retornam o mesmo inventário.
O resultado tem `schema_version`, `status`, `connection`, `ownership`, `roots`,
`libraries`, `apps` e `errors`. IDs de raiz/biblioteca são locais à consulta;
não são IDs estáveis entre consultas com entradas diferentes. Os campos de
inventário/erro omitem os caminhos usados na consulta; VDF bruto, campos de conta
e traceback não são publicados. Nomes são metadados não confiáveis, com a
neutralização específica descrita abaixo, sem anonimização arbitrária.
AppIDs são ordenados numericamente dentro de cada biblioteca; a ordem das raízes
segue a entrada e a das bibliotecas segue o índice numérico. Consultas idênticas
em dados idênticos produzem JSON idêntico, sem relógio/identificador aleatório.
O launcher também valida a coerência entre os estados antes de publicar a lista:
bibliotecas não podem pertencer a uma raiz ausente, apps só podem vir de uma
biblioteca consultável e um inventário completo não pode conter estados parciais
ou desconhecidos. Respostas contraditórias falham fechadas e não geram ação.

| Campo/estado | Significado |
| --- | --- |
| Inventário `available` | Consulta dos metadados reconhecidos concluída, dentro dos limites; não significa jogos atualizados ou jogáveis |
| Inventário `absent` | Todas as raízes explícitas estão ausentes; não comprova ausência global do Steam |
| Inventário `partial` | Parte dos metadados foi consultada, com erros/limites ou biblioteca indisponível |
| Inventário `unknown` | Nenhuma biblioteca pôde ser consultada, entrada inválida, deadline ou resultado grande demais |
| Raiz `absent` | A pasta raiz informada não existe; não comprova ausência global do Steam |
| Raiz `missing` | A pasta raiz existe, mas sua pasta primária `steamapps` não foi encontrada; a biblioteca correspondente também fica `missing` |
| Biblioteca `missing` | A pasta da biblioteca ou sua `steamapps` não foi encontrada; pode estar desmontada, movida ou removida, sem inferir a causa |
| App `installed_candidate` | `StateFlags` exatamente `4` e diretório `common/installdir` seguro presente; interpretação experimental de presença local |
| App `partial` | Hint `4`, mas diretório de instalação não encontrado |
| App `unknown` | Flags ausentes/não qualificadas ou alvo inacessível/inseguro; não é classificação de jogo desinstalado |
| `connection` e `ownership` | Sempre `unknown`; não se distingue online/offline nem titularidade por manifesto |

Com várias raízes, uma pasta `missing` pode coexistir com outra biblioteca
consultada. Nesse caso o inventário é `partial`, e os apps válidos da biblioteca
disponível continuam no resultado com seus próprios estados; a falha de uma raiz
não transforma os demais apps em ausentes nem comprova titularidade.

Nomes têm até 160 caracteres, sem caracteres de controle/formatação Unicode.
Podem ser truncados e continuam sendo metadados não confiáveis do manifesto.
Após retirar controles, nomes cujo início (desconsiderando espaços) pareça
caminho absoluto POSIX, caminho com drive Windows e separador, UNC, caminho
`~`/`~usuario`, `$HOME`/`${HOME}`, `%USERPROFILE%`/`%HOMEPATH%` ou URI `file:/`
são substituídos por `Jogo <appid>`. Esses apps têm `name_redacted: true`, erro
`pathlike_name_redacted` e inventário `partial`; a interpretação de presença
local e `ownership: unknown` permanece independente do nome. Títulos Unicode
comuns e separadores no meio do título são preservados. Essa regra não detecta
nomes pessoais, segredos arbitrários ou caminhos inseridos dentro de frases;
não trate o resultado como dado anonimizado para publicação sem revisão.
Manifestos inválidos não geram um app falso: preservam-se os demais apps e um
erro por código, com referência à biblioteca/AppID quando seguro. O inventário
não é snapshot atômico: Steam pode modificar metadados durante uma consulta.
Mudança de tamanho durante leitura é detectada; outras mudanças concorrentes
continuam possíveis. A autoridade para instalação, integridade, downloads,
updates e jogabilidade continua sendo o cliente Steam.

| Limite padrão máximo | Valor |
| --- | --- |
| Raízes / bibliotecas / manifestos | 8 / 32 / 512 por consulta |
| Entradas enumeradas | 4096 por diretório `steamapps` |
| Bytes por arquivo / total lido | 128 KiB / 4 MiB |
| Tokens / profundidade KV1 | 16384 / 16 por arquivo |
| Resultado JSON serializado | 512 KiB |
| Deadline do worker | 5 segundos, mais até 0,5 segundo de reap |

`Limits` permite reduzir esses máximos, nunca aumentá-los; valores inválidos
falham antes da leitura. O resultado limitado não é apresentado como lista vazia
completa. Exceder o tamanho do resultado retorna `unknown/result_byte_limit`;
deadline retorna `unknown/deadline`, encerrando o worker próprio. Um filesystem
com I/O preso no kernel pode impedir reap imediato: a validação sintética cobre
worker bloqueado comum e FIFO, não todos os estados de discos remotos/falhos.
Saída CLI: 0 para `available`, `absent` ou geração de URI; 2 para `partial`,
`unknown` ou entrada inválida. Erros têm códigos fixos, sem nomes de arquivos
rejeitados ou detalhes sensíveis.

## Fontes e qualificação pendente

Fontes consultadas em 2026-10-11, sem Steam Web API ou acesso a conta:

- [KeyValues.h da Valve, commit be57e3d01ac7d7aa6a2cacbfef187c0b46616db0](https://github.com/ValveSoftware/source-sdk-2013/blob/be57e3d01ac7d7aa6a2cacbfef187c0b46616db0/src/public/tier1/KeyValues.h): referência lexical KV1; SHA-256 `760f3794a728bc1265977cc706312af94218d696e0090317d4c9c082d4becfde`. Não define o schema dos manifestos do cliente Steam nem o significado de `StateFlags`.
- [Steam Support: bibliotecas e movimentação de jogos](https://help.steampowered.com/en/faqs/view/4BD4-4528-6B2E-8327): confirma bibliotecas em outros discos e gerenciamento pelo cliente. As instruções publicadas exemplificam Windows; não provam os caminhos Linux/Flatpak propostos.
- [Valve Developer Community: KeyValues](https://developer.valvesoftware.com/wiki/KeyValues) e [Steam browser protocol](https://developer.valvesoftware.com/wiki/Steam_browser_protocol): URLs primárias fixadas, mas a leitura retornou HTTP 403. O protocolo completo e os URIs gerados permanecem pendentes de consulta/qualificação nativa; testes aqui verificam somente construção e validação das strings.

O recibo local `.runtime/steam-discovery/sources.json` registra essas consultas e
o pin do arquivo da Valve. Vinte testes offline do helper passaram; isso não
promove o formato local a API estável. A integração Source do launcher usa apenas
fixtures fechadas e árvores próprias. Permanecem pendentes: consentimento para
raízes reais, dois jogos reais, disco externo presente/desmontado, Steam ausente,
gesto humano e ações pelo handler real. S1 permanece aberto até esses gates e os
favoritos serem qualificados.
