#include "LauncherController.h"
#include <KConfigGroup>
#include <KRunner/AbstractRunner>

LauncherController::LauncherController(QObject *parent)
    : QObject(parent), m_config(QString(), KConfig::SimpleConfig), m_state(QString(), KConfig::SimpleConfig),
      m_model(m_config.group("Plugins"), m_state.group("General"), nullptr)
{
    // Supply anonymous groups to ResultsModel as well: its default constructor opens KRunner's user state.
    m_model.runnerManager()->setHistoryEnabled(false);
    m_model.runnerManager()->setAllowedRunners({QStringLiteral("krunner_services"), QStringLiteral("calculator")});
    m_model.setLimit(32);
    connect(&m_model, &QAbstractItemModel::rowsInserted, this, &LauncherController::refresh);
    connect(&m_model, &QAbstractItemModel::rowsRemoved, this, &LauncherController::refresh);
    connect(&m_model, &QAbstractItemModel::modelReset, this, &LauncherController::refresh);
    connect(&m_model, &QAbstractItemModel::dataChanged, this, &LauncherController::refresh);
    connect(&m_model, &QAbstractItemModel::layoutChanged, this, &LauncherController::refresh);
    connect(&m_model, &KRunner::ResultsModel::queryingChanged, this, &LauncherController::refresh);
    connect(&m_model, &KRunner::ResultsModel::queryStringChangeRequested, this,
            [this](const QString &query, int) { setQuery(query); });
    m_debounce.setSingleShot(true);
    m_debounce.setInterval(60);
    connect(&m_debounce, &QTimer::timeout, this, [this] {
        m_launchedGeneration = m_generation;
        m_model.setQueryString(m_query.trimmed());
        if (m_model.runnerManager()->runners().isEmpty()) {
            m_error = tr("Os runners locais não estão disponíveis. Confira a instalação do Plasma.");
        }
        refresh();
    });
}

QString LauncherController::status() const
{
    if (!m_error.isEmpty()) return QStringLiteral("error");
    if (m_query.trimmed().isEmpty()) return QStringLiteral("idle");
    if (m_debounce.isActive() || m_model.querying()) return QStringLiteral("loading");
    return m_rows.isEmpty() ? QStringLiteral("empty") : QStringLiteral("ready");
}

QString LauncherController::resultId(const QModelIndex &index) const
{
    const auto match = m_model.getQueryMatch(index);
    return match.runner() ? match.runner()->id() + QLatin1Char(':') + match.id() : QString();
}

void LauncherController::refresh()
{
    m_rows.clear();
    if (m_launchedGeneration != m_generation || m_model.queryString() != m_query.trimmed()) {
        emit changed();
        return;
    }
    for (int row = 0; row < m_model.rowCount() && row < 40; ++row) {
        const auto index = m_model.index(row, 0);
        const auto match = m_model.getQueryMatch(index);
        QVariantList actions;
        for (const auto &action : match.actions()) {
            actions.append(QVariantMap{{"id", action.id()}, {"text", action.text()},
                                      {"resultId", resultId(index)}, {"generation", m_generation}, {"row", row}});
        }
        const bool calculator = match.runner() && match.runner()->id() == QStringLiteral("calculator");
        m_rows.append(QVariantMap{{"id", resultId(index)}, {"generation", m_generation}, {"title", m_model.data(index, Qt::DisplayRole)},
                                 {"description", m_model.data(index, KRunner::ResultsModel::SubtextRole)},
                                 {"enabled", m_model.data(index, KRunner::ResultsModel::EnabledRole)},
                                 {"kind", calculator ? QStringLiteral("calculator") : QStringLiteral("app")},
                                 {"source", calculator ? tr("KRunner · Calculadora") : tr("KRunner · Aplicativos")},
                                 {"actions", actions}});
    }
    // Sorting/batches may move rows. Preserve the selected identity, never its old index.
    m_selected = -1;
    for (int row = 0; row < m_rows.size(); ++row) {
        if (m_rows[row].toMap().value("id").toString() == m_selectedId) m_selected = row;
    }
    if (m_selected < 0) {
        m_selectedId.clear();
        for (int row = 0; row < m_rows.size(); ++row) {
            if (m_rows[row].toMap().value("enabled").toBool()) {
                m_selected = row;
                m_selectedId = m_rows[row].toMap().value("id").toString();
                break;
            }
        }
    }
    emit changed();
}

void LauncherController::setQuery(const QString &query)
{
    if (query == m_query) return;
    m_debounce.stop();
    m_query = query;
    ++m_generation;
    m_launchedGeneration = 0;
    m_error.clear();
    m_selected = -1;
    m_selectedId.clear();
    m_rows.clear();
    m_model.clear(); // Cancel the native context before starting another query.
    if (query.size() > 512) m_error = tr("Use uma busca com até 512 caracteres.");
    else if (!query.trimmed().isEmpty()) m_debounce.start();
    emit changed();
}

void LauncherController::select(int row)
{
    if (row < 0 || row >= m_rows.size() || !m_rows[row].toMap().value("enabled").toBool()) return;
    m_selected = row;
    m_selectedId = m_rows[row].toMap().value("id").toString();
    emit changed();
}

void LauncherController::moveSelection(int delta)
{
    if (delta == 0 || m_rows.isEmpty()) return;
    const int direction = delta > 0 ? 1 : -1;
    int row = m_selected;
    for (int tries = 0; tries < m_rows.size(); ++tries) {
        row = (row + direction + m_rows.size()) % m_rows.size();
        if (m_rows[row].toMap().value("enabled").toBool()) { select(row); return; }
    }
}

bool LauncherController::execute(int row, quint64 generation, const QString &id, const QString &actionId)
{
    // Resolve the live index only at the execution boundary. Old QML delegates/callbacks cannot run.
    if (generation != m_generation || m_launchedGeneration != m_generation || status() != QStringLiteral("ready")
        || row < 0 || row >= m_rows.size() || row != m_selected || id.isEmpty() || id != m_selectedId) return false;
    const auto index = m_model.index(row, 0);
    if (!index.isValid() || resultId(index) != id || !m_model.data(index, KRunner::ResultsModel::EnabledRole).toBool()) return false;
    const auto match = m_model.getQueryMatch(index);
    if (!match.runner() || (match.runner()->id() != QStringLiteral("krunner_services")
                           && match.runner()->id() != QStringLiteral("calculator"))) return false;
    int actionIndex = -1;
    if (!actionId.isEmpty()) {
        const auto actions = match.actions();
        for (int i = 0; i < actions.size(); ++i) if (actions[i].id() == actionId) actionIndex = i;
        if (actionIndex < 0) return false;
    }
    const bool close = actionIndex < 0 ? m_model.run(index) : m_model.runAction(index, actionIndex);
    if (close && generation == m_generation) dismiss();
    return true;
}

bool LauncherController::executeSelected()
{
    return execute(m_selected, m_generation, m_selectedId);
}

void LauncherController::dismiss()
{
    // Invalidate outstanding executions even when the input was already empty.
    m_debounce.stop();
    ++m_generation;
    m_launchedGeneration = 0;
    m_query.clear();
    m_rows.clear();
    m_selectedId.clear();
    m_selected = -1;
    m_error.clear();
    m_model.clear();
    emit changed();
    emit closeRequested();
}
