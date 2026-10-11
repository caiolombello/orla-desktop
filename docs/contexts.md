# Contexts / Contextos

## Português

O checkout-fonte candidato a 0.2.8 adiciona a aba experimental **Contextos** às configurações do dock. A release pública continua sendo a [0.2.7](https://github.com/caiolombello/orla-desktop/releases/tag/v0.2.7); esta integração de fonte ainda não foi publicada.

A aba observa Activity e área de trabalho virtual em cartões separados e, quando o contexto atual está disponível, permite associá-lo explicitamente a um perfil gerenciado que já existe. Use o seletor para escolher o perfil e **Associar Activity atual** ou **Associar área atual** para salvar; **Remover** elimina a associação atual. Apenas navegar pelo seletor não grava nada. As associações organizam preferências: nesta versão elas não selecionam perfil automaticamente, não trocam Activity/área e não alteram aplicativos, aparência ou widgets.

A descoberta nativa é carregada somente enquanto as configurações estão abertas na aba **Contextos**. A fonte consultada é somente de leitura; indisponibilidade de Activity não impede observar a área de trabalho, e vice-versa. Quando o KDE não fornece o domínio atual, seu cartão informa indisponibilidade e desativa suas ações.

As associações usam identificadores estáveis. Renomear ou remover um contexto não apaga a associação salva; IDs ausentes da lista atual são preservados e aparecem apenas como uma contagem de associações antigas. A aba não oferece uma lista nem uma ação para remover individualmente essas associações antigas; **Remover** atua somente sobre a associação do contexto atual ainda apresentado pelo KDE. Se o documento de associações salvo estiver inválido ou em uma versão futura, a fonte mantém seus bytes originais e bloqueia somente as ações de associação. A preferência usa a chave separada `contextsJSON`, inicialmente vazia; não há migração automática dos perfis existentes.

A integração não aplica nem cancela uma prévia de aparência pendente e não seleciona ou reescreve perfis. O Pomodoro conserva sua identidade e prazo; a configuração global de aviso local do Pomodoro continua desligada por padrão e independente das associações. O guia descreve o incremento de fonte, não uma validação de KConfig/reinício ou de uma sessão KDE real.

## English

The source checkout for candidate 0.2.8 adds an experimental **Contexts** tab to dock settings. The public release remains [0.2.7](https://github.com/caiolombello/orla-desktop/releases/tag/v0.2.7); this source integration has not been released.

The tab observes Activity and virtual desktop in separate cards. When the current context is available, it lets you explicitly associate it with an existing managed profile. Choose a profile, then select **Associar Activity atual** or **Associar área atual** to save; **Remover** clears the current association. Moving through a selector does not write anything. Associations organize preferences: this version does not automatically select a profile, switch an Activity or desktop, or change apps, appearance, or widgets.

Native discovery is loaded only while Settings is open on the **Contextos** tab. The source is read-only. An unavailable Activity does not prevent desktop observation, and vice versa. If KDE cannot provide the current item for one domain, that card reports it as unavailable and disables its actions.

Associations use stable IDs. Renaming or removing a KDE context does not erase its saved association; IDs missing from the current list are preserved and appear only as a count of old associations. The tab does not list or let you individually remove those unavailable associations; **Remover** applies only to the current context still shown by KDE. If the saved association document is invalid or from a future version, the source preserves its original bytes and blocks only association actions. The feature uses a separate `contextsJSON` setting with an empty default; existing profiles are not automatically migrated.

The integration does not apply or cancel a pending appearance preview and does not select or rewrite profiles. Pomodoro identity and deadline remain with the existing timer; the global local Pomodoro notice remains off by default and independent from these associations. This guide describes a source increment, not KConfig/restart qualification or a real KDE session validation.
