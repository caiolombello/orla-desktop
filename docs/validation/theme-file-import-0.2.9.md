# Importação local de temas — 16/10/2026

Escopo: checkout de desenvolvimento, com versão do pacote ainda `0.2.9`.
Nenhuma release foi publicada ou instalação Main alterada neste incremento.

## Comportamento

**Importar arquivo…** abre um seletor modal associado à janela de configurações.
Aceitar inicia uma leitura limitada; o resultado preenche o JSON pendente.
**Usar na prévia** continua obrigatório antes de **Aplicar**. Falhas preservam a
última prévia válida; fechar, mudar de aba ou editar invalida o resultado antigo.

O serviço de temas é independente dos plugins de projetos e do launcher. O
instalador registra ativação lazy somente com as dependências disponíveis,
preserva registros estranhos e repete a atualização do D-Bus numa reinstalação.
O leitor distribuído e o parser canônico são os mesmos já usados pelo kit CLI.

## Verificação executada

| Verificação | Resultado |
| --- | --- |
| CLI, instalação, parser, leitor, serviço e kit (`test_package_cli test_themes test_theme_file test_theme_service test_release`) | 71 testes passaram |
| Estado, picker, aparência, presets, dock e design, estilo Fusion | 129 testes; OK, 3 skips existentes |
| Estado, picker, aparência, presets e design, estilo KDE | 95 testes passaram |
| `scripts/design.py check` | Sem ocorrências |
| Galeria | Claro/escuro; botão e foco inspecionados em 350 e 420 px; erro em 420 px |
| Pacote construído | 78 arquivos; bytes/modos conferidos com Source; SHA-256 `adef6b0b1534c42dd1f2a40de2951bc1f2e15e4155c75f4e05a58d937b42c406` |

A prova real de D-Bus privado usou um diretório de instalação com espaços e
ativação lazy. O bridge QML recebeu o tipo STRING do Plasma, extraiu seu texto
sem coerção genérica e passou pelo estado real: JSON pendente/zero writes →
prévia/zero writes → aplicar/um write → desfazer/dois writes, restaurando a
configuração sintética. Sem warnings, processos ou socket restantes. Essa prova
foi offscreen e não incluiu o seletor ou input Wayland.

Os testes causais corrigiram publicação após cancelamento, timeout com owner
destruído, prévia antiga apagando entrada mais recente, encerramento de stdout
excessivo e retry do registro após perda de dependência ou downgrade.

## Limites nativos e falha preexistente

Um prototype instrumentado, em KWin/Wayland e D-Bus isolados, abriu o seletor
Qt Quick como filho da janela original. Cancelar preservou janela, draft e
configuração; os processos próprios terminaram normalmente. Os bookends Main
confirmaram o mesmo processo Plasma, bancos/configuração/launcher preservados,
automação OFF e sessão desbloqueada. Não houve input no compositor Main.

O aceite de arquivo não foi qualificado: a lista expõe somente SetFocus pelo
AT-SPI, e focar o item não habilitou Aceitar. O teste encerrou pelo Cancelar
normal, mantendo o erro original. Escape, o diálogo de plataforma KDE e o fluxo
completo do produto no Wayland seguem abertos. Não há alegação de instalação ou
validação nativa completa baseada nos testes offscreen.

O teste de áudio KDE `test_audio_output_pointer_failures_restore_confirmed_presentation`
falhou em `pendingKind` tanto no checkout atual quanto na base `8d74a055` em
processos isolados. A assinatura é preexistente; a causa específica continua
indefinida e áudio não foi alterado neste incremento.

## Capturas sintéticas

| Largura | Escuro | Claro |
| --- | --- | --- |
| 350 px | ![Importar tema, escuro, 350 px](captures/theme-file-dark-350.png) | ![Importar tema, claro, 350 px](captures/theme-file-light-350.png) |
| 420 px | ![Importar tema, escuro, 420 px](captures/theme-file-dark-420.png) | ![Importar tema, claro, 420 px](captures/theme-file-light-420.png) |
