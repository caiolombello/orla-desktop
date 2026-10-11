#include <QtTest>
#include "LauncherController.h"
#include "BusChecks.h"

class LauncherTests final : public QObject
{
    Q_OBJECT
private Q_SLOTS:
    void initTestCase() { verifyPrivateTestBus(); }
    void editingClearsOldResultsBeforeReplacementArrives()
    {
        LauncherController launcher;
        launcher.setQuery(QStringLiteral("2+2"));
        QTRY_VERIFY_WITH_TIMEOUT(!launcher.rows().isEmpty() && launcher.status() == "ready", 5000);
        QCOMPARE(launcher.rows().first().toMap().value("title").toString(), QStringLiteral("4"));
        launcher.setQuery(QStringLiteral("9*9"));
        QVERIFY2(launcher.rows().isEmpty(), "Old result must disappear synchronously when typing a replacement");
        QTRY_VERIFY_WITH_TIMEOUT(!launcher.rows().isEmpty() && launcher.status() == "ready", 5000);
        QCOMPARE(launcher.rows().first().toMap().value("title").toString(), QStringLiteral("81"));
    }
    void oversizedInputReportsRecoverableErrorWithoutSearching()
    {
        LauncherController launcher;
        launcher.setQuery(QString(513, QLatin1Char('x')));
        QCOMPARE(launcher.status(), QStringLiteral("error"));
        QVERIFY(!launcher.error().isEmpty());
        QVERIFY(launcher.rows().isEmpty());
        launcher.setQuery(QStringLiteral("2+2"));
        QTRY_COMPARE_WITH_TIMEOUT(launcher.status(), QStringLiteral("ready"), 5000);
        QVERIFY(launcher.error().isEmpty());
    }
    void staleExecutionIsRejectedEvenWhenTheSameQueryReturns()
    {
        LauncherController launcher;
        launcher.setQuery(QStringLiteral("2+2"));
        QTRY_COMPARE_WITH_TIMEOUT(launcher.status(), QStringLiteral("ready"), 5000);
        const auto oldGeneration = launcher.generation();
        const auto oldId = launcher.rows().first().toMap().value("id").toString();
        launcher.setQuery(QStringLiteral("9*9"));
        QVERIFY(!launcher.execute(0, oldGeneration, oldId));
        launcher.setQuery(QStringLiteral("2+2"));
        QTRY_COMPARE_WITH_TIMEOUT(launcher.status(), QStringLiteral("ready"), 5000);
        QVERIFY(!launcher.execute(0, oldGeneration, oldId));
        QCOMPARE(launcher.query(), QStringLiteral("2+2"));
        QVERIFY(!launcher.execute(0, launcher.generation(), QStringLiteral("different-result")));
        QVERIFY(!launcher.execute(0, launcher.generation(), oldId, QStringLiteral("nonexistent-action")));
    }
    void escapeCancelsBothDebouncedAndInFlightResults()
    {
        LauncherController launcher;
        QSignalSpy closed(&launcher, &LauncherController::closeRequested);
        launcher.setQuery(QStringLiteral("2+2"));
        launcher.dismiss();
        QTest::qWait(150);
        QCOMPARE(closed.count(), 1);
        QCOMPARE(launcher.status(), QStringLiteral("idle"));
        QVERIFY(launcher.rows().isEmpty());
        launcher.setQuery(QStringLiteral("9*9"));
        QTest::qWait(65);
        launcher.dismiss();
        QTest::qWait(250);
        QCOMPARE(closed.count(), 2);
        QVERIFY(launcher.rows().isEmpty());
        QVERIFY(!launcher.executeSelected());
    }
    void appResultsOnlyRunOwnedFixtureAfterExplicitSelection()
    {
        const auto receipt = qEnvironmentVariable("ORLA_TEST_RECEIPT");
        if (receipt.isEmpty()) QSKIP("Owned desktop fixture was not provided; no installed app is launched");
        QFile::remove(receipt);
        LauncherController launcher;
        launcher.setQuery(QStringLiteral("OrlaOwnedLauncherFixture"));
        QTRY_COMPARE_WITH_TIMEOUT(launcher.status(), QStringLiteral("ready"), 5000);
        QCOMPARE(launcher.rows().size(), 1);
        const auto row = launcher.rows().first().toMap();
        QCOMPARE(row.value("kind").toString(), QStringLiteral("app"));
        QCOMPARE(row.value("title").toString(), QStringLiteral("OrlaOwnedLauncherFixture"));
        QVERIFY(!QFile::exists(receipt)); // Typing never executes an app.
        QVERIFY(!launcher.execute(1, launcher.generation(), row.value("id").toString()));
        QVERIFY(!QFile::exists(receipt));
        QVERIFY(launcher.executeSelected());
        QTRY_VERIFY_WITH_TIMEOUT(QFile::exists(receipt), 5000);
        QFile file(receipt);
        QVERIFY(file.open(QIODevice::ReadOnly));
        QCOMPARE(file.readAll(), QByteArray("owned-launcher-fixture\n"));
        QVERIFY(launcher.rows().isEmpty());
    }
};
QTEST_MAIN(LauncherTests)
#include "LauncherTests.moc"
