#pragma once

#include <QObject>
#include <QAction>
#include <QPointer>
#include <QQuickWindow>

class LauncherController;
class WindowSession final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString shortcutText READ shortcutText NOTIFY shortcutTextChanged)
    Q_PROPERTY(QString notice READ notice NOTIFY noticeChanged)
public:
    enum class ShortcutMode { Temporary, Managed };
    WindowSession(LauncherController *controller, QQuickWindow *window, bool useShortcut, const QString &key,
                  QObject *parent = nullptr, ShortcutMode mode = ShortcutMode::Temporary);
    ~WindowSession() override;
    QString shortcutText() const { return m_shortcutText; }
    QString notice() const { return m_notice; }
    void requestQuit();
    // Ask the compositor to blur behind the rounded glass panel drawn by QML.
    // An empty rect turns the blur off. Unsupported compositors simply ignore it.
    Q_INVOKABLE void setBlurRegion(const QRectF &rect, qreal radius);
Q_SIGNALS:
    void shortcutTextChanged();
    void noticeChanged();
private:
    friend class UiTests;
    void showFromShortcut();
    void dismiss();
    void setNotice(const QString &notice);
    void refreshShortcut();
    void deactivateShortcut();
    void shortcutUnavailable(const QString &notice);
    QPointer<QQuickWindow> m_window;
    QPointer<QWindow> m_returnWindow;
    LauncherController *m_controller;
    QAction m_action;
    QString m_shortcutText;
    QString m_notice;
    ShortcutMode m_mode;
    quint64 m_activationGeneration = 0;
    bool m_registered = false;
    bool m_deactivated = false;
    bool m_quitRequested = false;
};
