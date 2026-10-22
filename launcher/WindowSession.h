#pragma once

#include <QObject>
#include <QAction>
#include <QPointer>
#include <QQuickWindow>

class LauncherController;
class WindowSession final : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QString shortcutText READ shortcutText CONSTANT)
    Q_PROPERTY(QString notice READ notice NOTIFY noticeChanged)
public:
    WindowSession(LauncherController *controller, QQuickWindow *window, bool useShortcut, const QString &key, QObject *parent = nullptr);
    ~WindowSession() override;
    QString shortcutText() const { return m_shortcutText; }
    QString notice() const { return m_notice; }
    // Ask the compositor to blur behind the rounded glass panel drawn by QML.
    // An empty rect turns the blur off. Unsupported compositors simply ignore it.
    Q_INVOKABLE void setBlurRegion(const QRectF &rect, qreal radius);
Q_SIGNALS:
    void noticeChanged();
private:
    friend class UiTests;
    void showFromShortcut();
    void dismiss();
    void setNotice(const QString &notice);
    QPointer<QQuickWindow> m_window;
    QPointer<QWindow> m_returnWindow;
    LauncherController *m_controller;
    QAction m_action;
    QString m_shortcutText;
    QString m_notice;
    quint64 m_activationGeneration = 0;
    bool m_registered = false;
};
