#pragma once

#include "LauncherController.h"
#include <KRunner/AbstractRunner>
#include <QElapsedTimer>
#include <QCoreApplication>
#include <QDebug>
#include <QPointer>
#include <QThread>
#include <QtTest>
#include <memory>
#include <atomic>
#include <chrono>

// Test fixtures own one manager at a time. Runner destruction is asynchronous;
// join only their threads and observe their deletion before the next manager.
class LauncherControllerTestOwner final
{
public:
    explicit LauncherControllerTestOwner(SteamProviderController *steam = nullptr, const QString &aliasPath = QString(), const QString &favoritePath = QString())
    {
        if (s_activeOwner || s_teardownFailed)
            qFatal("A previous test controller's owned runners have not been destroyed");
        s_activeOwner = true;
        m_controller = std::make_unique<LauncherController>(steam, nullptr, aliasPath, favoritePath);
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
        QList<quintptr> threadTags;
        for (const auto &runner : m_runners) {
            if (!runner) continue;
            QThread *thread = runner->thread();
            if (thread != QThread::currentThread() && !threads.contains(thread)) {
                threads.append(thread);
                if (threadTags.size() < 16)
                    threadTags.append(reinterpret_cast<quintptr>(thread));
            }
        }
        QList<std::shared_ptr<RunnerTrace>> traces;
        int observersInstalled = 0, observersExpected = 0, missingMetadata = 0;
        const qsizetype metadataLimit = qMin<qsizetype>(m_runners.size(), 16);
        for (qsizetype index = 0; index < metadataLimit; ++index) {
            const auto &runner = m_runners[index];
            if (!runner) { ++missingMetadata; continue; }
            auto *thread = runner->thread();
            const QString id = runner->id();
            const QString alias = id == QStringLiteral("krunner_services") || id == QStringLiteral("calculator")
                ? id : QStringLiteral("unknown_runner");
            auto trace = std::make_shared<RunnerTrace>(index, alias,
                reinterpret_cast<quintptr>(runner.data()), reinterpret_cast<quintptr>(runner->parent()),
                reinterpret_cast<quintptr>(thread),
                thread ? reinterpret_cast<quintptr>(thread->thread()) : 0,
                thread && thread->isRunning(), thread && thread->isFinished());
            // Observe only: shared data outlives this owner; callbacks never touch QObjects.
            auto *context = QCoreApplication::instance();
            ++observersExpected;
            observersInstalled += bool(QObject::connect(runner.data(), &QObject::destroyed, context, [trace] {
                trace->runnerDestroyedNs.store(monotonicNs(), std::memory_order_relaxed);
            }, Qt::DirectConnection));
            if (thread) {
                observersExpected += 2;
                observersInstalled += bool(QObject::connect(thread, &QThread::finished, context, [trace] {
                    trace->finishedNs.store(monotonicNs(), std::memory_order_relaxed);
                }, Qt::DirectConnection));
                observersInstalled += bool(QObject::connect(thread, &QObject::destroyed, context, [trace] {
                    trace->threadDestroyedNs.store(monotonicNs(), std::memory_order_relaxed);
                }, Qt::DirectConnection));
            } else ++missingMetadata;
            traces.append(trace);
        }
        QList<JoinTrace> joins;
        qsizetype joinCount = 0;
        qint64 resetEnterNs = 0, resetReturnNs = 0, auditEnterNs = 0, auditReturnNs = 0;
        qint64 auditBudgetBeforeMs = 0, auditBudgetAfterMs = 0;
        const quintptr currentThreadTag = reinterpret_cast<quintptr>(QThread::currentThread());
        const auto reportFailure = [&] {
            int lines = 0, bytes = 0, omittedRecords = 0;
            // Reserve one final omission line; only our payload counts, not a logging prefix.
            const auto emitDetail = [&](const QString &line) {
                const int size = line.toUtf8().size() + 1;
                if (lines >= 33 || size > 20 * 1024 - 512 - bytes) { ++omittedRecords; return; }
                qInfo().noquote() << line;
                ++lines; bytes += size;
            };
            QString line;
            {
                QDebug detail(&line);
                detail.noquote() << "ORLA_TEST_RUNNER_FAILURE" << "reset_enter_ns=" << resetEnterNs
                    << "reset_return_ns=" << resetReturnNs << "audit_enter_ns=" << auditEnterNs
                    << "audit_return_ns=" << auditReturnNs << "audit_budget_before_ms=" << auditBudgetBeforeMs
                    << "audit_budget_after_ms=" << auditBudgetAfterMs << "current_thread_tag=" << currentThreadTag
                    << "remaining_ms=" << deadline.remainingTime()
                    << "observers=" << observersInstalled << "expected_observers=" << observersExpected;
            }
            emitDetail(line);
            for (const auto &trace : traces) {
                // Independent observations, not an event-queue or simultaneous-state snapshot.
                const auto finished = trace->finishedNs.load(std::memory_order_relaxed);
                const auto runnerDestroyed = trace->runnerDestroyedNs.load(std::memory_order_relaxed);
                const auto threadDestroyed = trace->threadDestroyedNs.load(std::memory_order_relaxed);
                line.clear();
                {
                    QDebug detail(&line);
                    detail.noquote() << "ORLA_TEST_RUNNER_TRACE" << "index=" << trace->index << "id=" << trace->id
                        << "runner_tag=" << trace->runnerTag << "parent_tag=" << trace->parentTag
                        << "runner_affinity=" << trace->threadTag << "thread_tag=" << trace->threadTag
                        << "thread_object_affinity=" << trace->threadAffinityTag
                        << "running_before=" << trace->runningBefore << "finished_before=" << trace->finishedBefore
                        << "finished_ns=" << finished << "runner_destroyed_ns=" << runnerDestroyed
                        << "thread_destroyed_ns=" << threadDestroyed
                        << "runner_null=" << m_runners[trace->index].isNull();
                }
                emitDetail(line);
            }
            for (const auto &join : joins) {
                line.clear();
                {
                    QDebug detail(&line);
                    detail.noquote() << "ORLA_TEST_RUNNER_JOIN" << "thread_tag=" << join.threadTag
                        << "present=" << join.present << "joined=" << join.joined
                        << "start_ns=" << join.startNs << "end_ns=" << join.endNs
                        << "budget_before_ms=" << join.budgetBeforeMs << "budget_after_ms=" << join.budgetAfterMs;
                }
                emitDetail(line);
            }
            qInfo() << "ORLA_TEST_RUNNER_DIAGNOSTICS_OMITTED"
                    << "runners=" << m_runners.size() - metadataLimit << "missing_metadata=" << missingMetadata
                    << "joins=" << joinCount - joins.size() << "records=" << omittedRecords
                    << "observer_failures=" << observersExpected - observersInstalled;
        };
        resetEnterNs = monotonicNs();
        m_controller.reset();
        resetReturnNs = monotonicNs();
        // finished/runner deletion precede TLS cleanup. Join before pumping
        // DeferredDelete, which can otherwise destroy the QThread QObject.
        for (const auto &thread : threads) {
            const auto index = joinCount++;
            const qint64 begin = monotonicNs(), budgetBefore = deadline.remainingTime();
            const bool present = !thread.isNull();
            const bool joined = present && thread->wait(deadline);
            if (joins.size() < 16)
                joins.append({threadTags[index], begin, monotonicNs(), budgetBefore,
                    deadline.remainingTime(), present, joined});
            if (!joined) {
                s_teardownFailed = true;
                reportFailure();
                QTest::qFail("Owned runner thread join exceeded the 500 ms test deadline", __FILE__, __LINE__);
                return;
            }
        }
        auditEnterNs = monotonicNs();
        auditBudgetBeforeMs = deadline.remainingTime();
        const bool destroyed = QTest::qWaitFor([this] {
            for (const auto &runner : m_runners) if (!runner.isNull()) return false;
            return true;
        }, deadline);
        auditReturnNs = monotonicNs();
        auditBudgetAfterMs = deadline.remainingTime();
        qInfo() << "ORLA_TEST_RUNNER_TEARDOWN" << "captured=" << m_runners.size()
                << "destroyed=" << destroyed << "elapsed_ms=" << elapsed.elapsed();
        if (!destroyed) {
            s_teardownFailed = true;
            reportFailure();
            QTest::qFail("Owned runner destruction exceeded the 500 ms test deadline", __FILE__, __LINE__);
            return;
        }
        s_activeOwner = false;
    }

    LauncherController &controller() const { return *m_controller; }
    QList<QPointer<KRunner::AbstractRunner>> observedRunners() const { return m_runners; }

private:
    static qint64 monotonicNs()
    {
        return std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count();
    }
    struct RunnerTrace {
        RunnerTrace(qsizetype number, const QString &alias, quintptr runner, quintptr parent,
                    quintptr thread, quintptr threadAffinity, bool running, bool finished)
            : index(number), id(alias), runnerTag(runner), parentTag(parent), threadTag(thread),
              threadAffinityTag(threadAffinity), runningBefore(running), finishedBefore(finished) {}
        const qsizetype index;
        const QString id;
        const quintptr runnerTag, parentTag, threadTag, threadAffinityTag;
        const bool runningBefore, finishedBefore;
        std::atomic<qint64> finishedNs{0}, runnerDestroyedNs{0}, threadDestroyedNs{0};
    };
    struct JoinTrace {
        quintptr threadTag;
        qint64 startNs, endNs, budgetBeforeMs, budgetAfterMs;
        bool present, joined;
    };
    inline static bool s_activeOwner = false;
    inline static bool s_teardownFailed = false;
    std::unique_ptr<LauncherController> m_controller;
    QList<QPointer<KRunner::AbstractRunner>> m_runners;
};
