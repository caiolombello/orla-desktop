# Consulta experimental de updates

Disponível no checkout fonte e no ZIP da release 0.2.5, em `scripts/updates.py`. Execute no diretório extraído do bundle; o `.plasmoid` sozinho não contém a CLI nem uma interface de updates. A release 0.2.4 não incluía esse comando. Esta primeira fatia de U1 é uma CLI Linux com Python 3.10+ e biblioteca padrão. Ela consulta releases públicas do repositório oficial por HTTPS e compara a versão informada. O desktop não precisa estar aberto.

```bash
python3 scripts/updates.py check --installed-version 0.2.5 --channel beta
```

Substitua `--installed-version` pela versão que deseja comparar. O comando não detecta a versão instalada ou em execução. `stable` exclui a marcação de pré-release do GitHub e sufixos SemVer; `beta` inclui ambos. As alphas atuais, como `v0.2.4`, usam a marcação de pré-release do GitHub mesmo sem sufixo. Portanto, o canal estável pode retornar `no_release`.

O stdout contém um objeto JSON com `status`, `reason`, `source`, `installed_version`, `available_version`, `available_url`, `channel` e `checked_at` UTC. Versões seguem SemVer estrito; metadados de build não alteram a precedência.

| Estado | Significado |
|---|---|
| `update_available` | Existe uma versão elegível mais recente |
| `up_to_date` | A versão informada alcança ou supera a mais recente do canal |
| `no_release` | A consulta terminou sem release elegível no canal |
| `unavailable` | Entrada, rede, protocolo, resposta ou consulta incompleta impedem a comparação |
| `rate_limited` | O GitHub recusou a consulta com 403/429 |

Os três primeiros estados retornam código 0; os dois últimos retornam 2. A consulta não baixa pacotes, instala, grava cache, usa tokens ou altera a configuração da sessão. Há somente uma fonte fixa; redirects são recusados. Respostas/URLs incompatíveis produzem erro seguro, sem conteúdo bruto do servidor.

Limites: até duas páginas de 50 releases, 256 KiB por resposta e 384 KiB no total. Um teto cheio é tratado como consulta incompleta. O trabalho de rede ocorre em processos próprios, com deadline de até 5 segundos por requisição e orçamento total de 12 segundos; encerrar e recolher os recursos do último processo pode acrescentar até 0,5 segundo ao retorno (até 5,5/12,5 segundos). Não há tentativa automática após falha.

Execute esta CLI como processo independente. Seu transporte usa `fork` no Linux e não oferece uma API para importar em uma aplicação Qt com várias threads. O parâmetro interno `fetcher` é uma fixture síncrona cooperativa para testes, sem a garantia de deadline do transporte de produção.

```bash
python3 -m unittest discover -s tests -p 'test_updates.py' -v
```

Os 17 testes offline passaram em Python 3.14.7; a revisão independente repetiu o resultado. A cobertura inclui canais, precedência, respostas inválidas/grandes, paginação incompleta, URLs hostis, falhas de protocolo/rede e encerramento de um worker bloqueado com PID morto e reapado. A consulta anônima com o transporte final comparou `0.2.3` no canal beta e retornou `update_available`, versão `0.2.4`. Isso verifica somente a consulta e comparação, sem instalar ou validar um pacote. A CI executa os testes offline em processo próprio.

U1 completo ainda exige a entrega instalada e a proveniência da dock instalada/em execução. A fase A abaixo acrescenta histórico, canal e UI no Source. U2 exige compatibilidade, autenticidade dos pacotes, preservação da configuração e recuperação após atualização interrompida.

Fontes: [API de releases GitHub](https://docs.github.com/en/rest/releases/releases?apiVersion=2022-11-28#list-releases), [paginação](https://docs.github.com/en/rest/using-the-rest-api/using-pagination-in-the-rest-api) e [limites de consultas](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api#exceeding-the-rate-limit).


## Janela Source — fase A de U1

Em uma cópia completa do Source, Python/PySide6 6.11+ pode abrir a janela independente:

```bash
python3 -B scripts/orla.py updates desktop
```

A primeira abertura é passiva: lê a referência limitada de `package/metadata.json`
e o histórico local, sem criar arquivos, consultar a rede, iniciar serviços ou
inspecionar o Plasma. A referência é **pacote fonte do dock**; as versões da dock
instalada e em execução permanecem **não verificadas**. Referência ausente ou
inválida desabilita a consulta. Não há substituição por uma versão presumida.
A versão de referência tem destaque com sua origem explícita. As linhas de versão
instalada/em execução e a explicação de escopo ficam em **Sobre os componentes**;
expandir mantém os dois estados não verificados e não faz uma consulta.

Somente **Consultar agora** inicia a CLI existente em outro interpretador, com
argumentos literais. O processo Qt não importa o transporte de rede. O watchdog
externo é de 15 segundos; stdout/stderr retidos têm limite de 16 KiB cada. A janela
aguarda o encerramento do processo e de seu grupo antes de concluir o fechamento.
Nenhuma consulta executa instalação, update, rollback, coleta ou integração opcional.
A abertura da página canônica de release requer um clique explícito; o retorno
do navegador confirma apenas a solicitação de abertura.

O canal Estável/Beta é salvo em `$XDG_CONFIG_HOME/orla/updates.json`. O histórico
fica em `$XDG_CACHE_HOME/orla/updates-desktop.json`, com uma tentativa e a última
consulta concluída por canal e referência completa (papel, componente, origem,
versão, commit ou nulo e digest). XDG vazio/relativo usa os diretórios padrão do
HOME. Os arquivos são limitados, validados e substituídos atomicamente com modo
0600; links, arquivos não regulares e pais inseguros são recusados. Perda ou falha
de cache não impede uma consulta e nunca autentica o publicador.

Reabrir, mudar canal ou expandir informações não consulta. Um registro reaberto é
sempre histórico datado; uma falha recente permanece principal mesmo após sucesso
anterior. `no_release`, indisponibilidade e limite de consultas não afirmam que a
dock está atualizada. `checked_at` identifica o início informado pela CLI; o host
registra a conclusão separadamente. A interface apresenta datas e horas no formato
da localidade e no fuso local, inclusive quando a data difere do dia em UTC. Os
valores UTC canônicos continuam intactos no histórico e podem ser lidos na expansão
de componentes. A formatação não torna atual um resultado salvo. Horários
futuros continuam marcados não confiáveis.

A CLI e seu contrato puro continuam no ZIP de contribuição. Os módulos e testes
desktop são excluídos desse ZIP porque `workspace/Updates.qml` não faz parte dele;
`updates desktop` recusa esse kit incompleto antes de importar Qt. O `.plasmoid`
continua sem CLI/UI. A entrega separada do Workspace é descrita a seguir.

## Entrega no bundle e na entrada instalada — fase B

O candidato Workspace usa `orla-workspace-package-0.2`: exatamente os 16 arquivos
anteriores mais `workspace/Updates.qml`, `scripts/updates.py`,
`scripts/updates_contract.py`, `scripts/updates_desktop_state.py` e
`scripts/updates_desktop.py`. O manifesto não conta entre os 21. O verificador e
seu pin no novo gerenciador mudam juntos; estado/âncora permanecem no schema 0.1.

`workspace/main.py --updates` verifica o bundle inteiro antes de Qt e abre a QML
real, sem serviço, NativeRuntime ou refresh de layout. `--service` é exclusivo;
`--version` continua sem Qt e `--diagnose` carrega ambas as superfícies com
controllers inertes, XDG privado e buses ausentes. A referência explícita é
`bundle/workspace/verified-manifest`, com versão, commit e digest canônico do
manifesto verificado, exibida como **esta cópia do Workspace**. Isso não comprova
instalação, dock carregada, autenticação do autor ou assets compatíveis da família.

A entrada **Sobre e atualizações do Orla** executa o wrapper absoluto com
`--updates`. A ação **Composição Orla** executa o mesmo wrapper sem flags;
`orla-workspace` direto mantém a composição. Não há quarta saída, integração
padrão, serviço ou job. Abrir/reabrir/trocar canal é passivo; somente Consultar
agora inicia a CLI. A lease compartilhada bloqueia update/uninstall/rollback/
recover até a GUI e a consulta concluírem a limpeza, inclusive após sinais.

O formato é incompatível com as ferramentas antigas. Use a [rota de instalação
nova com confiança independente](workspace-composition.md#formato-01--02-instalação-nova-com-confiança-independente):
recover/uninstall com ferramentas antigas; confirme ausência e retenha âncora e
histórico; obtenha ferramentas novas confiáveis fora do ZIP e instale o novo
arquivo com pins explícitos. Não há migração ou update/rollback entre formatos,
adoção de arquivos, alteração de recibos ou troca das ferramentas instaladas.

A qualificação desta fase é privada, sintética e offscreen. Integração, revisão,
publicação e instalação na sessão pertencem a Root. A proveniência da dock
instalada/em execução continua aberta; U1 permanece parcial e U2, Plasma/Wayland/AT
não são qualificados por esse fluxo.

As suítes `test_updates_desktop*.py` usam a QML de produção e processos sintéticos,
com HOME/XDG/TMPDIR privados, buses ausentes e Qt offscreen/software. A galeria
inclui estados de consulta, histórico, falha e foco curto, em claro/escuro.
As APIs de sessão são as de [QProcess no PySide6 6.11](https://doc.qt.io/qtforpython-6.11/PySide6/QtCore/QProcess.html):
`CreateNewSession` e `CloseFileDescriptors`, sem modificador Python entre fork/exec.
