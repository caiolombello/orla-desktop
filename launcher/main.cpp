#include <QApplication>
#include <QCommandLineParser>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickWindow>
#include "LauncherController.h"
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
    parser.setApplicationDescription(QStringLiteral("Orla Launcher opcional: aplicativos e calculadora locais via KRunner."));
    parser.addHelpOption();
    parser.addVersionOption();
    parser.addOption({QStringLiteral("no-global-shortcut"), QStringLiteral("Não registrar atalho; Escape encerra o processo.")});
    parser.addOption({QStringLiteral("shortcut"), QStringLiteral("Atalho temporário disponível, sem substituir bindings."),
                      QStringLiteral("combinação"), QStringLiteral("Ctrl+Alt+Meta+O")});
    parser.process(app);
    LauncherController controller;
    QQmlApplicationEngine engine;
    QObject::connect(&engine, &QQmlApplicationEngine::quit, &app, &QCoreApplication::quit);
    engine.rootContext()->setContextProperty(QStringLiteral("launcher"), &controller);
    // A window session is attached after QML creation; initial content is usable without a shortcut.
    engine.rootContext()->setContextProperty(QStringLiteral("windowSession"), QVariant::fromValue<QObject *>(nullptr));
    engine.load(QUrl(QStringLiteral("qrc:/orla/Launcher.qml")));
    if (engine.rootObjects().isEmpty()) return 1;
    auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
    if (!window) return 1;
    WindowSession session(&controller, window, !parser.isSet(QStringLiteral("no-global-shortcut")),
                          parser.value(QStringLiteral("shortcut")));
    engine.rootContext()->setContextProperty(QStringLiteral("windowSession"), &session);
    return app.exec();
}
