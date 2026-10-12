#include <QApplication>
#include <QCommandLineParser>
#include <QDebug>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickWindow>
#include "AiProviderController.h"
#include "AiTextController.h"
#include "LauncherController.h"
#include "SteamProviderController.h"
#include "WindowSession.h"

int main(int argc, char **argv)
{
    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("orla-launcher-session-%1").arg(QCoreApplication::applicationPid()));
    app.setApplicationDisplayName(QStringLiteral("Orla Launcher"));
    app.setApplicationVersion(QStringLiteral("0.1.0"));
    app.setDesktopFileName(QStringLiteral("org.orla.Launcher"));
    app.setQuitOnLastWindowClosed(false);
    QCommandLineParser parser;
    parser.setApplicationDescription(QStringLiteral("Orla Launcher opcional: aplicativos, calculadora e inventário Steam local explícito."));
    parser.addHelpOption();
    parser.addVersionOption();
    parser.addOption({QStringLiteral("no-global-shortcut"), QStringLiteral("Não registrar atalho; Escape encerra o processo.")});
    parser.addOption({QStringLiteral("start-hidden"), QStringLiteral("Iniciar oculto somente quando o atalho global estiver registrado.")});
    parser.addOption({QStringLiteral("shortcut"), QStringLiteral("Atalho temporário disponível, sem substituir bindings."),
                      QStringLiteral("combinação"), QStringLiteral("Ctrl+Alt+Meta+O")});
    parser.addOption({QStringLiteral("ai-python"), QStringLiteral("Interpretador Python absoluto para o helper limitado de IA."),
                      QStringLiteral("caminho"), QStringLiteral(ORLA_AI_PYTHON_PATH)});
    parser.addOption({QStringLiteral("ai-helper"), QStringLiteral("Helper limitado de IA absoluto; ausente significa indisponível."),
                      QStringLiteral("caminho"), QStringLiteral(ORLA_AI_HELPER_PATH)});
    parser.addOption({QStringLiteral("ai-text-helper"), QStringLiteral("Helper operacional de texto local absoluto."),
                      QStringLiteral("caminho"), QStringLiteral(ORLA_AI_TEXT_HELPER_PATH)});
    parser.process(app);
    AiProviderController aiController(parser.value(QStringLiteral("ai-python")),
                                      parser.value(QStringLiteral("ai-helper")));
    AiTextController aiTextController(parser.value(QStringLiteral("ai-python")),
                                      parser.value(QStringLiteral("ai-text-helper")));
    SteamProviderController steamController(QStringLiteral(ORLA_STEAM_PYTHON_PATH),
                                            QStringLiteral(ORLA_STEAM_HELPER_PATH));
    LauncherController controller(&steamController);
    QQmlApplicationEngine engine;
    QObject::connect(&engine, &QQmlApplicationEngine::quit, &app, &QCoreApplication::quit);
    engine.rootContext()->setContextProperty(QStringLiteral("launcher"), &controller);
    engine.rootContext()->setContextProperty(QStringLiteral("aiProviders"), &aiController);
    engine.rootContext()->setContextProperty(QStringLiteral("aiText"), &aiTextController);
    engine.rootContext()->setContextProperty(QStringLiteral("steamProvider"), &steamController);
    // A window session is attached after QML creation; initial content is usable without a shortcut.
    engine.rootContext()->setContextProperty(QStringLiteral("windowSession"), QVariant::fromValue<QObject *>(nullptr));
    engine.load(QUrl(QStringLiteral("qrc:/orla/Launcher.qml")));
    if (engine.rootObjects().isEmpty()) return 1;
    auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
    if (!window) return 1;
    WindowSession session(&controller, window, !parser.isSet(QStringLiteral("no-global-shortcut")),
                          parser.value(QStringLiteral("shortcut")));
    QObject::connect(&controller, &LauncherController::closeRequested, &aiController,
                     &AiProviderController::cancelAll);
    QObject::connect(&controller, &LauncherController::closeRequested, &aiTextController,
                     &AiTextController::cancelAll);
    QObject::connect(&controller, &LauncherController::closeRequested, &steamController,
                     &SteamProviderController::cancelAll);
    engine.rootContext()->setContextProperty(QStringLiteral("windowSession"), &session);
    if (parser.isSet(QStringLiteral("start-hidden")) && !session.shortcutText().isEmpty()) {
        window->hide();
    }
    qInfo().noquote() << "Orla Launcher ready; visible=" << window->isVisible()
                     << "; shortcut=" << session.shortcutText();
    return app.exec();
}
