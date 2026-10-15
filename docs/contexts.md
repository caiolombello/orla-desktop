# Contexts / Contextos

## Português

A prerelease alpha [0.2.8](https://github.com/caiolombello/orla-desktop/releases/tag/v0.2.8) adicionou associações explícitas na aba **Contextos**. O Source atual acrescenta perfis automáticos opcionais, ainda sem release. A versão do commit `c5509a1` foi instalada numa sessão KDE/Wayland e passou uma visita sem edição à aba, com o automático desligado; veja a [validação delimitada](validation/contexts-auto-installed.md). Essa prova não qualifica a automação ligada, sua persistência após reinício ou o foco/seat completo. Os testes Qt sintéticos continuam separados dessas provas nativas.

A aba observa Activity e área virtual em cartões separados. Escolha um perfil gerenciado e use **Associar Activity atual** ou **Associar área atual**; **Remover** elimina apenas a associação atual. Navegar nesses seletores não grava. Associar não ativa o modo automático nem troca a Activity/área do KDE.

A descoberta é somente leitura. Com o automático desligado, continua carregada apenas enquanto a aba Contextos está aberta. Com ele habilitado e as preferências válidas, permanece ativa fora das configurações. O backend separado que escreve a área de trabalho continua exclusivo do comando explícito **Trocar área**. Overrides de teste impedem a descoberta nativa.

### Perfis automáticos (Source experimental)

1. Crie perfis na aba **Perfis**. Em **Contextos**, escolha um **Perfil padrão** gerenciado existente; isso salva só essa preferência e não ativa o modo.
2. Marque **Trocar o perfil automaticamente**. O modo começa desligado por instância da dock e exige perfis e associações válidos. Usa Activity associada → área associada → padrão. Uma associação a perfil ausente pausa a troca; não cai silenciosamente em outra regra.
3. Os dois contextos devem estar prontos, com IDs atuais nas listas normalizadas. Durante carregamento ou indisponibilidade, o perfil atual é mantido. Nomes e IDs ausentes não são convertidos em novas associações.
4. Escolher/criar um perfil manualmente prevalece até o próximo par confirmado de IDs diferente, ou **Retomar automático agora**. Renomeação, reconexão no mesmo par e alteração do padrão/associações não desfazem essa escolha. O override é da sessão: ao reiniciar com o modo habilitado, o automático retoma quando receber o primeiro par completo.
5. Edições, arrastes, rolagem, popups, transferência da Central e pedidos/gestos de áudio adiam a troca. A automação não fecha, cancela ou aplica uma edição para prosseguir. Ao liberar, recalcula somente o contexto mais recente. Desativar mantém o perfil atual.

Se o KDE não informar uma Activity atual, o modo aguarda mesmo quando a área virtual está disponível. Esta versão exige ambos os contextos; não oferece ainda um modo automático somente por área de trabalho. O [diagnóstico nativo](validation/contexts-auto-installed.md#enabled-host-diagnosis-and-accessible-tabs) registra esse caso sem criar ou ativar uma Activity na sessão.

As opções do modo são globais entre os perfis desta dock e salvas imediatamente em `autoContextEnabled` e `autoContextDefaultProfile`; Cancelar aparência não as desfaz. O modo não troca Activity, área, monitor, janelas, barra ou launcher. O Pomodoro continua no mesmo objeto/prazo. Comportamento por monitor e a jornada KDE real permanecem abertos.

As associações usam identificadores estáveis. Renomear ou remover um contexto não apaga a associação salva; IDs ausentes da lista atual são preservados e aparecem apenas como uma contagem de associações antigas. A aba não oferece remoção individual dessas associações antigas; **Remover** atua sobre o contexto atual. Se o documento estiver inválido ou em versão futura, seus bytes são preservados e a gravação de associações e o automático ficam bloqueados. A chave separada `contextsJSON` começa vazia; não há migração automática dos perfis.

O documento de associações não armazena as preferências do automático. A configuração global de avisos locais do Pomodoro continua independente e desligada por padrão. As provas de Source incluem precedência, escolhas manuais, reentrada, documentos inválidos e bloqueios na composição real da dock com backends sintéticos; não comprovam a jornada nativa.

## English

The [0.2.8 alpha prerelease](https://github.com/caiolombello/orla-desktop/releases/tag/v0.2.8) introduced explicit associations. Current Source adds optional automatic profiles, without a release yet. Commit `c5509a1` was installed in one KDE/Wayland session and passed a no-edit visit to the tab with automation off; see the [bounded validation](validation/contexts-auto-installed.md). This does not qualify enabled automation, its persistence across restart or complete focus/seat behavior. Synthetic Qt tests remain separate from native evidence.

The tab observes Activity and virtual desktop separately. Choose an existing managed profile, then **Associar Activity atual** or **Associar área atual** to save; **Remover** clears only the current association. Navigating these selectors does not save. Binding alone does not enable automation or switch KDE context.

Discovery is read-only and remains lazy while automation is off. Valid enabled automation keeps it loaded beyond Settings. The separate desktop writer still requires the explicit **Trocar área** command. Test snapshot overrides block native discovery.

Choose **Perfil padrão**, then opt into **Trocar o perfil automaticamente**. Existing valid profiles and bindings are required; no implicit migration occurs. Priority is Activity binding, desktop binding, then the chosen default. Missing bound profiles pause switching rather than silently falling back. Both current contexts must be ready and present in their normalized lists; otherwise the current profile stays unchanged.

If KDE reports no current Activity, automation waits even when a virtual desktop is available. This version requires both contexts and does not yet offer desktop-only automation. The [native diagnosis](validation/contexts-auto-installed.md#enabled-host-diagnosis-and-accessible-tabs) records this case without creating or activating an Activity in the session.

A manual profile choice wins until a different confirmed pair of IDs or **Retomar automático agora**. Renaming, same-pair reconnection or changing defaults/bindings does not clear that choice. The override lasts for this session; restarting with automation enabled resumes on the first complete snapshot. Edits, drags, scrolling, popups, shared Control Center transfers and audio work defer switching without closing, cancelling or applying them. On release only the latest context is evaluated. Disabling preserves the current profile.

`autoContextEnabled` (false by default) and `autoContextDefaultProfile` (initially empty) are per-dock preferences shared across its profiles and saved immediately. Appearance Cancel does not undo them. Automation does not change KDE contexts, monitors, app windows, bar or launcher. Pomodoro retains its object/deadline. Native and per-monitor journeys remain open.

Associations use stable IDs. Renaming or removing a context preserves the association. Missing IDs appear only as a count of old associations; the tab does not remove them individually. **Remover** applies to the current context. Invalid or future-format documents retain their bytes and block binding writes and automation. `contextsJSON` starts empty; profiles are not implicitly migrated.

The binding document does not contain automation preferences. Local Pomodoro notices remain independently off by default. Source tests cover priority, manual choices, reentrancy, invalid documents and dock composition using synthetic backends; they do not establish native acceptance.
