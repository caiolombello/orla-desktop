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

No checkout: `python3 scripts/orla.py layout setup --service UNIT`, com PySide6 e
os widgets necessários já instalados. Há também um ZIP experimental separado,
relocável e um instalador experimental, descritos abaixo. Não há botão no plasmoid
apontando para um caminho do desenvolvedor. O instalador cria uma entrada própria
no menu; seus testes e revisão qualificam o contrato de instalação descrito abaixo,
separado do ciclo nativo.

O pré-requisito Menu Orla segue a [instalação manual da barra](../bar/README.md).
Também são necessários Menu Global, espaçador, bandeja, áudio/rede e relógio do
Plasma. A janela não instala widgets. `UNIT` é o nome literal do serviço Plasma
do usuário atual, verificado pelo helper; não há escolha automática de serviço.
Os comandos `layout status --service UNIT` e `layout setup --help` podem ser
consultados antes de abrir a janela.

## Bundle experimental separado

O ZIP do companion contém 21 arquivos permitidos no schema
`orla-workspace-package-0.2` e um manifesto de tamanhos, modos e SHA-256.
Inclui a janela de updates e sua CLI/contrato/estado/controller. Preserva os
imports relativos da interface e do helper; não inclui
Qt, a barra, o plasmoid inteiro ou um ambiente Python. Exige Python 3.10+ e
PySide6/Qt Quick 6.11+ instalados. Não é um novo canal de updates ou uma release.

Para construir a partir do commit revisado, no checkout:

```sh
python3 -I -B workspace/package.py build --commit COMMIT_40_HEX --output-dir OUTPUT
python3 -I -B workspace/package.py verify OUTPUT/orla-workspace-0.2.11.zip \
  --sha256 SHA256_64_HEX --commit COMMIT_40_HEX
```

Use os valores de commit/hash registrados para o artefato recebido. A verificação
deve usar uma cópia confiável do verificador antes da extração; hashes identificam
os bytes esperados, não autenticam o autor. O verificador recusa entradas extras,
duplicadas, ausentes, symlinks, modos divergentes e expansão excessiva. A extração
é feita numa pasta vazia, preservando arquivos regulares com modo 0644.

Depois de extrair, inclusive após mover a pasta ou mudar o diretório de trabalho:

```sh
python3 -I -B /CAMINHO/DO/BUNDLE/workspace/main.py --version
python3 -I -B /CAMINHO/DO/BUNDLE/workspace/main.py --diagnose
python3 -I -B /CAMINHO/DO/BUNDLE/workspace/main.py --updates
python3 -I -B /CAMINHO/DO/BUNDLE/workspace/main.py --service UNIT
```

`--diagnose` verifica a árvore e carrega as duas interfaces reais, composição
e updates, em um filho offscreen,
com diretórios XDG privados e barramentos ausentes. Distingue dependência Qt ausente,
versão incompatível, erro de QML e falha/timeout do processo. Não consulta ou inicia
Plasma; `nativeValidated` e `serviceContacted` permanecem falsos. `--version` não
exige Qt. `--updates` abre Sobre e atualizações sem serviço ou leitura de layout;
recebe a referência do manifesto já verificado, exibida como **esta cópia do Workspace**.
Ela não comprova a versão instalada/em execução da dock nem autentica o publicador.
`--updates` e `--service` são exclusivos. Abrir a composição exige `--service`
explícito e mantém os gates do backend.
Falhas de inicialização não exibem caminhos privados em tracebacks.

As raízes de configuração/estado são as do usuário que abre a composição. Valores
XDG relativos são ignorados em favor dos defaults, conforme a
[especificação XDG](https://specifications.freedesktop.org/basedir/latest/).
O bundle não instala widgets nem cria autostart, serviço ou atalho.

## Instalação gerenciada experimental

O bootstrap é o par confiável `workspace/install.py` e `workspace/package.py` do
mesmo código revisado, mantidos juntos. O instalador recebe o ZIP e os pins externos;
não baixa código nem escolhe um serviço automaticamente. Passou em testes privados
e revisão independente; não foi instalado na sessão do usuário. Em um diretório
com o par confiável:

```sh
python3 -I -B /CAMINHO/CONFIAVEL/install.py install /CAMINHO/DO/BUNDLE.zip \
  --sha256 SHA256_64_HEX --commit COMMIT_40_HEX --service UNIT
orla-workspacectl status
orla-workspacectl doctor
orla-workspace --updates
orla-workspace
```

`orla-workspace` e `orla-workspacectl` ficam em `$HOME/.local/bin`; a entrada
“Sobre e atualizações do Orla” fica no diretório XDG de aplicações, com ação
“Composição Orla”. A entrada principal executa o wrapper absoluto com `--updates`;
a ação e o comando sem flags preservam a composição. Continuam sendo três saídas
registradas no recibo: dois wrappers e um arquivo desktop. Não é criado autostart ou
serviço. Inclua `$HOME/.local/bin` no PATH, ou use os caminhos completos.
Depois da instalação, o bootstrap, o ZIP e o checkout não são necessários para
abrir, diagnosticar ou remover uma instalação íntegra. O serviço inicial fica
registrado; `orla-workspace --service OUTRA_UNIT` é uma substituição explícita
apenas para aquela execução.

Os arquivos próprios ficam em `$XDG_DATA_HOME/orla-desktop/workspace`, com versões
identificadas pelo hash do ZIP e ferramentas fixadas fora do payload. Estado e
histórico ficam em `$XDG_STATE_HOME/orla/workspace-install`. Valores XDG ausentes,
vazios ou relativos usam os defaults do usuário. Nenhuma dessas operações escreve
na configuração dos painéis, nos bancos de layout ou no launcher independente.

```sh
orla-workspacectl update /CAMINHO/DO/NOVO-BUNDLE.zip \
  --sha256 SHA256_64_HEX --commit COMMIT_40_HEX
orla-workspacectl rollback
orla-workspacectl recover
orla-workspacectl uninstall
```

Update mantém uma geração anterior; outro update é recusado enquanto ela existir.
Rollback alterna as duas gerações, preservando o serviço e as ferramentas do
gerenciador. Não há limpeza automática nem atualização remota nesta fatia.
Enquanto qualquer janela ou seu worker continuam vivos, update, rollback, recover e
uninstall recusam a alteração e pedem fechar o Workspace. Sinais são encaminhados
à janela e o supervisor aguarda o fechamento, sem timeout que mate uma transação.
Updates usa a mesma lease compartilhada,
herdada pela GUI, até o fechamento e a limpeza do processo de consulta terminarem.

Hashes, modos, identidade dos diretórios, recibos e colisões são conferidos antes
da alteração. Drift exige inspeção; `recover` não adota arquivos desconhecidos.
Recuperação automática cobre os checkpoints persistidos, não toda interrupção
possível entre criar um inode e registrar sua identidade. Se uma remoção parcial
já retirou as ferramentas instaladas, `recover` exige novamente o par confiável
original. Guarde esse par. Uninstall mantém a auditoria e remove somente a árvore
própria; restaurar os painéis é uma operação separada da janela de composição.

### Formato 0.1 → 0.2: instalação nova com confiança independente

O verificador antigo exige 16 arquivos e recusa o arquivo de 21 antes de escrever.
O novo recusa o formato antigo. Não há update, rollback ou adoção entre formatos;
as ferramentas instaladas e os recibos não podem ser remendados para aceitá-los.
O schema do estado/âncora continua `orla-workspace-install-0.1`.

Feche todas as janelas. Com o par **antigo** confiável, termine eventual `recover`
e execute `uninstall`. Confirme remoção concluída (seletor/pending nulos e
saídas removidas). Preserve a âncora e os registros de auditoria. Obtenha o novo
par `install.py`/`package.py` do mesmo Source revisado, por uma origem independente
do ZIP, e confira seus hashes confiáveis. Só então use o comando `install` acima,
com hash/commit externos e o serviço literal de composição. O histórico retido
válido é preservado; não apague estado, não force colisões nem aceite drift.
Recuperação de uma reinstalação 0.2 interrompida usa o novo par confiável.

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
qualificação da instalação na sessão do usuário e aceite nativo permanecem gates posteriores.
