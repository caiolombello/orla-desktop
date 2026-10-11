# Central de Controle (alpha 0.2.9)

A alpha 0.2.9 publica a primeira fatia experimental. A revisão independente do Source foi aprovada; isso não equivale à validação de uma sessão Plasma nativa.

Ative **Mostrar Central de Controle no dock (global)** em **Widgets** para exibir o botão opcional no dock. A preferência é global, começa desligada e é salva imediatamente, fora dos perfis.

O popup apresenta dois cards independentes: **Som e mídia**, com o modelo MPRIS já compartilhado pelo dock, e **Energia**, com o modelo de bateria já existente. Os botões explícitos podem encaminhar a abertura das páginas de Som, Energia ou **Todos os ajustes** nas Configurações do Sistema do KDE. Um encaminhamento bem-sucedido não confirma que a janela abriu nem que uma configuração mudou.

Esta fatia mostra estado e oferece atalhos. Ela não controla diretamente volume, microfone, Wi-Fi, Bluetooth, brilho ou Não perturbe; não é HUD nem sistema de notificações. O popup pode ativar a leitura já existente da bateria enquanto necessário. Ausência de player/bateria não transforma o card correspondente em prova de serviço ou hardware disponível.

O [registro de validação](validation/control-center-peripherals-0.2.9.md) separa testes Source/mock de validação nativa ainda aberta.
