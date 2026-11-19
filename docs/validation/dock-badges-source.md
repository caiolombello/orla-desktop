# Contadores de não lidas na dock (Source)

**Data:** 19/11/2026. **Ambiente:** Fedora 44, Plasma 6.8.3, KF6 6.32, Qt 6.11.2, Wayland, uma tela.
**Branch verificada:** `feat/dock-unread-badges`.

## O que faz

Apps como Telegram, Thunderbird e Discord publicam o número de não lidas pelo
sinal D-Bus `com.canonical.Unity.LauncherEntry.Update`, a mesma fonte que o
gerenciador de tarefas do Plasma lê. O serviço de integrações da dock passa a
escutar esse sinal quando a dock pede os contadores (`BadgeCounts(as)`). A dock
pergunta a cada 2 s pelos apps que mostra e desenha uma pílula vermelha com o
número (até "99+") no canto do ícone. A opção global "Mostrar contadores de não
lidas nos apps" desliga o recurso.

Semântica, conferida no `smartlauncherbackend.cpp` do plasma-desktop 6.8.3
(reimplementada, não copiada):

- cada atualização muda só as chaves presentes (`count`, `count-visible`);
- `count-visible=false` esconde o contador;
- quando o app sai do barramento, os contadores dele somem;
- nada é consultado na partida: um contador publicado antes de o serviço
  começar a escutar só aparece na próxima atualização do app.

Como qualquer processo da sessão pode emitir o sinal, o serviço limita IDs (só
`*.desktop`), 64 apps, contagens de 0 a 2³¹−1 e consultas de 128 IDs, e não
registra nada em log. Ele também reivindica o nome `com.canonical.Unity` se
estiver livre, porque alguns apps só publicam quando esse nome tem dono. Neste
sistema o nome estava livre: o Orla substitui o gerenciador de tarefas do Plasma,
que é quem normalmente o reivindica.

## Verificação

- Offscreen:
  - `test_dock_badges`: lógica, estado, tile e a dock real.
  - `test_integrations`: inclui um barramento privado com um emissor real e a saída do emissor.
  - Suítes de UI da dock com Fusion e org.kde.desktop, mais `test_design_system`, `test_package_cli` e `test_release`.
- Galeria: `docs/screenshots/dock-badges/glass.png` (escuro) e `frost.png` (claro), com resposta sintética.
- Ao vivo, dock instalada desta branch com backup e um reinício do Plasma:
  - A dock chamou `BadgeCounts` a cada 2 s com os 7 apps fixados.
  - O serviço passou a ser dono de `com.canonical.Unity`.
  - Um emissor sintético com conexão mantida publicou `count=5` para `org.kde.dolphin.desktop`, e o serviço respondeu com esse contador.
  - Depois de `count=0` e da saída do emissor, a resposta ficou vazia.

## Não verificado

- O selo desenhado na dock ao vivo: a dock estava oculta atrás de uma janela em uso,
  e não usei entrada virtual para revelá-la. O desenho foi visto só offscreen.
- Nenhum app real: neste sistema só Discord e Chromium poderiam publicar, e não foram
  abertos. Se um app não publicar, o ícone dele não terá contador.
- O Plasma esconde contadores no modo Não Perturbe; esta versão ainda não.
