#include "HelperPaths.h"

#include <QDir>

QString OrlaHelpers::resolve(Kind kind, const QString &applicationDirectory, const QString &configuredOverride)
{
    if (!configuredOverride.isEmpty()) return configuredOverride;
    QString filename;
    switch (kind) {
    case Kind::Ai: filename = QStringLiteral("ai.py"); break;
    case Kind::AiText: filename = QStringLiteral("ai_text_ollama.py"); break;
    case Kind::Steam: filename = QStringLiteral("steam.py"); break;
    }
    // Cwd and the Source checkout never participate in installed helper lookup.
    if (!QDir::isAbsolutePath(applicationDirectory) || filename.isEmpty()) return {};
    return QDir::cleanPath(QDir(applicationDirectory).filePath(QStringLiteral("../libexec/") + filename));
}
