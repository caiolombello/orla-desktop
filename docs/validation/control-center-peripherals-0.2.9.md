# Candidata 0.2.9 — Central de Controle e PeriGauge

**Estado:** documentação de uma candidata Source; não publicada. O round 3 corrigiu o layout estreito e a navegação por teclado; a revisão independente final do Source aprovou essa fatia sem blockers ou nits. Não há commit de release, CI ou assets publicados para 0.2.9 neste registro.

## Central de Controle

A candidata tem preferência global default-off; os cards reutilizam MPRIS e `SystemBattery`. As três páginas de configurações KDE só recebem despacho após ação explícita. O teste mock não prova que uma janela abriu ou um ajuste foi aplicado.

No round 2, quatro testes do ciclo de preferência passaram com Fusion offscreen. A execução mais ampla relacionada registrou 84 PASS, 3 SKIP preexistentes de TaskManager e uma falha antiga de contagem codificada, também reproduzida na baseline limpa. Um teste intermediário de largura estreita falhou devido à fixture Python que não substituía binding QML; o estilo KDE também não ficou verde por warning do Breeze TextArea. Estes registros históricos foram mantidos.

O round 3 corrigiu o viewport e a navegação por teclado. Quatro testes focados com Fusion offscreen passaram. Separadamente, a revisão independente aprovou o Source sem blockers ou nits e executou o caso integrado congelado 260×320: a última ação começou fora da viewport, recebeu foco por Tab comum, provocou `contentY > 0` e ficou totalmente visível, sem dispatch de backend nem Loader nativo. A revisão cobre o Source e esse teste focado, não uma suíte ampla ou sessão Plasma.

UNRUN: abertura nativa de KCM/Configurações do Sistema, popup/grab/foco/posicionamento em compositor, MPRIS/UPower reais, barramento de sessão, hardware, build, pacote, release e suíte completa. A 0.2.9 continua candidata não publicada. O bundle ainda não foi construído; quando for gerado pelo builder atual, o ZIP incluirá `scripts/ai.py` e `test_ai.py` e excluirá launcher C++/bar. Essa composição não indica que a integração de IA esteja pronta.

## PeriGauge

A correção Source/mock round 2 recebeu **aprovação independente sem findings**, limitada aos seis arquivos pinados e aos contratos/testes sintéticos. A evidência do autor inclui 17/17 testes de bridge e 3/3 testes de UI isolada, mais dois testes focados para flags malformadas e um teste legado. A revisão independente executou quatro verificações focadas e uma matriz adversarial separada; esses números não são uma única suíte combinada.

Flags `stale` malformadas neutralizam fatos atuais de bateria e marcam o snapshot como limitado; `hidden` malformado omite o dispositivo e também marca estado limitado. Flags ausentes preservam a compatibilidade aditiva schema 1 conforme o contrato. “Reler cache local” não coleta dados nem executa CLI. O estado deve distinguir presente, origem, leitura antiga/limitada, ausente e desconhecido.

UNRUN: cache/dataset real do usuário, daemon ou serviço, hardware, rede, painel nativo, instalação e comportamento de sessão. I1 permanece parcial; QuotaLantern ainda não tem custo tipado suportado e FalaTrace não pode afirmar liveness (permanece `false`).
