#include <QCoreApplication>
#include <QFile>
int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    if (argc != 2) return 2;
    QFile receipt(QString::fromLocal8Bit(argv[1]));
    if (!receipt.open(QIODevice::WriteOnly | QIODevice::NewOnly)) return 3;
    constexpr char marker[] = "owned-launcher-fixture\n";
    return receipt.write(marker, sizeof(marker) - 1) == sizeof(marker) - 1 ? 0 : 4;
}
