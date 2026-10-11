# Calendário KDE experimental no Source

O Source atual do Orla inclui `pimevents` em `enabledPlugins` somente enquanto o
popup do calendário está aberto, a preferência de eventos do perfil está ligada
e não há fixture de teste. Fechar o popup ou desligar a preferência define
`enabledPlugins` como uma lista vazia. Isso não comprova que Akonadi, recursos
KDE ou processos iniciados pelo KDE terminaram. Esta mudança pertence ao
checkout Source; os assets da alpha 0.2.9 permanecem inalterados.

O calendário aplica as cores de primeiro plano do dock também aos textos
internos do `MonthView`, inclusive dias fora do mês que o componente KDE marca
como desabilitados. Isso evita texto escuro sobre o fundo Midnight e acompanha
as paletas clara e escura do Orla.

## Estados que o Orla consegue observar

| Estado | Evidência disponível |
|---|---|
| Eventos desativados | A preferência do perfil está desligada. |
| Componente PIM não encontrado | Os metadados instalados do KDE não contêm `pimevents`. |
| Eventos presentes | O modelo do KDE entregou um ou mais eventos para a data. |
| Nenhum evento recebido | A lista atual está vazia. Isso pode significar uma data vazia, nenhum calendário selecionado ou KDE PIM indisponível. |

A presença dos metadados não comprova que o plugin carregou. Uma lista vazia,
`modelReset` ou tempo decorrido também não comprova que o backend terminou uma
consulta, está online ou contém zero calendários. Por isso a interface não usa
estados `pronto`, `offline`, `sem calendários` ou `sem seleção`. Eventos
recebidos também não comprovam sincronização recente.

## Configurar Google Agenda pelo KDE

1. Abra o calendário do Orla e escolha **Configurar no KOrganizer**.
2. No KOrganizer/KDE PIM, adicione e autentique o recurso Google pelo fluxo do
   KDE.
3. Escolha no KDE quais calendários o plugin PIM deve exibir.
4. Volte ao Orla e mantenha **Eventos do calendário** ligado no perfil desejado.

O Orla não solicita nem armazena a autenticação Google. A seleção do plugin PIM
é compartilhada com o relógio/calendário do KDE: alterá-la no KDE também muda o
relógio. Esta fatia apenas lê os eventos entregues e não altera essa seleção.

## Limites da validação

Os testes usam eventos e metadados sintéticos, plataforma Qt offscreen,
diretórios XDG próprios e um endereço de barramento inexistente. Eles não
carregam `pimevents`, iniciam Akonadi, acessam contas, calendários ou configuração
do usuário, nem comprovam abertura nativa do KOrganizer. Google real,
recorrência, dia inteiro, fuso, sincronização, indisponibilidade e seleção
continuam no gate G1.

Execute o calendário em processo próprio; o supervisor usa somente a biblioteca
padrão e prepara o ambiente antes de importar Qt:

```bash
python3 -B tests/run_calendar_tests.py
python3 -B tests/run_calendar_tests.py --style org.kde.desktop
```

O supervisor exige cinco IDs exatos, zero skips, falhas ou erros e um recibo
JSON versionado ligado a um token novo por execução. Probe e suíte têm timeouts
independentes; o diretório temporário é removido inclusive quando um filho falha
ou expira.

Não acrescente `test_calendar` a um comando `unittest` compartilhado. Uma
execução direta o ignora com a indicação do runner, sem mudar XDG ou D-Bus no
processo importador. As demais suítes conservam seus próprios contratos e são
executadas separadamente; casos que exigem TaskManager/seat não são qualificados
por este runner offscreen.

O contrato foi conferido no
[`EventPluginsManager` do Plasma Workspace 6.7.5](https://github.com/KDE/plasma-workspace/blob/v6.7.5/components/calendar/eventpluginsmanager.cpp)
e no
[`pimevents` do kdepim-addons 26.08.1](https://github.com/KDE/kdepim-addons/blob/v26.08.1/plugins/plasma/pimeventsplugin/pimeventsplugin.cpp).
O tratamento visual acompanha o
[`MonthView` 6.7.5](https://github.com/KDE/plasma-workspace/blob/v6.7.5/components/calendar/qml/MonthView.qml),
o [`DayDelegate` 6.7.5](https://github.com/KDE/plasma-workspace/blob/v6.7.5/components/calendar/qml/DayDelegate.qml)
e as propriedades anexadas do
[`PlatformTheme` Kirigami 6.30.0](https://github.com/KDE/kirigami/blob/v6.30.0/src/platform/platformtheme.h).
