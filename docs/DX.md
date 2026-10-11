# Experiência de desenvolvimento do Orla Desktop

> **Roadmap em execução.** Este documento descreve como tornar o Orla simples de desenvolver, testar e estender. O incremento da base é Orla Dock 0.2.2 alpha, licenciado sob MIT. Os comandos e contratos marcados como futuros são propostas; não existem SDK, runtime de plugins ou galeria no alpha.

## Objetivo

Uma pessoa contribuinte deve conseguir entender a estrutura, reproduzir um problema, alterar um módulo, validar a mudança e compartilhar um artefato sem depender de API paga, credenciais privadas ou uma instalação completa do KDE para cada ciclo. A experiência de desenvolvimento acompanha a evolução do produto: primeiro melhorar o fluxo da base atual; publicar contratos somente quando houver consumidores e compatibilidade para sustentar esses contratos.

## Fluxo disponível hoje

O repositório é um projeto pequeno de Plasma/QML com helper Python, testes QML e integração local D-Bus. A CI executa testes portáteis e empacota o applet em Ubuntu; ela não simula uma sessão Plasma nem valida Wayland, painel, escalas ou múltiplos monitores.

```bash
git clone https://github.com/caiolombello/orla-desktop.git
cd orla-desktop
python3 scripts/orla.py doctor
python3 -m unittest discover -s tests -p 'test_integrations.py' -v
python3 -m unittest discover -s tests -p 'test_package_cli.py' -v
python3 scripts/orla.py build
```

`doctor`, `build`, `install` e `uninstall` são comandos atuais do helper. Para interações QML, testes da sessão privada D-Bus ou comportamento nativo, consulte [CONTRIBUTING.md](../CONTRIBUTING.md) e [ROADMAP.md](../ROADMAP.md); esses testes exigem runtimes/ambientes específicos e não são cobertos pela CI portátil inteira. Alterações de UI precisam ser conferidas numa sessão Plasma compatível antes de afirmar que comportamento nativo está validado.

### Regras para documentação de comandos

Desde 0.2.2, `doctor` identifica PySide6.QtDBus, `busctl` e sessão D-Bus como dependências opcionais das integrações. A instalação do dock continua sem elas; restaurar as dependências e reinstalar ativa o serviço. A suíte de integração D-Bus ainda requer PySide6 e `dbus-run-session`. Veja a [validação da base](validation/foundation-0.2.2.md) para escopo e limites.

- Exemplos acima correspondem ao fluxo atual documentado; não sugerem que haja CLI para criar extensões.
- Os nomes `orla-ext create`, `orla-ext check`, `orla-ext dev` e `orla-ext pack` abaixo são **nomes candidatos para um futuro conjunto de ferramentas**. Não os executar nem documentar como se já estivessem disponíveis.
- Quando o futuro CLI for criado, manter um `--help` verificável e exemplos testados na CI. O comando de prévia deverá dizer se usa mocks ou uma sessão Plasma real.
- Uma falha de dependência deve identificar o pacote/ferramenta que falta, a funcionalidade afetada e uma maneira de seguir no modo básico.

## Organização técnica gradual

Preservar inicialmente o layout e as ferramentas existentes. Evitar introduzir monorepo, gerenciador de workspaces ou sistema de plugins de build enquanto o produto é um applet QML com helper Python e poucos alvos de pacote. Extrair módulos quando houver fronteiras e ciclos de teste claros, mantendo o build reproduzível e o desenvolvimento local simples.

| Fronteira proposta | Responsabilidade e regra de dependência |
|---|---|
| `dock/` (QML/Plasma) | Apresentação, interação e integração com APIs do Plasma. Não implementa armazenamento de segredo nem chama provedores de IA diretamente. |
| `core/commands/` (futuro) | IDs estáveis, descrição, busca e despacho tipado das ações. Consultar resultados não executa ação; comandos apontam para o adaptador que possui o estado. |
| `providers/` (futuro) | Adaptadores pequenos para KDE, MPRIS, UPower, projetos locais e provedores de IA. Falha de um adaptador não derruba outros módulos. |
| Bridge (fronteira atual; pasta futura) | Serviço local opcional e leitores de estado explicitamente suportados, hoje em `package/contents/code/`. Continua separado da UI e sem buscar tokens, conteúdo privado ou APIs online por conta própria. |
| `extension-host/` (futuro) | Processo e protocolo estreitos para extensões executáveis; valida pedidos, permissões, prazos e saída antes de entregá-los ao host. Nunca é uma importação de QML de terceiros no `plasmashell`. |
| `sdk/` e `tools/` (futuros) | Schema, exemplos, validação e empacotamento de extensões. Só aparecem após X1/X2 em [EXTENSIONS.md](EXTENSIONS.md); SDK público não expõe arquivos privados do app. |

Dependências preferenciais: interface → contratos internos → adaptador/provedor. A UI consome modelos de estado e capacidades, sem acoplar telas a caminhos de configuração ou detalhes de transporte. O bridge atual não vira um barramento genérico para extensões. Antes de mover arquivos para essas pastas, definir dono, importações permitidas e teste de contrato; reorganizar gradualmente em mudanças pequenas.

### Contratos e compatibilidade

Tratar estas versões como dimensões separadas:

| Identificador | O que versiona | Regra proposta |
|---|---|---|
| Versão do Orla/host | Aplicativo, applet e recursos integrados | Versão de produto, publicada nas releases. |
| Versão do protocolo do host | Mensagens entre host e provedor externo | Negociação explícita; campos opcionais novos podem ser ignorados; capacidade desconhecida nunca é concedida; incompatibilidade exige versão nova. |
| Versão do SDK | Tipos e ferramentas de desenvolvimento de extensões | Não derivar automaticamente do número do app. Mudança incompatível documentada com migração após estabilização pública. |
| Versão da extensão | Pacote individual e seus próprios dados/configuração | Compatibilidade declarada com intervalo do host/protocolo; upgrade não apaga configuração sem decisão explícita. |

Antes da primeira versão estável do SDK, publicar schema versionado, exemplos válidos e inválidos e fixtures de ida/volta para mensagens. Usar mudanças aditivas durante a fase experimental; rejeitar limites, tipos e capacidades que não sejam conhecidos. Nenhuma API deve ser chamada de estável sem pelo menos duas versões consumidoras no projeto e caminho de migração testado. O prazo de suporte de cada protocolo fica definido antes de estabilizá-lo.

Fixtures de contrato devem ser pequenas, legíveis e sintéticas: descoberta, pedido/resposta válida, campo adicional ignorável, capacidade ausente, timeout/cancelamento, erro seguro, saída malformada, mensagem acima do limite e incompatibilidade de versão. Reutilizar os fixtures no host e nos exemplos do SDK, evitando duplicar uma implementação que apenas confirma a si mesma.

## Ciclo de contribuição por área

### Interface QML, widgets e barra

Incluir o objetivo do usuário e estados relevantes: inicial, carregando, vazio, conteúdo longo, integração ausente, erro e recuperação. Conferir teclado/foco, Escape, leitor de tela, contraste, movimento reduzido, idioma longo e escala. Capturas de uma galeria sintética são úteis para revisão; o gate nativo continua sendo executar na sessão Plasma suportada e registrar Plasma/Qt, Wayland ou X11 e escala testada. Não usar captura com agenda, títulos de janela ou outros dados pessoais.

### Temas e presets

O checkout fonte já inclui o formato de dados `0.1-experimental`, schema, validador, empacotador e dois exemplos sem assets/código em [theme-format.md](theme-format.md). `python3 scripts/themes.py validate themes/examples/essential.json --json` confere um exemplo; `pack` cria um artefato canônico sem sobrescrever arquivos. Os testes portáteis de temas e do bundle também rodam na CI. Esta etapa não instala/aplica temas, nem conclui X1/DX2.

O consumo no dock e a futura prévia devem carregar dados fictícios e mostrar resultado antes de ativar; tema inválido deve ser rejeitado sem substituir o atual. Nenhum tema requer credencial ou serviço online. Assets locais e outros recursos só entram depois de contrato próprio; não aceitar QML/JavaScript arbitrário como tema. Consulte [EXTENSIONS.md](EXTENSIONS.md) para os gates restantes.

### Traduções e documentação

Contribuições de texto e traduções não dependem de QtDBus, KDE instalado, API ou conta. Definir catálogo e processo de extração quando o projeto adotar uma ferramenta de localização; até lá, preservar PT-BR/EN nos documentos e interface existentes. Exemplos precisam ser atualizados junto ao fluxo real, com rótulo explícito para qualquer comando ou componente futuro.

### Integrações e hardware

Usar fixtures determinísticas para estado ausente, antigo, parcial e erro. Mock provider/serviço deve implementar o mesmo contrato estreito do adaptador real. Separar teste portátil de prova real de MPRIS, UPower, calendário, Steam, Wayland ou multi-monitor. Uma contribuição que toca API do Plasma ou hardware inclui versão, sessão e dispositivo usados; ausência local não deve impedir testar a lógica sem dispositivo quando houver fixture adequada.

### IA e provedores pagos

Nenhuma contribuição comunitária ou comando da CI deve exigir chave, assinatura, crédito de API ou pedido faturável. Para desenvolver fluxo de IA, utilizar mock local gravado e rotulado; testes ao vivo são opcionais, manuais e opt-in. Não guardar respostas privadas, prompts, tokens, sessões de CLI ou dados de usuário em fixtures. Contratos de provedores são distintos do contrato do SDK de extensões; consultar [AI_INTEGRATIONS.md](AI_INTEGRATIONS.md).

## DX futuro para temas e extensões

Os comandos de referência ainda serão definidos por X2; interface sugerida para discussão:

```text
orla-ext create theme <id>       # criar exemplo mínimo de tema
orla-ext check <diretório>       # validar manifesto, schema, assets e compatibilidade
orla-ext dev <diretório>         # prévia local com mock explícito ou host de desenvolvimento
orla-ext pack <diretório>       # produzir pacote determinístico e checksum
```

Cada comando deve aceitar um caminho local explícito, validar sem executar o pacote, indicar versão de ferramenta e host usados, e retornar código de saída útil para CI. `dev` só carrega código externo quando existir o host isolado aprovado; a galeria de temas declarativos pode ser pré-visualizada sem executar código. `pack` não assina automaticamente com credencial comunitária nem incorpora arquivos pessoais. Um template público deve começar por tema e depois um provider somente de dados, com mock, contrato e testes já conectados.

Saída do validador proposta: caminho/campo, problema, valor esperado, severidade, ação corretiva e versão de schema. Validar: JSON/schema, IDs e versão, licença/autoria, intervalos de host/protocolo, lista de capacidades, tamanho e tipo de assets, caminhos dentro do pacote, entradas duplicadas, links/URLs e conteúdo executável proibido. A regra de descoberta deve ser simples; publicar qualquer comando exige documentação que diga claramente se ele somente lê dados ou executa ações.

## Isolamento obrigatório para código externo

Manifesto, lista de permissões, assinatura, hash ou processo separado não limitam capacidades por si só. Antes de habilitar plugins executáveis de terceiros, o host precisa impor o isolamento e comprovar que um pacote não acessa arquivos, rede, clipboard, sessão D-Bus ou shell fora das capacidades concedidas. Se uma instalação suportada não puder aplicar a política, não ativa código externo nessa instalação.

Critérios técnicos de saída antes do runtime executável:

- Processo externo sem privilégios adicionais, com canal IPC tipado e mensagens limitadas.
- Broker do host para cada capacidade; nenhum acesso genérico ao D-Bus, shell ou sistema de arquivos.
- Prazos, cancelamento, limite de memória/saída e isolamento da UI em falha ou processo que não responde.
- Testes adversariais para path traversal, symlinks, arquivo grande, pacote malformado, saída excessiva, URL inesperada, privilégio não concedido, revogação e atualização/rollback.
- UI hospedada pelo Orla ou componentes visuais permitidos finitos; plugin não injeta QML no processo do dock.
- Desativar e remover encerra o processo e as concessões correspondentes; logs redigidos não contêm credenciais ou conteúdo privado.
- Provas repetíveis em cada ambiente declarado como compatível e revisão independente da fronteira de confiança.

Até que esses itens sejam demonstrados em sessão suportada, contribuições executáveis são propostas para revisão do núcleo e não pacotes ativáveis pela galeria.

## Contribuição aberta e addons

O fluxo deve reconhecer trabalho em bugs, acessibilidade, documentação, tradução, temas e testes sem custo de API ou hardware específico. Um bom pedido inclui escopo, comportamento visível, critério de aceite, dependências e como validar; issues não devem assumir datas nem criar promessa de merge. RFCs ficam para mudanças de contrato, permissões, marketplace, identidade visual ou compatibilidade que exijam decisão do mantenedor. Manter etiquetas claras para primeiro passo, área, ambiente necessário e estado de triagem; não anunciar SLA de revisão enquanto não houver capacidade acordada.

Cada contribuição mantém autoria e licencia explicitamente assets/código redistribuídos. A licença MIT do core não transfere direitos sobre assets de terceiros. Um addon pode ser gratuito ou comercial sob licença escolhida pelo autor, desde que declare origem, compatibilidade, dependências, licença e permissões. Primeiro, autores podem publicar e vender addons por canais próprios; isso não significa que o Orla processe pagamento, verifique a transação, dê suporte comercial ou ofereça uma loja. Catálogo com checkout só depois de decidir operação, moderação, revogação, responsabilidade e suporte.

Métricas de DX começam por uma baseline observada, não por metas inventadas: tempo de clone até primeiro teste verde; proporção de contribuições que passam validação antes da revisão; tempo até primeiro tema em prévia; problemas de ambiente sem reprodução; testes que exigem Plasma real; falhas por incompatibilidade de contrato; retorno após instrução de erro. Não coletar telemetria de desenvolvedor por padrão. Na fase de piloto, colher medições voluntárias e revisar quais fricções impedem contribuições.

## Etapas DX

| Etapa | Entrega | Dependências | Critério de saída |
|---|---|---|---|
| **DX0 — alpha compreensível** | Documentar e manter sincronizados comandos atuais, dependências, limites da CI, contribuição e triagem | Estado atual 0.2.1 | Pessoa nova reproduz os testes portáteis e o build usando somente docs existentes; comandos listados coincidem com o helper e a CI. |
| **DX1 — contratos internos testáveis** | Inventariar fronteiras do applet, bridge e adaptadores; adicionar fixtures sintéticas e erros reproduzíveis | DX0; passos iniciais de arquitetura no ROADMAP | Falhas de integração podem ser testadas sem serviço/conta; cada interface interna tem owner, dependências e teste correspondente. |
| **DX2 — galeria e tema declarativo** | Especificar schema versionado, validador, template, prévia mock/offline e exemplos gratuitos | Tema/manifesto em X1/X2 de EXTENSIONS; DX1 | Contribuidor cria, confere e pré-visualiza tema sem executar código nem usar sessão de IA; CI testa fixtures válidas/inválidas. |
| **DX3 — kit de contribuidor** | Comandos `create/check/dev/pack`, exemplos e guia gerado do schema | DX2 e necessidade demonstrada pelos primeiros temas | Instruções se mantêm testáveis; pacote determinístico; erro aponta correção; galeria declara quando uma sessão Plasma é necessária. |
| **DX4 — SDK e provedores compatíveis** | Publicar contrato experimental para dados/ações, mocks e matriz host/protocolo/SDK/extensão | DX1; consumidor real no núcleo; decisões de API em EXTENSIONS | Fixtures/consumidores internos validam contrato e migração. Exemplo executável de terceiro só roda, inclusive em preview, após isolamento comprovado em X5; dados tipados não substituem esse gate. |
| **DX5 — runtime/comunidade ampliada** | Ferramentas de isolamento, compatibilidade automatizada, ciclo de revisão, releases e canais de addon | DX4; prova de segurança; mantenedores e política operacional definidos | Testes de abuso/isolation passam nas plataformas anunciadas; desativação/revogação/rollback demonstrados; addon comercial não depende de serviço de pagamento do core. |

As fases são gates de saída, não datas. DX1 pode ocorrer junto das correções de base do roadmap; DX2 precede publicação de ferramentas de autoria; DX4 depende de um contrato usado e mantido pelo próprio produto; DX5 não começa só porque existe interesse em plugins pagos.

## Medição e prontidão

O alpha permite testar o fluxo portátil documentado; não prova simplicidade para novos contribuidores, a UX da galeria ou isolamento de extensões. Registrar primeiro uma baseline qualitativa e voluntária com contribuições guiadas. Critério para declarar DX2 utilizável: pelo menos uma pessoa fora do núcleo consegue seguir o guia, pré-visualizar um tema sintético e interpretar erros do validador; corrigir a documentação a partir das dificuldades observadas. Não confundir aceitação de um PR com eficácia do processo.

**Prontidão:** DX0 está pronto para execução e parcialmente presente na documentação atual; sua atualização deve ocorrer junto às mudanças reais dos comandos. DX1 pode começar após mapear um primeiro adaptador/contrato e fixtures. DX2–DX5 estão definidos como roadmap, mas dependem dos schemas, consumidor, isolamento, política de manutenção e evidência de uso descritos acima.
