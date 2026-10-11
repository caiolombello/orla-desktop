# Alpha 0.2.9 — Central de Controle e PeriGauge

**Estado:** publicada como prerelease alpha; instalação e admissão nativa continuam UNRUN. A revisão independente round 3 aprovou a fatia Source sem blockers ou nits. Esta validação registra o escopo de CI e os recibos anônimos dos três assets, sem ampliar a admissão nativa.

## Central de Controle

A fatia publicada tem preferência global default-off; os cards reutilizam MPRIS e `SystemBattery`. As três páginas de configurações KDE só recebem despacho após ação explícita. O teste mock não prova que uma janela abriu ou um ajuste foi aplicado.

No round 2, quatro testes do ciclo de preferência passaram com Fusion offscreen. A execução mais ampla relacionada registrou 84 PASS, 3 SKIP preexistentes de TaskManager e uma falha antiga de contagem codificada, também reproduzida na baseline limpa. Um teste intermediário de largura estreita falhou devido à fixture Python que não substituía binding QML; o estilo KDE também não ficou verde por warning do Breeze TextArea. Estes registros históricos foram mantidos.

O round 3 corrigiu o viewport e a navegação por teclado. Quatro testes focados com Fusion offscreen passaram. Separadamente, a revisão independente aprovou o Source sem blockers ou nits e executou o caso integrado congelado 260×320: a última ação começou fora da viewport, recebeu foco por Tab comum, provocou `contentY > 0` e ficou totalmente visível, sem dispatch de backend nem Loader nativo. A revisão cobre o Source e esse teste focado, não uma suíte ampla ou sessão Plasma.

UNRUN: instalação, abertura nativa de KCM/Configurações do Sistema, popup/grab/foco/posicionamento em compositor, MPRIS/UPower reais, barramento de sessão, hardware e admissão da suíte completa. A release 0.2.9 não executou o conjunto QML do Control Center na CI e não compilou o launcher C++. O ZIP inclui `scripts/ai.py` e `tests/test_ai.py`, mas exclui o launcher C++/QML e a barra; isso não indica prontidão da integração de IA.

## Publicação e artefatos

A Source `a377340b2a37555a57fc87360d45ed68c815ccda` foi integrada pelo [PR 22](https://github.com/caiolombello/orla-desktop/pull/22), merge `3c27fd01b2f3571b6d4eb71d68d8095f9b0bf85a`; CI [38116955839/job 114403627560](https://github.com/caiolombello/orla-desktop/actions/runs/38116955839/job/114403627560) passou às 06:06:55 UTC. Foram 17 testes do bridge (5.541 s); esta CI não executou os testes QML do CC0 nem compilou C++.

A [release v0.2.9](https://github.com/caiolombello/orla-desktop/releases/tag/v0.2.9) foi publicada às 06:08:41 UTC como prerelease e `latest=false`. Os três downloads anônimos retornaram HTTP 200 e coincidem byte a byte com as builds de origem. Duas builds candidatas e uma build do commit exato foram idênticas: 154 arquivos Source, 124 entradas ZIP e 38 entradas do applet.

| Asset | Tamanho | SHA-256 |
|---|---:|---|
| [Applet `.plasmoid`](https://github.com/caiolombello/orla-desktop/releases/download/v0.2.9/orla-dock-0.2.9.plasmoid) | 61,122 bytes | `3bb66040c3e79ba52282eb15a9d807046da84e6b8d2f1fce80d8224af3a62278` |
| [Bundle ZIP](https://github.com/caiolombello/orla-desktop/releases/download/v0.2.9/orla-dock-0.2.9.zip) | 503,854 bytes | `8eda180dcf8098df23bd0f386a2370af010958223ad0ac54cc85114f02bf4799` |
| [`SHA256SUMS`](https://github.com/caiolombello/orla-desktop/releases/download/v0.2.9/SHA256SUMS) | 177 bytes | `1d4a8fe2c232dcf6b8d03250400ee2250ea7c368af6b7ccdf06a3000eac6a5b6` |

## PeriGauge

A correção Source/mock round 2 recebeu **aprovação independente sem findings**, limitada aos seis arquivos pinados e aos contratos/testes sintéticos. A evidência do autor inclui 17/17 testes de bridge e 3/3 testes de UI isolada, mais dois testes focados para flags malformadas e um teste legado. A revisão independente executou quatro verificações focadas e uma matriz adversarial separada; esses números não são uma única suíte combinada.

Flags `stale` malformadas neutralizam fatos atuais de bateria e marcam o snapshot como limitado; `hidden` malformado omite o dispositivo e também marca estado limitado. Flags ausentes preservam a compatibilidade aditiva schema 1 conforme o contrato. “Reler cache local” não coleta dados nem executa CLI. O estado deve distinguir presente, origem, leitura antiga/limitada, ausente e desconhecido.

UNRUN: cache/dataset real do usuário, daemon ou serviço, hardware, rede, painel nativo, instalação e comportamento de sessão. I1 permanece parcial; QuotaLantern ainda não tem custo tipado suportado e FalaTrace não pode afirmar liveness (permanece `false`).
