#pragma once
#include <QtTest>
#include <QDBusConnection>
#include <QDBusConnectionInterface>
#include <QDBusReply>

// Fail before any RunnerManager/ServiceRunner is constructed when not run through the private wrapper.
inline void verifyPrivateTestBus()
{
    QVERIFY2(qEnvironmentVariable("DBUS_SESSION_BUS_ADDRESS").startsWith(QStringLiteral("unix:abstract=orla-test-")),
             "Run this test through CTest or tests/run_isolated.py; personal session bus is forbidden");
    const QString expected = qEnvironmentVariable("ORLA_EXPECTED_PRIVATE_BUS_ID");
    QVERIFY(!expected.isEmpty());
    const auto connection = QDBusConnection::sessionBus();
    QVERIFY(connection.isConnected());
    QVERIFY(connection.interface());
    const QDBusReply<QString> actual = connection.interface()->call(QStringLiteral("GetId"));
    QVERIFY(actual.isValid());
    QCOMPARE(actual.value(), expected);
}
