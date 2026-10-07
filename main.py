"""نقطة تشغيل برنامج تسيير مدرسة الدروس الخصوصية."""

import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QProcess, Qt, QTranslator
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from ecole import APP_NAME, backup, db
from ecole.services import Store
from ecole.ui.common import STYLE
from ecole.ui.login import ChangePasswordDialog, LoginDialog
from ecole.ui.main_window import MainWindow


class App:
    def __init__(self, qt_app: QApplication):
        self.qt_app = qt_app
        self.data_dir = db.default_data_dir()
        self.db_path = self.data_dir / "ecole.db"
        self.conn = db.connect(self.db_path)
        self.store = Store(self.conn)
        self.window = None
        self.closed = False

    def run(self) -> int:
        login = LoginDialog(self.store)
        if not login.exec():
            return 0
        user = self.store.user
        if user.must_change and not ChangePasswordDialog(self.store, user.id, forced=True).exec():
            return 0
        self.window = MainWindow(self.store, self.data_dir, self.backup, self.restore)
        self.window.showMaximized()
        self.qt_app.aboutToQuit.connect(self.shutdown)
        return self.qt_app.exec()

    def backup(self) -> list[Path]:
        """نسخة في المجلد المحلي + المجلد الإضافي (فلاشة أو Drive) إن وُجد."""
        settings = self.store.settings()
        keep = int(settings.get("backup_keep", 30))
        paths = [backup.make_backup(self.conn, self.data_dir / "backups", keep)]
        extra = settings.get("backup_dir", "").strip()
        if extra:
            paths.append(backup.make_backup(self.conn, extra, keep))
        return paths

    def shutdown(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.backup()
        except OSError:
            # المجلد الإضافي قد يكون غير متوفر (فلاشة منزوعة): نكتفي بالنسخة المحلية.
            try:
                backup.make_backup(self.conn, self.data_dir / "backups")
            except OSError:
                pass
        self.conn.close()

    def restore(self, path: str):
        try:
            backup.make_backup(self.conn, self.data_dir / "backups" / "before-restore", 10)
            self.closed = True
            self.conn.close()
            backup.restore_backup(path, self.db_path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self.window, "خطأ", f"فشل الاسترجاع:\n{exc}")
            self.conn = db.connect(self.db_path)
            self.store.conn = self.conn
            self.closed = False
            return
        QMessageBox.information(self.window, "تم", "تم استرجاع النسخة. سيُعاد تشغيل البرنامج.")
        QProcess.startDetached(sys.executable, sys.argv[1:] if getattr(sys, "frozen", False)
                               else sys.argv)
        self.qt_app.quit()


def install_excepthook():
    """يعرض الأخطاء غير المتوقعة في رسالة ويحفظها في ملف بدل إغلاق البرنامج بصمت."""
    log_path = db.default_data_dir() / "errors.log"

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            pass
        QMessageBox.critical(None, "خطأ غير متوقع",
                             f"حدث خطأ غير متوقع. تم حفظ التفاصيل في:\n{log_path}\n\n{exc}")

    sys.excepthook = hook


def main() -> int:
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName(APP_NAME)
    qt_app.setLayoutDirection(Qt.RightToLeft)
    QLocale.setDefault(QLocale(QLocale.Arabic, QLocale.Algeria))
    translator = QTranslator(qt_app)
    if translator.load(QLocale(QLocale.Arabic), "qtbase", "_",
                       QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        qt_app.installTranslator(translator)
    qt_app.setFont(QFont("Segoe UI", 10))
    qt_app.setStyle("Fusion")
    qt_app.setStyleSheet(STYLE)
    icon = Path(__file__).with_name("icon.ico")
    if icon.exists():
        from PySide6.QtGui import QIcon
        qt_app.setWindowIcon(QIcon(str(icon)))
    install_excepthook()
    return App(qt_app).run()


if __name__ == "__main__":
    sys.exit(main())
