# Contexts / Contextos

## Português

A prerelease alpha [0.2.8](https://github.com/caiolombello/orla-desktop/releases/tag/v0.2.8) adicionou associações explícitas na aba **Contextos**. O Source atual acrescenta perfis automáticos opcionais, ainda sem release. A versão do commit `c5509a1` foi instalada numa sessão KDE/Wayland e passou uma visita sem edição à aba, com o automático desligado; veja a [validação delimitada](validation/contexts-auto-installed.md). Essa prova não qualifica a automação ligada, sua persistência após reinício ou o foco/seat completo. Os testes Qt sintéticos continuam separados dessas provas nativas.

A aba observa Activity e área virtual em cartões separados. Escolha um perfil gerenciado e use **Associar Activity atual** ou **Associar área atual**; **Remover** elimina apenas a associação atual. Navegar nesses seletores não grava. Associar não ativa o modo automático nem troca a Activity/área do KDE.

A descoberta é somente leitura. Com o automático desligado, continua carregada apenas enquanto a aba Contextos está aberta. Com ele habilitado e as preferências válidas, permanece ativa fora das configurações. O backend separado que escreve a área de trabalho continua exclusivo do comando explícito **Trocar área**. Overrides de teste impedem a descoberta nativa.

### Perfis automáticos (Source experimental)

1. Crie perfis na aba **Perfis**. Em **Contextos**, escolha um **Perfil padrão** gerenciado existente; isso salva só essa preferência e não ativa o modo.
2. Em **Usar no automático**, mantenha **Activity e áreas** para usar Activity associada → área associada → padrão, aguardando os dois contextos. Escolha **Somente áreas** para usar área associada → padrão, mesmo sem Activity disponível. Isso salva só a base da regra; não ativa o automático e preserva as associações de Activity.
3. Marque **Trocar o perfil automaticamente**. O modo começa desligado por instância da dock e exige perfis e associações válidos. Os contextos exigidos pela opção escolhida devem estar prontos, com IDs atuais nas listas normalizadas. Uma associação usada pela regra a um perfil ausente pausa a troca; não cai silenciosamente no padrão. Carregamento ou indisponibilidade do contexto exigido mantém o perfil atual.
4. Escolher/criar um perfil manualmente prevalece até mudar o ID de um contexto exigido, **Retomar automático agora** ou escolher outra base da regra. Uma escolha manual feita depois da mudança de base continua valendo. Se ainda não havia contexto confirmado, o primeiro contexto recebido mantém essa escolha; um ID diferente recebido depois pode liberá-la. Renomeação, reconexão no mesmo ID e alteração do padrão/associações não desfazem a seleção manual. Em **Somente áreas**, mudanças de Activity também não a desfazem. O override é da sessão: ao reiniciar com o modo habilitado, o automático retoma quando receber os contextos exigidos. Restaurar o perfil salvo na inicialização não conta como uma nova escolha manual; uma seleção real feita depois continua prevalecendo.
5. Edições, arrastes, rolagem, popups, transferência da Central e pedidos/gestos de áudio adiam a troca. A automação não fecha, cancela ou aplica uma edição para prosseguir. Ao liberar, recalcula somente o contexto mais recente. Desativar mantém o perfil atual.

Se o KDE não informar uma Activity atual, **Activity e áreas** aguarda mesmo quando a área virtual está disponível. **Somente áreas** ignora Activity por escolha explícita, inclusive durante uma falha desse serviço; não tenta distinguir ausência de falha. O status identifica os contextos exigidos indisponíveis e distingue carregamento. O [diagnóstico nativo anterior](validation/contexts-auto-installed.md#enabled-host-diagnosis-and-accessible-tabs) registra a espera do modo combinado sem criar ou ativar uma Activity na sessão.

As opções do modo são globais entre os perfis desta dock e salvas imediatamente em `autoContextEnabled`, `autoContextDefaultProfile` e `autoContextPolicy`; Cancelar aparência não as desfaz. Mudar a base da regra retoma o automático após terminar a interação, inclusive fechar as configurações; uma escolha manual mais recente prevalece. A política começa em `activity-desktop`; a alternativa é `desktop`. Valor desconhecido fica preservado, pausa o automático e aparece sem opção selecionada para permitir uma escolha válida. O modo não troca Activity, área, monitor, janelas, barra ou launcher. O Pomodoro continua no mesmo objeto/prazo. Comportamento por monitor e a jornada completa no painel do usuário permanecem abertos.

As associações usam identificadores estáveis. Renomear ou remover um contexto não apaga a associação salva; IDs ausentes da lista atual são preservados. **Remover** nos cartões de contexto continua atuando sobre o contexto atual; a seção experimental **Associações salvas** permite escolher uma entrada salva individualmente. Se o documento estiver inválido ou em versão futura, seus bytes são preservados e a gravação de associações e o automático ficam bloqueados. A chave separada `contextsJSON` começa vazia; não há migração automática dos perfis.

Remover um perfil na aba **Perfis** preserva suas referências. A aba Contextos mostra separadamente quantas associações de Activity e área apontam para perfis indisponíveis, inclusive em contextos antigos. Para um contexto disponível, escolha outro perfil e associe novamente ou remova a associação atual. Se o padrão foi removido, escolha outro padrão válido; sem perfis restantes, crie um na aba Perfis. Corrigir o padrão não ativa o automático nem libera uma escolha manual no mesmo contexto.

### Associações salvas (Source experimental)

Abra **Associações salvas** e escolha uma entrada. A seção começa recolhida e sem seleção; navegar e abrir o seletor não grava. Confira o domínio (Activity ou área), o último nome salvo, o identificador completo e o perfil associado. Nomes iguais não representam a mesma associação: a identidade é domínio + ID. A lista inclui contextos não observados agora e perfis indisponíveis; ausência na descoberta não significa que um contexto foi excluído.

**Remover associação** exige confirmação explícita e apaga somente essa entrada, sem apagar perfil ou contexto. Não há Desfazer. **Cancelar** descarta a pergunta sem gravar e permite escolher outra entrada. Mudar de aba mantém a pergunta; fechar as configurações a descarta. Escape fecha primeiro o menu do seletor e depois cancela a pergunta. Alterações externas deixam a confirmação antiga bloqueada: cancele e escolha novamente.

A remoção salva apenas `contextsJSON`, preservando as outras associações, o padrão, a política, o modo ligado/desligado e o Pomodoro. Uma prévia de aparência não precisa ser descartada. Ao terminar a interação, o automático pode usar outra associação ou o padrão conforme sua regra; a escolha manual no mesmo contexto continua valendo. Remover explicitamente uma associação órfã pode liberar esse fallback; enquanto ela estiver salva e for usada pela regra, o perfil ausente continua pausando a troca. Esta entrega de desenvolvimento não integra os assets publicados 0.2.9; testes Source e qualificação instalada são etapas separadas.

O documento de associações não armazena as preferências do automático. A configuração global de avisos locais do Pomodoro continua independente e desligada por padrão. As provas de Source incluem precedência, escolhas manuais, reentrada, documentos inválidos e bloqueios na composição real da dock com backends sintéticos; não comprovam a jornada nativa.

## English

The [0.2.8 alpha prerelease](https://github.com/caiolombello/orla-desktop/releases/tag/v0.2.8) introduced explicit associations. Current Source adds optional automatic profiles, without a release yet. Commit `c5509a1` was installed in one KDE/Wayland session and passed a no-edit visit to the tab with automation off; see the [bounded validation](validation/contexts-auto-installed.md). This does not qualify enabled automation, its persistence across restart or complete focus/seat behavior. Synthetic Qt tests remain separate from native evidence.

The tab observes Activity and virtual desktop separately. Choose an existing managed profile, then **Associar Activity atual** or **Associar área atual** to save; **Remover** clears only the current association. Navigating these selectors does not save. Binding alone does not enable automation or switch KDE context.

Discovery is read-only and remains lazy while automation is off. Valid enabled automation keeps it loaded beyond Settings. The separate desktop writer still requires the explicit **Trocar área** command. Test snapshot overrides block native discovery.

Choose **Perfil padrão**, then choose the inputs under **Usar no automático**. **Activity e áreas** is the default: Activity binding, desktop binding, then the chosen default, requiring both contexts. **Somente áreas** explicitly uses desktop binding, then default, ignoring Activity availability while preserving its bindings. Choosing either selector does not enable automation. Opt into **Trocar o perfil automaticamente** separately. Valid profiles and binding documents are required; no implicit migration occurs. A missing profile targeted by the chosen rule pauses switching rather than silently falling back. Required current contexts must be ready and present in their normalized lists; otherwise the current profile stays unchanged.

If KDE reports no current Activity, **Activity e áreas** waits even when a virtual desktop is available. **Somente áreas** ignores Activity by explicit choice, including a service failure; it does not infer absence from an outage. Status names unavailable required contexts and distinguishes loading. The [earlier native diagnosis](validation/contexts-auto-installed.md#enabled-host-diagnosis-and-accessible-tabs) records the combined-mode wait without creating or activating an Activity in the session.

A manual profile choice wins until a required context ID changes, **Retomar automático agora**, or a committed policy change. A manual choice made after that policy change still wins. If no required context has yet been confirmed, the first ready identity attaches to that choice; a later different identity can release it. Renaming, same-ID reconnection or changing defaults/bindings does not clear manual choice. Activity changes do not release it in desktop-only mode. The override lasts for this session; restarting with automation enabled resumes once the required contexts are ready. Restoring the saved profile at startup is not a new manual choice; a genuine later selection still wins. Edits, drags, scrolling, popups, shared Control Center transfers and audio work defer switching without closing, cancelling or applying them. On release only the latest context is evaluated. Disabling preserves the current profile.

`autoContextEnabled` (false by default), `autoContextDefaultProfile` (initially empty) and `autoContextPolicy` (`activity-desktop` by default, or `desktop`) are per-dock preferences shared across profiles and saved immediately. Appearance Cancel does not undo them. A committed policy change resumes the rule after interactions and Settings close; a newer manual choice wins. An unknown policy remains raw, pauses automation and leaves the selector unselected but repairable. Automation does not change KDE contexts, monitors, app windows, bar or launcher. Pomodoro retains its object/deadline. Complete user-panel and per-monitor journeys remain open.

Associations use stable IDs. Renaming or removing a context preserves the association, including IDs absent from current discovery. **Remover** in each context card still applies to the current context; experimental **Associações salvas** selects individual saved entries. Invalid or future-format documents retain their bytes and block binding writes and automation. `contextsJSON` starts empty; profiles are not implicitly migrated.

Removing a profile in **Perfis** preserves its references. Contexts separately counts Activity/desktop associations targeting unavailable profiles, including old contexts. For an available context, select another profile and bind again or remove its current association. Replace a removed default with a valid one; if no profiles remain, create one in Perfis first. Repairing the default neither enables automation nor releases a manual choice in the same context.

### Saved associations (experimental Source)

Open **Associações salvas**, then choose one entry. The section starts collapsed and unselected; opening or navigating its selector does not save. Check the domain (Activity/desktop), last saved name, full ID and associated profile. Identity is domain + ID, including when names match. The list includes contexts not observed now and unavailable profiles; failed discovery does not establish that a context was deleted.

Explicit **Remover associação** confirmation deletes only that entry, keeping the profile and KDE context. There is no Undo. **Cancelar** discards the question without saving and allows another choice. Tabs keep the question; closing Settings discards it. Escape closes the native selector menu first, then cancels the question. External authority changes block the old confirmation: cancel and choose again.

Removal writes only `contextsJSON`, preserving other entries, default/policy/enabled preferences and Pomodoro. An appearance preview can remain open. When the interaction ends, automation may use another binding or its default; a manual choice in the same context still wins. Explicitly removing an orphan binding can allow that fallback; retaining a missing target used by the rule continues to pause switching. This development increment is absent from published 0.2.9 assets; Source and installed qualification remain separate.

The binding document does not contain automation preferences. Local Pomodoro notices remain independently off by default. Source tests cover priority, manual choices, reentrancy, invalid documents and dock composition using synthetic backends; they do not establish native acceptance.

## Experimental internal removal contract

`ContextBindingsState.unbind(kind, contextId, expectedProfileScope,
expectedProfileRevision, expectedContextRevision, expectedRevision,
continuationGuard)` adds an optional synchronous predicate. Existing six-argument
callers retain their behavior. A supplied non-function refuses the request;
an eligible predicate runs once and only boolean `true` accepts it. A throw
refuses it. A missing-entry no-op still validates the predicate and preserves
the original raw bytes and revision without a write.

The state revalidates owners, raw documents, scope, revisions and monotonic
authority/command epochs after the predicate, immediately before its single
`contextsJSON` assignment. Newer reentrant operations are preserved rather than
rolled back. The UI owns the captured domain/ID, impact and session validation;
a successful return does not establish ownership after setter callbacks.
