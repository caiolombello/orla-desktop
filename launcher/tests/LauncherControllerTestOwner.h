#pragma once

#include "LauncherController.h"
#include <KRunner/AbstractRunner>
#include <QElapsedTimer>
#include <QPointer>
#include <QThread>
#include <QtTest>
#include <memory>

// Test fixtures own one manager at a time. Runner destruction is asynchronous;
// join only their threads and observe their deletion before the next manager.
class LauncherControllerTestOwner final
{
public:
    explicit LauncherControllerTestOwner(SteamProviderController *steam = nullptr)
    {
        if (s_activeOwner || s_teardownFailed)
            qFatal("A previous test controller's owned runners have not been destroyed");
        s_activeOwner = true;
        m_controller = std::make_unique<LauncherController>(steam);
        // ResultsModel normally preloads these same allowed runners on a zero
        // timer. Eager test-only loading captures their identities even on an
        // early assertion return, without creating cleanup-time runners.
        for (auto *runner : m_controller->m_model.runnerManager()->runners())
            m_runners.append(runner);
    }

    ~LauncherControllerTestOwner()
    {
        QElapsedTimer elapsed;
        elapsed.start();
        const QDeadlineTimer deadline(500, Qt::PreciseTimer);
        QList<QPointer<QThread>> threads;
        for (const auto &runner : m_runners) {
            if (!runner) continue;
            QThread *thread = runner->thread();
            if (thread != QThread::currentThread() && !threads.contains(thread))
                threads.append(thread);
        }
        m_controller.reset();
        // finished/runner deletion precede TLS cleanup. Join before pumping
        // DeferredDelete, which can otherwise destroy the QThread QObject.
        for (const auto &thread : threads) {
            if (!thread || !thread->wait(deadline)) {
                s_teardownFailed = true;
                QTest::qFail("Owned runner thread join exceeded the 500 ms test deadline", __FILE__, __LINE__);
                return;
            }
        }
        const bool destroyed = QTest::qWaitFor([this] {
            for (const auto &runner : m_runners) if (!runner.isNull()) return false;
            return true;
        }, deadline);
        qInfo() << "ORLA_TEST_RUNNER_TEARDOWN" << "captured=" << m_runners.size()
                << "destroyed=" << destroyed << "elapsed_ms=" << elapsed.elapsed();
        if (!destroyed) {
            s_teardownFailed = true;
            QTest::qFail("Owned runner destruction exceeded the 500 ms test deadline", __FILE__, __LINE__);
            return;
        }
        s_activeOwner = false;
    }

    LauncherController &controller() const { return *m_controller; }
    QList<QPointer<KRunner::AbstractRunner>> observedRunners() const { return m_runners; }

private:
    inline static bool s_activeOwner = false;
    inline static bool s_teardownFailed = false;
    std::unique_ptr<LauncherController> m_controller;
    QList<QPointer<KRunner::AbstractRunner>> m_runners;
};
