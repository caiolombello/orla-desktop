#include <QtTest>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickWindow>
#include <QQuickItem>
#include <QDir>
#include "LauncherController.h"
#include "BusChecks.h"

// Synthetic Qt key events verify handlers only; they do not qualify Wayland/global-shortcut focus.
class UiTests final : public QObject
{
    Q_OBJECT
private Q_SLOTS:
    void initTestCase() { verifyPrivateTestBus(); }
    void ownWindowRendersResultsWithoutExecuting()
    {
        LauncherController controller;
        QQmlApplicationEngine engine;
        engine.rootContext()->setContextProperty("launcher", &controller);
        engine.rootContext()->setContextProperty("windowSession", QVariant::fromValue<QObject *>(nullptr));
        engine.load(QUrl(QStringLiteral("qrc:/orla/Launcher.qml")));
        QCOMPARE(engine.rootObjects().size(), 1);
        auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
        QVERIFY(window);
        QVERIFY(QTest::qWaitForWindowExposed(window));
        const QString capture = qEnvironmentVariable("ORLA_UI_CAPTURE_DIR");
        const auto snapshot = [&](const QString &name) {
            QTest::qWait(100);
            const QImage image = window->grabWindow();
            QVERIFY(!image.isNull());
            if (!capture.isEmpty()) QVERIFY(image.save(QDir(capture).filePath(name + QStringLiteral(".png"))));
        };
        snapshot(QStringLiteral("idle"));
        controller.setQuery(QStringLiteral("2+2"));
        QTRY_COMPARE_WITH_TIMEOUT(controller.status(), QStringLiteral("ready"), 5000);
        QCOMPARE(controller.rows().first().toMap().value("title").toString(), QStringLiteral("4"));
        QVERIFY(!controller.rows().first().toMap().value("actions").toList().isEmpty());
        snapshot(QStringLiteral("calculator"));
        window->resize(440, 380);
        snapshot(QStringLiteral("calculator-narrow"));
        controller.setQuery(QStringLiteral("OrlaNoResultOwnedNonexistent573849"));
        QTRY_COMPARE_WITH_TIMEOUT(controller.status(), QStringLiteral("empty"), 5000);
        snapshot(QStringLiteral("empty"));
        controller.setQuery(QString(513, QLatin1Char('x')));
        QCOMPARE(controller.status(), QStringLiteral("error"));
        snapshot(QStringLiteral("error"));
        controller.dismiss();
    }
    void searchKeyboardAndEscape()
    {
        LauncherController controller;
        QQmlApplicationEngine engine;
        engine.rootContext()->setContextProperty("launcher", &controller);
        engine.rootContext()->setContextProperty("windowSession", QVariant::fromValue<QObject *>(nullptr));
        engine.load(QUrl(QStringLiteral("qrc:/orla/Launcher.qml")));
        QCOMPARE(engine.rootObjects().size(), 1);
        auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().first());
        QVERIFY(window);
        auto *search = window->findChild<QQuickItem *>(QStringLiteral("searchInput"));
        QVERIFY(search);
        search->forceActiveFocus();
        QTest::keyClick(window, Qt::Key_2);
        QTest::keyClick(window, Qt::Key_Plus);
        QTest::keyClick(window, Qt::Key_2);
        QTRY_COMPARE_WITH_TIMEOUT(controller.status(), QStringLiteral("ready"), 5000);
        QCOMPARE(controller.rows().first().toMap().value("title").toString(), QStringLiteral("4"));
        QTest::keyClick(window, Qt::Key_Down);
        QCOMPARE(controller.selectedIndex(), 0);
        QTest::keyClick(window, Qt::Key_Up);
        QCOMPARE(controller.selectedIndex(), 0);
        QTest::keyClick(window, Qt::Key_Return);
        QCOMPARE(controller.query(), QStringLiteral("4"));
        QSignalSpy closed(&controller, &LauncherController::closeRequested);
        QTest::keyClick(window, Qt::Key_Escape);
        QCOMPARE(closed.count(), 1);
        QVERIFY(controller.rows().isEmpty());
    }
};
QTEST_MAIN(UiTests)
#include "UiTests.moc"
