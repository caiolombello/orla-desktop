#pragma once

#include <QString>

// Private runtime layout shared by the entry point and its owned tests.
namespace OrlaHelpers {
enum class Kind { Ai, AiText, Steam };
QString resolve(Kind kind, const QString &applicationDirectory, const QString &configuredOverride = {});
}
