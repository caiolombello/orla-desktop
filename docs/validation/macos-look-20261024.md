# Visual macOS — registro de validação (23–24/10/2026)

Sessão real: Fedora 44, Plasma 6.7.5/Wayland, Qt 6.11.2, uma tela 4K com escala
1,45 (2649 × 1490 lógicos), esquema escuro. Cada instalação na sessão teve
backup em `.runtime/live-update-r17…r30-*/installed-before.tar` (fora do Git).
As capturas da sessão real mostram conteúdo pessoal e não foram publicadas; as
imagens em `docs/screenshots/` são sintéticas.

| PR | Entrega | Observado na sessão real | Não observado |
|---|---|---|---|
| #120 | Central em grade (macOS) | grade aberta pela dock com Wi-Fi, Bluetooth, Não perturbe, microfone, brilho, som e perfil reais, sem mudar estado | esquema claro |
| #121 | Tema Plasma Orla | barra translúcida com desfoque; calendário do relógio e uma notificação local de teste em vidro arredondado | esquema claro, outras escalas |
| #122 | Dock, popups e etiqueta com o desfoque do tema | variante de diagnóstico (moldura em vermelho) mostrou o desvio inicial e depois a coincidência exata com margens medidas de ~9,5/14 px; dock fosca e simétrica; Central pela dock e pela barra e configurações em vidro; etiqueta em bolha; um log temporário mediu o limite de ~720 px que o Plasma impõe ao diálogo, e a Central compacta coube | outros temas da dock com o desfoque |
| #123 | Decoração Orla | semáforos de 12 px, glifos no hover do grupo e título central na janela das Configurações; o primeiro desenho tinha os discos cortados (grupo sem altura), corrigido; o cache de QML do KWin foi confirmado e contornado com id novo | esquema claro, janelas inativas lado a lado |
| #124 | Página de redes Wi-Fi | leitura nativa só de leitura (offscreen, `plasma-nm` real): rede conectada, protegida e salva, sem registrar nomes | a página aberta na sessão; conectar/desconectar (não executados para não derrubar a conexão em uso) |
| #125 | Página de aparelhos Bluetooth | leitura nativa só de leitura (offscreen, BluezQt real): dois aparelhos pareados, um conectado com bateria | a página aberta na sessão; conectar/desconectar (não executados para não desligar periféricos) |
| #126 | `macos_look.py` | aplicado; `isEffectLoaded` confirmou `magiclamp` carregado e `squash` descarregado | o Alt+Tab e o efeito de minimizar na tela |
| #128 | Lixeira na dock | instalada e ativada por script do Plasma (`showTrash=true`) | a dock com a Lixeira na tela |

## Incidente de 24/10

Às 22:30 uma janela de 15 s sem entrada de teclado/mouse liberou a instalação
da dock e da barra, com o reinício do Plasma e o movimento do ponteiro para
revelar a dock. Havia um vídeo em tela cheia tocando: o Plasma reiniciou por
alguns segundos durante o vídeo, e o ponteiro passou sobre ele. A captura foi
apagada e a interação parou. A verificação agora também exige que nenhum player
MPRIS esteja tocando (`.runtime/.../safe_to_interact.sh`).

## Ambiente

Depois da atualização do sistema de 24/10 (mesa, pipewire, bluez),
`test_audio_output_pointer_failures_restore_confirmed_presentation` passou a
falhar localmente no estilo `org.kde.desktop`, inclusive no `main`. A causa era
o teste clicar fora da janela de 220 px do harness; o #127 aumenta a janela
nesse teste.

## Pendências

- Formato de relógio do macOS na barra ("sáb 24 out 18:30"): o helper de
  layout só aceita uma atualização gerenciada a partir da primeira revisão, e a
  barra desta máquina já usou essa atualização para receber a Central. Mudar a
  configuração direto criaria desvio no recibo e travaria a restauração do
  layout original, então nada foi alterado.
- Observar na sessão: páginas de Wi-Fi e Bluetooth, Lixeira, Alt+Tab e lâmpada
  mágica; esquema claro; outras escalas e monitores.
