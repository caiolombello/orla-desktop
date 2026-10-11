# Manual dock profiles / Perfis manuais do dock

Orla Dock 0.2.5 alpha. P1/C1 are partial; this covers the dock. Profile JSON uses `0.1-experimental`, independently versioned from Orla.

## English

1. Open dock settings: the tabs are **Aparência** (Appearance), **Widgets** and **Perfis** (Profiles). The current UI labels are Portuguese.
2. In **Perfis**, **Criar Trabalho, Pessoal e Jogos** makes independent Work, Personal and Games copies of your saved flat preferences. **Preferências anteriores** (Previous preferences) stays active; initialization does not change the visible dock.
3. Choose a profile, then press **Usar perfil** (Use profile). Moving the selector or its arrow keys only changes the pending choice. To clone the saved active presentation and activate the clone immediately, enter a unique name and press **Criar e usar** (Create and use).
4. Customize apps and appearance for that profile. Appearance is a preview until **Aplicar** (Apply); **Cancelar**, Escape or closing settings discards it. Apply or Cancel before creating/switching profiles. Changing tabs keeps the draft. Undo belongs to the current profile and is cleared when the profile changes.
5. In **Widgets**, toggle visibility and move widgets with the up/down buttons. These changes, calendar-event visibility and the current-desktop window filter save immediately. Appearance Cancel does not undo them. Previous preferences allows visibility changes but keeps the original widget order; use a profile to reorder.
6. Select **Preferências anteriores** and press **Usar perfil** to return to the flat settings. Managed-profile edits do not replace those saved flat fields.

Each profile stores pinned apps, theme/icon/motion/custom appearance, the order and visibility of seven known widgets (clock, Pomodoro, music, system battery, QuotaLantern, PeriGauge and FalaTrace), calendar-event visibility and the current-desktop window filter. Calendar visibility does not select calendars or connect an account; KDE PIM owns that setup. The window filter does not switch desktops.

The Pomodoro remains one global timer: switching profiles, including hiding its widget, keeps its object and deadline within the same dock. Native resume across process restarts has not been tested. Integration providers and media state are shared rather than copied into profiles.

Limits: up to 16 named profiles (Previous preferences is separate), unique names of up to 48 characters with no control characters, and up to 32 local `.desktop` launcher URLs per profile. Leading/trailing name whitespace is trimmed on creation. Rename/delete/import/export controls are not provided yet. Missing apps stay in saved preferences; passive reload does not replace the saved list with only apps currently resolved by KDE. Validated URL spelling is preserved while Qt URL identity is used for app operations. Profiles contain data, not imported community themes or executable plugins.

Empty `profilesJSON` uses the flat settings; there is no implicit migration. Invalid, oversized or future-format profile JSON is preserved and disables presentation writes. On startup the dock falls back to the flat presentation; invalid replacement while running retains the last validated presentation. Report the error rather than editing KConfig while Plasma is running. If a saved custom appearance is invalid when cloning, the new profile uses the earlier theme/icon/motion preferences and shows a message; the original flat value is preserved.

Activities/desktop association and switching, bar/launcher/event-surface selection, native popup/focus gestures and full release qualification remain open. See [validation](validation/profiles-0.2.5.md).

## Português brasileiro

1. Abra as configurações do dock: **Aparência**, **Widgets** e **Perfis**.
2. Em **Perfis**, **Criar Trabalho, Pessoal e Jogos** faz três cópias independentes das preferências salvas. **Preferências anteriores** permanece ativo; inicializar não muda o dock visível.
3. Escolha um perfil e pressione **Usar perfil**. O seletor/setas só muda a escolha pendente. Para copiar a apresentação salva do perfil ativo e ativar a cópia, digite um nome único e pressione **Criar e usar**.
4. Personalize apps e aparência do perfil. A aparência fica em prévia até **Aplicar**; **Cancelar**, Escape ou fechar descarta a prévia. Aplique ou cancele antes de criar/trocar perfil. Mudar de aba mantém o rascunho. Desfazer pertence ao perfil atual e é limpo ao trocar.
5. Em **Widgets**, altere visibilidade e ordem pelos botões subir/descer. Essas opções, eventos do calendário e filtro pela área atual salvam imediatamente; Cancelar aparência não as desfaz. Preferências anteriores permite mudar visibilidade, mas mantém a ordem original; use um perfil para reordenar.
6. Escolha **Preferências anteriores** e pressione **Usar perfil** para voltar às preferências flat. Alterações nos perfis não substituem esses campos salvos.

Cada perfil guarda apps fixados, tema/ícones/movimento/aparência personalizada, ordem e visibilidade dos sete widgets conhecidos (relógio, Pomodoro, música, bateria do sistema, QuotaLantern, PeriGauge e FalaTrace), eventos do calendário e filtro pela área atual. Mostrar eventos não escolhe calendários nem conecta contas: isso pertence ao KDE PIM. O filtro não troca a área de trabalho.

O Pomodoro continua global: selecionar outro perfil, mesmo ocultando seu widget, mantém objeto e prazo no mesmo dock. A retomada nativa entre processos não foi testada. Providers e estado da mídia continuam compartilhados.

Limites: até 16 perfis nomeados, além de Preferências anteriores; nomes únicos com até 48 caracteres e sem caracteres de controle; até 32 URLs locais de arquivos `.desktop` por perfil. Espaços no início/fim do nome são removidos na criação. Ainda não há controles para renomear, apagar, importar ou exportar. Apps ausentes permanecem salvos; recarregar não substitui a lista pelos apps resolvidos pelo KDE. A grafia validada das URLs é preservada; operações de apps comparam identidade de URL pelo Qt. Perfis são dados: não importam temas comunitários nem executam plugins.

`profilesJSON` vazio usa as preferências flat, sem migração implícita. JSON inválido, grande demais ou de formato futuro é preservado e bloqueia gravações da apresentação. Na inicialização, o dock usa flat; substituição inválida durante execução mantém a última apresentação validada. Relate o erro em vez de editar KConfig com o Plasma aberto. Se a aparência personalizada salva for inválida ao copiar, o novo perfil usa as preferências anteriores de tema/ícones/movimento e mostra um aviso; o valor flat original é preservado.

Associação/troca de Activities/desktops, escolha de barra/launcher/eventos, gestos/foco de popup nativo e qualificação da release completa continuam pendentes. Consulte a [validação](validation/profiles-0.2.5.md).
