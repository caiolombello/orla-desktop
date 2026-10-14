#pragma once
#include <QString>
#include <QVariantList>

// Private launcher preferences. Reads never create or repair files.
class AliasStore final
{
public:
    explicit AliasStore(const QString &path = QString());
    bool reload();
    QVariantList entries() const { return m_entries; }
    QString revision() const { return m_revision; }
    QString error() const { return m_readError.isEmpty() ? m_commandError : m_readError; }
    bool writable() const { return m_readError.isEmpty(); }
    bool save(const QString &alias, const QString &appId, const QString &expectedRevision);
    bool rename(const QString &oldAlias, const QString &appId, const QString &newAlias, const QString &expectedRevision);
    bool remove(const QString &alias, const QString &appId, const QString &expectedRevision);
    static QString key(const QString &alias);
    static bool validAppId(const QString &appId);
private:
    bool publish(const QVariantList &entries, const QString &expectedRevision);
    bool fail(const QString &message);
    QString m_path, m_revision, m_readError, m_commandError;
    QVariantList m_entries;
};
