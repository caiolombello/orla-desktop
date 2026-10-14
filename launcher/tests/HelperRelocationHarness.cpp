#include <QDBusConnectionInterface>
#include <QDBusReply>
#include <QFileInfo>
#include <QDir>
#include <QRegularExpression>
#include <QTimer>
#include <cstdio>
#include <memory>

// The owned driver exercises the production entry point and its actual controllers.
#define main orlaLauncherMain
#include "../main.cpp"
#undef main

namespace {
void installHelperDriver()
{
    const auto bus = QDBusConnection::sessionBus();
    const QDBusReply<QString> id = bus.interface() ? bus.interface()->call(QStringLiteral("GetId")) : QDBusReply<QString>();
    if (!id.isValid() || id.value() != qEnvironmentVariable("ORLA_EXPECTED_PRIVATE_BUS_ID"))
        qFatal("Helper relocation harness requires the verified private test bus");
    auto stage = std::make_shared<int>(0);
    auto *timer = new QTimer(QCoreApplication::instance());
    timer->setInterval(10);
    QObject::connect(timer, &QTimer::timeout, [timer, stage] {
        QQuickWindow *window = nullptr;
        for (QWindow *candidate : QGuiApplication::allWindows())
            if (candidate->objectName() == QStringLiteral("launcherWindow")) window = qobject_cast<QQuickWindow *>(candidate);
        auto *context = window ? QQmlEngine::contextForObject(window) : nullptr;
        if (!context) return;
        auto *ai = qobject_cast<AiProviderController *>(context->contextProperty(QStringLiteral("aiProviders")).value<QObject *>());
        auto *text = qobject_cast<AiTextController *>(context->contextProperty(QStringLiteral("aiText")).value<QObject *>());
        auto *steam = qobject_cast<SteamProviderController *>(context->contextProperty(QStringLiteral("steamProvider")).value<QObject *>());
        auto *session = qobject_cast<WindowSession *>(context->contextProperty(QStringLiteral("windowSession")).value<QObject *>());
        if (!ai || !text || !steam || !session) return;
        if (*stage == 0) {
            const QString receipts = QFileInfo(qEnvironmentVariable("ORLA_TEST_HELPER_ROOT")).dir().filePath(QStringLiteral("receipts"));
            if (ai->busy() || text->busy() || steam->busy()
                || !QDir(receipts).entryList(QDir::AllEntries | QDir::NoDotAndDotDot).isEmpty()) {
                QCoreApplication::exit(13); return;
            }
            *stage = 1;
            ai->discover();
            text->generate(QStringLiteral("owned-relocation"), QStringLiteral("summarize"), QVariant(),
                           QStringLiteral("owned input"), QStringLiteral("owned-model"), QStringLiteral("127.0.0.1"), 11434, true);
            steam->scan({QStringLiteral("native=") + qEnvironmentVariable("ORLA_TEST_HELPER_ROOT") + QStringLiteral("/test-root")});
            return;
        }
        if (ai->busy() || text->busy() || steam->busy()) return;
        const QString mode = qEnvironmentVariable("ORLA_TEST_HELPER_MODE");
        const bool missingAi = mode == QStringLiteral("missing") || mode == QStringLiteral("empty") || mode == QStringLiteral("relative");
        const bool aiOk = missingAi ? ai->errorCode() == QStringLiteral("helper_unavailable")
                                   : ai->status() == QStringLiteral("report_available") && ai->providers().size() == 5;
        const bool textOk = missingAi ? text->errorCode() == QStringLiteral("helper_unavailable")
                                     : text->status() == QStringLiteral("completed") && text->output() == QStringLiteral("owned closure");
        const bool steamOk = mode == QStringLiteral("missing") ? steam->errorCode() == QStringLiteral("helper_unavailable")
                                                              : steam->status() == QStringLiteral("absent") && steam->apps().isEmpty();
        if (!aiOk || !textOk || !steamOk) {
            std::fprintf(stderr, "ORLA_HELPER_RESULT_FAILED ai=%s/%s text=%s/%s steam=%s/%s\n",
                         ai->status().toUtf8().constData(), ai->errorCode().toUtf8().constData(),
                         text->status().toUtf8().constData(), text->errorCode().toUtf8().constData(),
                         steam->status().toUtf8().constData(), steam->errorCode().toUtf8().constData());
            QCoreApplication::exit(11); return;
        }
        timer->stop();
        *stage = 2;
        std::puts("ORLA_HELPER_RESULTS_SETTLED");
        std::fflush(stdout);
        session->requestQuit();
    });
    QObject::connect(QCoreApplication::instance(), &QCoreApplication::aboutToQuit, [stage] {
        std::printf("ORLA_HELPER_EXIT settled=%d\n", *stage == 2);
        std::fflush(stdout);
    });
    timer->start();
    QTimer::singleShot(1500, QCoreApplication::instance(), [] { QCoreApplication::exit(12); });
}
}
Q_COREAPP_STARTUP_FUNCTION(installHelperDriver)

int main(int argc, char **argv)
{
    // On baseline RED, absolute Source defaults refuse BEFORE any production controller/action.
    if (!QStringLiteral(ORLA_AI_HELPER_PATH).isEmpty() || !QStringLiteral(ORLA_AI_TEXT_HELPER_PATH).isEmpty()
        || !QStringLiteral(ORLA_STEAM_HELPER_PATH).isEmpty()) {
        std::puts("ORLA_HELPER_UNSAFE_COMPILED_OVERRIDE");
        return 3;
    }
    const QString root = qEnvironmentVariable("ORLA_TEST_HELPER_ROOT");
    const QString mode = qEnvironmentVariable("ORLA_TEST_HELPER_MODE");
    const QRegularExpression privateAddress(QStringLiteral("^unix:abstract=orla-test-[0-9a-f]{32},guid=[0-9a-f]{32}$"));
    const QStringList modes{QStringLiteral("relocated"), QStringLiteral("empty"), QStringLiteral("relative"),
                            QStringLiteral("override"), QStringLiteral("missing")};
    if (qEnvironmentVariable("QT_QPA_PLATFORM") != QStringLiteral("offscreen")
        || qEnvironmentVariable("QT_QUICK_BACKEND") != QStringLiteral("software")
        || !privateAddress.match(qEnvironmentVariable("DBUS_SESSION_BUS_ADDRESS")).hasMatch()
        || qEnvironmentVariable("ORLA_EXPECTED_PRIVATE_BUS_ID").isEmpty() || !modes.contains(mode)
        || !QDir::isAbsolutePath(root) || QFileInfo(root).canonicalFilePath() != root
        || QFileInfo(QString::fromLocal8Bit(argv[0])).canonicalFilePath() != root + QStringLiteral("/bin/owned-helper-harness")) return 3;
    QStringList expected{QString::fromLocal8Bit(argv[0]), QStringLiteral("--no-global-shortcut")};
    if (mode == QStringLiteral("empty")) expected << QStringLiteral("--ai-helper=") << QStringLiteral("--ai-text-helper=");
    if (mode == QStringLiteral("relative")) expected << QStringLiteral("--ai-helper=libexec/ai.py") << QStringLiteral("--ai-text-helper=libexec/ai_text_ollama.py");
    if (mode == QStringLiteral("override")) expected << QStringLiteral("--ai-helper=") + root + QStringLiteral("/libexec/ai-override.py")
                                                   << QStringLiteral("--ai-text-helper=") + root + QStringLiteral("/libexec/text-override.py");
    QStringList actual;
    for (int i = 0; i < argc; ++i) actual << QString::fromLocal8Bit(argv[i]);
    if (actual != expected) return 3;
    return orlaLauncherMain(argc, argv);
}
