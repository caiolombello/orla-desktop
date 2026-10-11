#include <QtTest>
#include "LauncherController.h"
#include "SteamProviderController.h"
#include "BusChecks.h"

namespace {
QString writeSteamHelper(QTemporaryDir &directory)
{
    const QByteArray document = R"({"apps":[{"appid":"42","library":"library-0","name":"Synthetic Steam Game","ownership":"unknown","source":"local_manifest","status":"installed_candidate"}],"connection":"unknown","errors":[],"libraries":[{"id":"library-0","kind":"native","root":"root-0","status":"available"}],"ownership":"unknown","roots":[{"id":"root-0","kind":"native","status":"available"}],"schema_version":"0.1-experimental","status":"available"})" "\n";
    const QString helper = directory.filePath(QStringLiteral("steam-helper.py"));
    QFile file(helper);
    if (!file.open(QIODevice::WriteOnly)) return {};
    file.write("import base64,sys\nsys.stdout.buffer.write(base64.b64decode('");
    file.write(document.toBase64());
    file.write("'))\n");
    file.close();
    return helper;
}
}

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

    void steamSearchOnlyOpensTheCurrentExplicitSelection()
    {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        QList<QUrl> opened;
        SteamProviderController steam(QStringLiteral(ORLA_TEST_PYTHON_EXECUTABLE),
            writeSteamHelper(directory), [&opened](const QUrl &url) { opened.append(url); return true; });
        LauncherController launcher(&steam);
        steam.scan({QStringLiteral("native=/synthetic/root")});
        QTRY_COMPARE_WITH_TIMEOUT(steam.status(), QStringLiteral("available"), 3000);

        launcher.setQuery(QStringLiteral("Synthetic Steam"));
        QTRY_VERIFY_WITH_TIMEOUT(launcher.status() == QStringLiteral("ready")
                                 && !launcher.rows().isEmpty(), 5000);
        int steamRow = -1;
        for (int row = 0; row < launcher.rows().size(); ++row) {
            if (launcher.rows()[row].toMap().value(QStringLiteral("kind")).toString()
                == QStringLiteral("steam")) steamRow = row;
        }
        QVERIFY(steamRow >= 0);
        launcher.select(steamRow);
        const QVariantMap old = launcher.rows()[steamRow].toMap();
        QVERIFY(opened.isEmpty());

        launcher.setQuery(QStringLiteral("different"));
        QVERIFY(!launcher.execute(steamRow, old.value(QStringLiteral("generation")).toULongLong(),
                                  old.value(QStringLiteral("id")).toString()));
        QVERIFY(opened.isEmpty());

        launcher.setQuery(QStringLiteral("Synthetic Steam"));
        QTRY_VERIFY_WITH_TIMEOUT(launcher.status() == QStringLiteral("ready"), 5000);
        for (int row = 0; row < launcher.rows().size(); ++row) {
            const QVariantMap current = launcher.rows()[row].toMap();
            if (current.value(QStringLiteral("kind")).toString() != QStringLiteral("steam")) continue;
            launcher.select(row);
            QVERIFY(launcher.execute(row, current.value(QStringLiteral("generation")).toULongLong(),
                                     current.value(QStringLiteral("id")).toString()));
            break;
        }
        QCOMPARE(opened, QList<QUrl>{QUrl(QStringLiteral("steam://rungameid/42"))});
    }
};
QTEST_MAIN(LauncherTests)
#include "LauncherTests.moc"
