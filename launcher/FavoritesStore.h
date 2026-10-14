#pragma once
#include <QString>
#include <QStringList>

// Private launcher preferences. Reads never create or repair files.
class FavoritesStore final
{
public:
    explicit FavoritesStore(const QString &path = QString());
    bool reload();
    QStringList entries() const { return m_entries; }
    QString revision() const { return m_revision; }
    QString error() const { return m_readError.isEmpty() ? m_commandError : m_readError; }
    bool writable() const { return m_readError.isEmpty(); }
    bool pin(const QString &appId, const QString &expectedRevision);
    bool unpin(const QString &appId, const QString &expectedRevision);
private:
    bool publish(const QStringList &entries, const QString &expectedRevision);
    bool fail(const QString &message);
    QString m_path, m_revision, m_readError, m_commandError;
    QStringList m_entries;
};
