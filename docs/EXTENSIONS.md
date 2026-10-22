# Extensões, temas e integrações de IA

> **Ecossistema em construção.** Há um núcleo experimental para complementos JSON de bateria, com schemas, CLI e serviço próprio. Sua interface e distribuição ainda estão em integração. SDK estável, execução de plugins de terceiros e loja continuam futuros. Os demais contratos propostos abaixo não são APIs publicadas.

## Objetivo

Fazer do Orla uma plataforma que a comunidade possa personalizar e ampliar sem exigir que cada contribuição seja aceita no núcleo. Usuários devem encontrar, experimentar, configurar e remover extensões com clareza. Autores devem conseguir criar, testar e publicar um tema ou integração sem conhecer toda a base do dock.

O caminho proposto começa por conteúdo declarativo simples e componentes de interface controlados pelo Orla. Código de terceiros só entra depois de existir um host isolado, permissões verificáveis, contrato versionado e uma experiência clara de revogação e recuperação. A prévia pode usar contrato experimental explicitamente identificado; oferta comercial de compatibilidade exige API estável e política de suporte.


QuotaLantern, PeriGauge, FalaTrace e outros projetos específicos serão plugins opcionais do catálogo. Nenhum será requisito ou widget padrão do Orla. A fundação atual desliga esses widgets por padrão e exige `install --with-integrations` para registrar os adaptadores experimentais incluídos. Extraí-los em pacotes externos, oferecer busca/instalação no catálogo e permitir distribuição gratuita ou comercial ainda são próximos marcos; não há marketplace implementado.

Na aba **Widgets**, cada adaptador local oferece **Sobre** com finalidade, estado e requisitos. Abrir esses detalhes não ativa o widget, relê cache ou instala serviços; o checkbox existente continua salvando a visibilidade no perfil atual. A dock pede à ponte experimental somente os caches dos módulos visíveis no perfil/contexto atual. Ocultar um módulo limpa seus dados e invalida respostas pendentes; uma leitura já enviada pode terminar, mas seu resultado é descartado. Com todos desligados, a dock não inicia a ponte. Os detalhes não são um catálogo de plugins externos nem certificam que o aplicativo ou coletor esteja instalado/ativo. O FalaTrace mostra apenas estado salvo, sem verificar captura ao vivo.

## Contrato experimental de leitura local

O consumidor é a dock e o opt-in continua sendo a visibilidade efetiva do widget.
A interface `org.caiodock.Integrations1`, no serviço e caminho já existentes,
ganha `SnapshotFor(as) → s`: uma lista de até três IDs únicos entre `quota`,
`peripherals` e `recording`. A resposta JSON tem `schemaVersion: 2`, `modules`
na ordem canônica acima e somente os objetos pedidos. Lista vazia lê nenhum
cache; seleção inválida devolve `{"schemaVersion":2,"error":"invalid-modules"}`
antes de qualquer leitura. O ID não pode selecionar caminhos arbitrários.

`Snapshot()` e `--snapshot` preservam o schema 1 completo para consumidores
anteriores. A dock nova não usa fallback para essa chamada: ponte antiga ou
indisponível produz estado neutro e uma orientação de atualização. Isso é uma
garantia de consumo da dock, não uma permissão de acesso que impeça outros
clientes locais de chamar a interface legada. Os campos continuam sendo cache,
sem atestar instalação, processo ativo ou coleta ao vivo.

A seleção é eventual: mudanças limpam a apresentação imediatamente; há no máximo
uma chamada em voo, e a seleção mais recente é enviada depois que ela termina.
Gerações distintas descartam sucesso e erro antigos, inclusive voltar ao mesmo
perfil. O estado portátil e o transporte KDE são separados para testar essas
transições sem contas, rede, hardware ou serviços pessoais. A serialização de
`QStringList` segue o [sistema de tipos Qt D-Bus 6.11](https://doc.qt.io/qt-6.11/qdbustypesystem.html)
e também é verificada em barramento privado.

## Categorias de contribuição

| Categoria | O que pode oferecer | Forma inicial proposta |
| --- | --- | --- |
| Tema | Cores, dimensões, cantos, sombras e estados visuais | Tokens declarativos validados; sem QML ou JavaScript |
| Preset de layout | Ordem e visibilidade de itens nativos, dock/barra e atalhos | Dados declarativos que referenciam recursos já instalados |
| Widget de dados | Ex.: agenda, bateria, quota ou agora tocando | Contrato de dados + interface renderizada pelo Orla |
| Ação/integração | Ex.: abrir projeto, consultar serviço ou controlar mídia | Comando em processo separado, limitado pela API do host |
| Componente visual avançado | Interface totalmente própria | Futuro e sujeito a runtime, sandbox e revisão de segurança |

Temas e presets devem ser seguros para importar mesmo que venham de uma fonte desconhecida. Não aceitar fontes, JavaScript, expressões, HTML ou componentes QML executáveis nesses pacotes. Para cobrir novos casos visuais, ampliar primeiro os componentes e tokens renderizados pelo próprio Orla.

## Experiência que a plataforma deve oferecer

### Para quem usa

- Personalização acessível dentro das configurações: prévia ao vivo, comparar com o atual, aplicar, desfazer e restaurar o padrão.
- Busca e filtros simples por tipo, compatibilidade, idioma e estado; páginas com capturas reais, descrição, autor, licença, versão, permissões e origem.
- Mostrar diferenças entre o pacote instalado e a versão disponível. Atualização, voltar à versão anterior, desativar e remover devem ser ações claras.
- Antes de instalar código, mostrar permissões e o efeito em linguagem simples; nenhuma instalação deve pedir segredo de API em uma página de catálogo.
- Se uma extensão falhar, desativá-la sem derrubar o dock, exibir um diagnóstico curto e oferecer abrir logs redigidos. Preservar configurações do usuário ao atualizar ou remover.
- Preferências por monitor, perfil e ambiente só aparecem onde o conceito se aplica. Usar linguagem consistente, navegação por teclado, alvos confortáveis e contraste acessível.

### Para quem contribui

- Repositório-modelo com tema ou provedor de exemplo, arquivos pequenos e exemplos executáveis por contrato, não por APIs internas.
- Comandos documentados para validar, pré-visualizar com dados fictícios, empacotar e verificar manifesto. Erros de validação indicam campo, problema e correção provável.
- SDK pequeno e tipado, documentação de referência gerada do schema e exemplos PT/EN. Mudanças de API têm notas de migração.
- Testes de compatibilidade e acessibilidade da interface hospedada, tempo limite/cancelamento, falha do processo e instalação/remoção limpa.
- Catálogo de exemplos gratuitos de qualidade para reduzir a barreira de entrada; nenhum pagamento é necessário para contribuir.

## Fronteira de confiança

Uma declaração de permissões no manifesto é consentimento e informação para o usuário; sozinha **não** limita o que um processo pode fazer. O isolamento precisa ser imposto pelo host e pelo sistema operacional. Um plugin com acesso irrestrito ao barramento D-Bus do usuário pode agir com os privilégios desse usuário. Um PID, processo separado, manifesto ou assinatura identificam ou descrevem um pacote; não provam sandbox.

1. **Temas e presets declarativos:** dados estritos, limite de tamanho e de profundidade, chaves permitidas, valores e assets validados. Sem carregar código. Bloquear referências a caminhos fora do pacote, symlinks, caminhos de extração inseguros, pacotes excessivos e assets com scripts ou referências externas. Definir formatos permitidos e validação específica antes de aceitar SVG ou outros formatos compostos.
2. **Widgets e ações da comunidade:** executar fora do processo do Plasma/Orla, por um protocolo estreito host↔provedor. O host controla a apresentação e entrega apenas as capacidades aprovadas. O provedor não pode injetar QML na interface do dock.
3. **Código visual arbitrário, scripts e plugins nativos:** não habilitar inicialmente. QML pode acessar módulos nativos, recursos de processo e APIs da aplicação; empacotá-lo como “tema” ou rodar outro PID não o torna seguro. Considerar essa classe apenas após validação de isolamento, atualizações e recuperação em sistemas suportados.

Antes de chamar uma extensão externa: verificar esquema e limites de tamanho; impor prazo, cancelamento, limite de chamadas e de memória; tratar saída como dado, escapar texto e recusar URLs/esquemas inesperados. Uma extensão não deve bloquear o thread de UI. Logs locais precisam omitir tokens, conteúdo privado, dados de calendário e prompts por padrão.

Permissões possíveis para desenhar o contrato, ainda não implementado:

| Permissão proposta | Escopo que o host deve impor |
| --- | --- |
| `network` | Sem rede por padrão; declaração de hosts/protocolos permitidos e escolha explícita do usuário |
| `calendar.read` | Ler somente eventos exigidos por uma função habilitada, por integração do host |
| `media.control` | Ações de mídia aprovadas pelo usuário, sem leitura de arquivos arbitrários |
| `files.read` / `files.write` | Pastas escolhidas por seletor do sistema; escrita restrita à pasta autorizada |
| `clipboard.read` / `clipboard.write` | Apenas durante ação explícita e com indicação visível |
| `notifications` | Solicitar notificações próprias; não substituir o servidor de notificações do Plasma |
| `launcher.commands` | Registrar comandos nomeados; confirmação para ações destrutivas ou externas |
| `ai.provider` | Invocar provedor escolhido pelo usuário; nunca receber token bruto do host |

Pedir cada permissão quando a funcionalidade é habilitada, explicar a finalidade, permitir revogar e registrar o estado. Não criar permissão genérica `system`, `shell`, `dbus` ou `all`. Se uma função necessária não puder ser limitada em uma instalação suportada, marcá-la como não disponível, em vez de fingir que foi isolada.

## IA e provedores do usuário

O Orla deve oferecer um ponto de entrada opcional para ações assistidas por IA, como resumir a agenda selecionada, explicar um indicador, abrir um projeto ou sugerir comandos. A IA não é requisito do dock e permanece desligada até o usuário escolher um provedor e uma ação. Cada chamada mostra destino e dados enviados; acesso ao desktop exige confirmação específica.

Para a sequência específica de provedores, produtos e capacidades de IA, consulte o [roadmap de integrações de IA](AI_INTEGRATIONS.md). Esta proposta cobre a fronteira entre adaptadores e extensões de terceiros; ela não substitui aquele roadmap.

### Caminho de integração

1. **API configurada pelo usuário:** suportar uma interface de provedor com endpoint/modelo compatíveis, segredo guardado pelo host no cofre do sistema disponível (por exemplo, KWallet), botão de apagar e teste sem enviar dados da área de trabalho. Se o cofre não existir, não gravar segredo em texto puro; orientar o usuário.
2. **CLI já instalado:** detectar executáveis e versões de Codex CLI, Claude Code, OpenCode e ferramentas futuras somente para apresentar disponibilidade. Invocar apenas comandos e formatos documentados pelo fornecedor, sem ler arquivos de sessão, tokens, banco de histórico ou estado privado interno. O usuário escolhe e autoriza cada integração. O fluxo oficial [Sign in with ChatGPT para apps open source](https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt) pode ser um adaptador nativo do Orla quando o uso, o projeto e o plano do usuário forem elegíveis; a permissão de uso do plano é condicional e não dá acesso às conversas. Não inferir elegibilidade nem automatizar login. No caso do Claude Code, a integração planejada é abrir o binário/terminal oficial; não tratar assinatura Claude como API para automação embutida. A [documentação do Claude Code](https://docs.anthropic.com/en/docs/claude-code/getting-started) distingue login via Console e login por plano Claude; o Orla não reaproveita credenciais desses fluxos.
3. **Adaptadores internos do Orla:** APIs de provedores selecionados podem ser integradas como recursos nativos depois de definir cofre e contrato de credenciais; isso não depende do runtime de plugins. Para assinaturas, usar somente fluxo oficial documentado e elegível, sem copiar credenciais de sessão nem contornar login ou cobrança.
4. **Adaptadores de IA de terceiros:** só quando existir o runtime isolado e a permissão `ai.provider` realmente imposta pelo host. Não fazer engenharia reversa de autenticação de assinatura nem reutilizar credenciais fora de mecanismos suportados pelo fornecedor.

Assinatura ou sessão num produto CLI não significa autorização para automatizar outro cliente. Respeitar termos e APIs documentados por cada fornecedor; quando não houver interface suportada, oferecer o CLI ao usuário sem extrair suas credenciais. Credenciais nunca vão para plugins, prompts de catálogo, telemetria, logs, argumentos de linha de comando ou manifestos.

### Controles de produto para IA

- Escolha de provedor, modelo e escopo por ação; botão para desconectar e apagar credenciais.
- Mostrar uma prévia dos dados a enviar. Agenda, clipboard, arquivos, nome de usuário, projetos locais e conteúdo de janelas ficam excluídos por padrão.
- Ações externas, execução de comandos, gravação de arquivos, enviar mensagens e controlar a sessão exigem revisão humana clara antes de acontecer.
- Limites de contexto, custo/uso quando informado pelo provedor, tempo limite, cancelar, erros compreensíveis e modo sem rede.
- Respostas do modelo são conteúdo não confiável: não executá-las como shell, QML, JavaScript ou chamadas D-Bus. Converter para ações tipadas, conferir permissões e pedir confirmação conforme o efeito.
- Sem telemetria de prompts por padrão. Se for considerada uma opção de diagnóstico, documentar conteúdo, destino, retenção e desligamento; não ligar silenciosamente.

## Complementos de bateria — núcleo experimental disponível

O formato `0.1-experimental` aceita somente metadados e uma fonte de dados
normalizados. O renderer é `peripheral-battery`; a apresentação pertence ao
Orla. O pacote não pode fornecer comandos, scripts, QML, JavaScript, caminhos
de entrada ou ícones remotos. Sua origem, autoria e licença são declarações;
o SHA-256 verifica os bytes aprovados, sem autenticar o publicador.

Os contratos atuais estão nos schemas de [manifesto](../addons/schema/manifest-0.1.schema.json)
e [leituras](../addons/schema/peripherals-0.1.schema.json). O parser do host
também aplica limites de bytes/profundidade, rejeita chaves repetidas e confere
relações entre campos que o schema sozinho não expressa. O
[exemplo sintético](../addons/fixtures/peripherals-0.1.json) não é uma leitura
de hardware nem um complemento instalado por padrão.

No checkout, a CLI de desenvolvimento permite inspecionar e empacotar um
manifesto local. Substitua os caminhos pelos seus; os diretórios de saída
devem ser absolutos. `pack` não sobrescreve um arquivo existente.

```sh
python3 scripts/addons.py inspect file:///caminho/complemento.json
python3 scripts/addons.py pack file:///caminho/complemento.json --output /caminho/dist
python3 scripts/addons.py list
```

Instalar usa o SHA-256 dos **bytes exatos** mostrado por `inspect`. Um arquivo
reformatado precisa de nova inspeção. Nos exemplos seguintes, substitua
`SHA256_APROVADO` pelo digest completo de 64 caracteres e o ID pelo ID real:

```sh
python3 scripts/addons.py install file:///caminho/complemento.json --expected-sha256 SHA256_APROVADO
python3 scripts/addons.py enable org.exemplo.bateria --expected-current-sha256 SHA256_APROVADO
python3 scripts/addons.py disable org.exemplo.bateria --expected-current-sha256 SHA256_APROVADO
python3 scripts/addons.py rollback org.exemplo.bateria --expected-current-sha256 SHA256_APROVADO
python3 scripts/addons.py remove org.exemplo.bateria --expected-current-sha256 SHA256_APROVADO
```

Cada linha é uma operação independente. Depois de atualizar ou voltar uma
versão, consulte `list` para obter o digest atual antes da próxima operação.
Rollback exige uma versão anterior retida.
Instalação, atualização e rollback deixam o complemento desativado. Ativação
exige aprovação separada do pacote atual; só um provedor de bateria pode ficar
ativado. A visibilidade no perfil e o compartilhamento autorizado no aplicativo
produtor são escolhas adicionais. Nenhum desses comandos inicia o produtor.

O namespace do manifesto determina somente
`$XDG_STATE_HOME/<namespace>/exports/orla-peripherals-v1.json`, com o fallback
XDG habitual. Orla não consulta caches privados do produtor por esse contrato.
As leituras têm prazos de validade explícitos, sem nomes, aliases ou IDs de
hardware. Percentual zero, nível aproximado, estimativa, ausência e observação
antiga permanecem distintos. `snapshot` permite conferir a projeção passiva
pela CLI depois de uma ativação explícita.

O armazenamento em `$XDG_DATA_HOME/orla-desktop/addons` preserva preferências
ao remover um pacote. Esta versão limita o registro a 32 IDs e retém até
128 arquivos/8 MiB; remover não libera automaticamente essa capacidade.
Uma falha de publicação pode deixar um arquivo desconhecido e bloquear o
registro até recuperação explícita. Não há adoção ou reparo automático.
Uma falha com `committed: true` exige reler o estado. No transporte do serviço,
`null` indica resultado desconhecido e também exige releitura. Não repetir uma
mutação automaticamente. As recusas da CLI usam códigos finitos; uma falha
depois da publicação não promete que a operação foi desfeita.

O serviço `org.orla.Addons` é separado da ponte legada. Seus métodos retornam
JSON em uma string, com prazo e worker pertencente ao host. O núcleo passou
por [testes privados e chamadas reais em barramento isolado](validation/addon-host-core.md); isso não qualifica
a instalação na sessão do usuário, a interface completa ou a coleta real do
produtor. O fluxo nas configurações, a extração do PeriGauge e sua validação
local continuam em integração. QuotaLantern e FalaTrace mantêm o caminho
experimental opcional descrito acima.

## SDK de execução de provedores — proposta, não API publicada

Esta proposta futura não é o formato de complemento JSON descrito acima.

Manter o primeiro contrato reduzido: metadados, lista de capacidades solicitadas, contribuição de dados e ações tipadas. O host é dono do ciclo de vida, UI, configuração e permissões. Não exportar objetos Qt, componentes internos, paths de configuração ou chamadas D-Bus privadas.

Todo pedido/resposta deve ter `apiVersion`, `requestId`, tipo e payload validado contra um schema versionado. Listas e strings têm limites. Erros são códigos estáveis com mensagem segura para apresentar; detalhes técnicos ficam nos logs redigidos. Eventos não podem crescer sem limite. Pedidos assíncronos aceitam cancelamento e prazo; atualização do dock encerra/renegocia a conexão ordenadamente.

Exemplo apenas conceitual (não consumir como schema válido):

```json
{
  "schemaVersion": 1,
  "id": "community.example.agenda",
  "version": "0.1.0",
  "type": "data-provider",
  "name": "Agenda compacta",
  "api": { "min": 1, "max": 1 },
  "license": "MIT",
  "permissions": ["calendar.read"],
  "entry": "provider"
}
```

Os campos são hipótese para discussão. Antes de disponibilizar SDK público, publicar JSON Schema e contratos de protocolo, definir compatibilidade por versão, validação rigorosa, limite de mensagens e testes de ida/volta. Marcar cada contrato como experimental até seus próprios gates de estabilidade; a versão do SDK/formato não deriva da versão do aplicativo. Um formato declarativo pode estabilizar antes do runtime de plugins. Evitar anunciar compatibilidade estável para um contrato ainda experimental.

## Empacotamento, distribuição e remuneração

### Distribuição gradual

1. **Desenvolvimento local:** instalar pacote da pasta de trabalho com modo de desenvolvedor claramente indicado. Ficar visível onde está o código e como desativar/remover.
2. **Repositório público:** começar com repositórios externos e arquivos compactados com manifesto, hash, versão e instruções. A instalação exibe a origem e permite revisão antes de ativar.
3. **Catálogo do Orla:** somente após política de revisão, moderação e remoção; compatibilidade automática, hashes verificados, histórico/revogação e update/rollback testados.
4. **KNewStuff/KDE Store:** avaliar como canal para conteúdo declarativo depois de validar o fluxo com KF6 e a categoria adequada. KNewStuff oferece mecanismo de descoberta e transferência, mas não substitui validação do formato, sandbox, autenticidade do autor ou política do Orla. Não presumir que um botão “baixar” torna extensões confiáveis.

Assinar um pacote ajuda a verificar que veio do titular de uma chave conhecida e não foi alterado; não demonstra que o código é seguro. Verificação inicial também deve validar hash, versão, licença declarada, limites do manifesto e origem. Manter allow/deny local, botão para desativar, rollback e mecanismo de revogação de versão maliciosa. Assinatura/revogação ainda exigem desenho de chaves e operação antes de existir catálogo central.

### Extensões gratuitas e pagas

O projeto pode permitir que autores ofereçam add-ons gratuitos ou pagos, inclusive fora de um catálogo central, após estabelecer contrato e política. Um tema simples, um provedor aberto e uma extensão comercial não têm o mesmo risco ou custo de suporte.

- A licença do Orla cobre o núcleo conforme o arquivo LICENSE; ela não concede automaticamente uma licença a temas, ícones, fontes, modelos, dados ou integrações submetidos por terceiros. Cada contribuição informa sua própria licença e autoria.
- Não exigir que código pago seja aberto para ser compatível com o host; exigir metadados/licença para redistribuição e distribuição no catálogo. O formato de extensão, dependências e componentes vinculados precisam de análise técnica e de licença antes de aceitar binários fechados.
- Primeiro validar links externos, download direto pelo autor, metadados de preço e compatibilidade. O projeto não processa pagamento nem promete reembolso nessa etapa.
- Loja própria, cobrança, comissão, entrega de licença, reembolsos, impostos, fraudes, suporte e proteção de conteúdo são decisões futuras. Definir responsabilidades, termos e jurisdição com assessoria adequada antes de abrir pagamentos pelo projeto.
- A classificação “destaque” deve revelar critério e não ser comprada sem rótulo. Favoritos e avaliações são sinais, não garantia de segurança ou qualidade.

## Etapas propostas

| Fase | Entrega | Critério de saída |
| --- | --- | --- |
| **X0 — 0.4: personalização nativa** | Melhorar editor visual, presets embutidos, prévia, acessibilidade e recuperação das preferências | Navegação por teclado; mudança ao vivo reversível; preferências por tela/perfil testadas; nenhuma configuração existente perdida |
| **X1 — 0.4–0.5: temas de dados** | Schema e ferramenta de validação para tokens visuais sem código | Corpus de inválidos e válidos; importação com limites; tema inválido não quebra configuração nem painel; screenshot/preview com acessibilidade |
| **X2 — 0.4–0.5: SDK de conteúdo** | Template, CLI de validar/preview/empacotar e tema comunitário de exemplo | Uma pessoa nova cria e depura tema seguindo guia; contrato publicado como experimental e teste no Plasma suportado |
| **X3 — 0.6–0.7: distribuição de temas** | Instalação/atualização/rollback de temas e presets, inicialmente de URL/repositório indicado pelo usuário | Hash conferido; origem e licença visíveis; sem execução; remoção não apaga personalização do usuário |
| **X4 — 0.7: UI de widgets hospedada** | Catálogo finito de blocos nativos; adaptadores internos/mocks enviam dados tipados | Renderização e estado sob controle do host; entradas malformadas e fonte lenta não travam a UI. Executar provedor comunitário, mesmo somente de dados, depende de X5 |
| **X5 — prévia 0.9+: ações e plugins executáveis de terceiros** | API versionada, host RPC, processo separado, timeout/cancelamento e permissões aprovadas | Sandbox comprovada nos sistemas suportados; testes de abuso e isolamento; atualização/rollback; nenhuma trava ou ação além da autorização |
| **X6 — conforme roadmap de IA** | Adaptadores nativos do Orla por API e CLIs suportadas, com consentimento, cofre e saída tipada | Segredos persistidos somente no cofre seguro, fora de exportações/log/argv; desativação e exclusão testadas; nenhum dado local enviado sem prévia e escolha. Segue o roadmap independente de IA e não aguarda X5 |
| **X7 — a partir de 0.7 para temas; código pago após SDK estável e X5** | Contribuições e venda por terceiros; pagamento do projeto continua uma decisão separada e futura | Para temas: formato de dados estável, origem/licença visíveis e remoção/rollback. Para código executável: SDK estável, gates de X5 e política de catálogo. Não bloquear contribuições gratuitas à espera de loja própria |

X0 faz parte da personalização prevista para 0.4; X1/X2 acompanham a definição de temas de dados em 0.4–0.5. X2 exige X1. X3 pode começar em 0.6–0.7 depois da verificação de pacotes e reversão. X4 entra em 0.7 com adaptadores internos/mocks, depois de validar o formato e a fronteira de dados; não habilita execução de terceiros antes de X5. X5 começa como prévia em 0.9 ou depois, somente após revisão de segurança e prova real de isolamento. X6 é uma trilha independente: integrações nativas do Orla precisam do cofre e contrato A0/A1 do roadmap de IA, mas não precisam esperar o runtime de plugins X5. Adaptadores de terceiros, ao contrário, exigem X5. Contribuições gratuitas e venda externa de temas simples podem surgir depois que o formato declarativo ficar estável; extensões comerciais executáveis dependem do SDK estável e X5. Uma loja de pagamentos do projeto não é pré-requisito para a comunidade crescer.

Não atribuir datas antes de medir o tamanho do runtime e provar isolamento no KDE/Wayland real. Se o sandbox não estiver disponível ou não puder restringir rede, arquivos e barramento, manter ativa somente a classe declarativa e adiar extensões com código.

## Pronto para convidar terceiros

- [ ] Especificação do manifesto e dos dados fechada, marcada por versão e compatibilidade.
- [ ] Nomes, categorias e permissões correspondem ao que o host realmente impõe.
- [ ] SDK de exemplo permite desenvolver sem dependências internas do Orla.
- [ ] Instalação, atualização, rollback, desativação, revogação e desinstalação funcionam no KDE limpo.
- [ ] Diagnóstico ajuda sem expor prompts, tokens, eventos privados ou caminhos desnecessários.
- [ ] Processo de contribuição cobre autoria, licença, localização, acessibilidade, revisão e manutenção.
- [ ] Casos de abuso, indisponibilidade e crash foram exercitados; ameaças e limites conhecidos estão publicados.

## Fontes técnicas para reavaliar durante a implementação

- [KNewStuff `EngineBase` (KDE API)](https://api.kde.org/knscore-enginebase.html) e [KDE Get Hot New Stuff](https://develop.kde.org/docs/administration/kiosk/keys/#ghns): referência de catálogo/transferência e conteúdo KDE. Confirmar APIs e requisitos na versão KF6 usada pelo projeto.
- [Qt Quick Modules](https://doc.qt.io/qt-6/qtqml-modules-topic.html), [Deploying Plugins](https://doc.qt.io/qt-6/deployment-plugins.html) e [Qt Shared Security Model](https://doc.qt.io/qt-6/shared-security-model.html): módulos carregam tipos, recursos e plugins nativos; confiar em QML não equivale a executar dados passivos. Conferir a versão Qt suportada pelo Orla antes de implementar.
- [XDG Desktop Portals](https://flatpak.github.io/xdg-desktop-portal/docs/): interfaces mediadas para recursos como arquivos e abertura de URI; considerar quando o acesso puder passar pelo portal apropriado.
- [OpenAI Sign in with ChatGPT para apps open source](https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt): referência atual ao fluxo oficial de OAuth e uso condicional de plano em projetos elegíveis; validar as condições e a API disponível antes de implementar.
- [Claude Code: instalação e autenticação](https://docs.anthropic.com/en/docs/claude-code/getting-started): referência às opções oficiais de login do Claude Code. A integração proposta pelo Orla limita-se a abrir o binário/terminal oficial.
- [Bubblewrap README](https://github.com/containers/bubblewrap/blob/main/README.md): ferramenta de baixo nível para montar namespaces e filesystem restrito, não sandbox pronta nem solução automática para permissões do Plasma. Uma integração exigiria política explícita de mounts, barramento, rede, ambiente, dependências e fallback.

Essas fontes orientam experimentos; não comprovam que a arquitetura já foi construída, que toda distribuição oferece o mesmo isolamento ou que uma extensão é confiável.
