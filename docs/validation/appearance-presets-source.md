# Aparência portátil — C1/X1 Source

A aba Aparência oferece um módulo recolhível para exportar o estado salvo e importar aparência, ordem e visibilidade dos sete widgets. Colar não altera o dock; **Usar na prévia** valida o documento antes da apresentação temporária. **Aplicar** salva os dois campos juntos, **Cancelar/Escape** descarta a prévia e **Desfazer** restaura o estado anterior enquanto o perfil e sua revisão não mudarem.

O payload usa whitelist e um schema experimental separado do tema com autoria: não contém apps fixados, nome/ID de perfil, eventos, contexto, caminhos, dados de integração ou Pomodoro. A saída é selecionável para cópia manual; importação aceita texto colado. Preferências anteriores podem ser exportadas; a importação exige escolher ou criar um perfil explicitamente. O [guia](../theme-format.md) descreve os limites e o [schema](../../themes/schema/appearance-preset-0.1-experimental.schema.json).

## Verificação

No checkout integrado, 130 testes rodaram em Fusion e os mesmos 130 em `org.kde.desktop`: 129 passaram e um foi pulado em cada estilo, pois TaskManager exige conexão Wayland/X11. As suítes cobrem parser, fluxo portátil, wiring da dock, aparência, temas, perfis, widgets, Contextos, Central de Controle e eventos locais. Depois dos ajustes finais de Backtab e da margem do contorno de foco, os 38 casos afetados passaram novamente por estilo, sem skips. Os sete guards, design check sem issues e build passaram; galeria geral e capturas específicas foram revisadas em claro/escuro.

A revisão funcional independente passou 48 testes por estilo. Reproduziu cancelamentos de Aplicar e Desfazer antes da escrita; a correção impede o setter nesse caso, com zero escritas e bytes preservados. A guarda opcional de continuidade é verificada imediatamente antes da escrita gerenciada; consumidores existentes com três argumentos mantêm seu contrato. Mudanças de scope/revisão e callbacks reentrantes não confirmam uma intenção antiga nem oferecem undo para outro perfil.

Na cópia isolada do autor, a regressão ampliada rodou 174 casos por estilo, com nove skips declarados: quatro precisavam de TaskManager/display e cinco de calendário usavam o wrapper separado. Os cinco casos de calendário passaram pelo wrapper próprio nos dois estilos. A CI acrescenta somente as suítes portáteis `test_appearance_preset` e `test_appearance_preset_parser`, sem módulo KDE, conta, rede ou chamada paga.

## Capturas sintéticas

| Prévia escura | Exportação clara |
|---|---|
| ![Prévia escura](../screenshots/appearance-presets/preset-dark-preview.png) | ![Exportação clara](../screenshots/appearance-presets/preset-light-export.png) |

Capturas offscreen com dados sintéticos: prévia em 420 px e exportação em 350 px. O rodapé mantém uma única ação primária; Tab/Backtab alcançam exportação, saída, entrada e ações. Texto inválido volta ao campo para correção; rolagem revela o controle e seu contorno inteiro de foco após mudanças de layout. A revisão UI final aprovou os bytes integrados, com zero warnings no teardown. Não são capturas da sessão real.

## Limites

C1/X1 continuam parciais. Importação de arquivo, organização dos apps fixados, importação com reorder nas preferências anteriores e catálogo mantêm suas fatias próprias. Persistência KConfig, clipboard e acessibilidade nativos e o fluxo de importação real ainda não foram qualificados por estes testes offscreen.

## Canary local limitado — 2026-10-13

O commit `768697f` foi instalado na dock da sessão Plasma 6.7.5/Wayland: 66 arquivos, somente os 11 deltas esperados. Na preferência anterior, abrir a seção e usar Tab/Space em Exportar mostrou o JSON selecionável na interface real. Valores dos applets, configurações protegidas, barra, launcher e bancos permaneceram iguais; Plasma terminou ativo, sem crash ou restart automático. Os dispositivos de input próprios foram liberados.

Esse canary confirma abertura e saída visível nas preferências anteriores. Não exercitou clipboard, acessibilidade por tecnologia assistiva, foco de retorno ou Aplicar/Cancelar/Desfazer de um preset em perfil gerenciado. A evidência Source desses fluxos permanece separada.

## Encerramento das fixtures do launcher — 2026-10-13

A CI de `80d6153` passou as verificações de `launcher-behavior`, mas o processo
terminou com SIGSEGV após a suíte. Uma reprodução com o mesmo Source e as versões
da CI falhou na segunda execução. O core identificou o worker `krunner_services`
finalizando dados locais da thread após a destruição do registro global do Qt.
Destruir o objeto do runner não garantia o término dessa limpeza.

A guarda dos testes agora captura somente as threads dos runners próprios e
exige `QThread::wait` bem-sucedido antes de processar a exclusão assíncrona.
O prazo compartilhado de 500 ms foi preservado. Uma regressão com runner real
falhou na guarda anterior e passou com o join; ela observa o estado antes da
limpeza de segurança, sem transformar essa limpeza em PASS. A fixture final
também mantém seus dados vivos em retornos antecipados de assertions.

Build e sete CTests passaram no container com as dependências da CI. Após o
ajuste final da fixture, o checkout integrado com KRunner 6.30 passou build e
sete CTests em 97,17 s; o caso dirigido passou também com estilo KDE. Revisões independentes
aprovaram o join e o ajuste de lifetime. A nova CI hospedada permanece pendente.

Essa mudança é somente de testes. Não qualifica o encerramento do launcher
nativo nem explica retrospectivamente outros crashes sem core. Falhas e
recibos anteriores permanecem preservados; importação gerenciada nativa segue
UNRUN. [Contrato Qt de término da thread](https://doc.qt.io/qt-6.11/qthread.html#isFinished).
