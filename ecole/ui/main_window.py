"""النافذة الرئيسية: قائمة جانبية وصفحات."""

from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from .. import APP_NAME, APP_VERSION
from .attendance import AttendancePage
from .common import error, info
from .dashboard import DashboardPage
from .groups import GroupsPage
from .login import ChangePasswordDialog
from .payments import PaymentsPage
from .reports import ReportsPage
from .settings_page import SettingsPage
from .students import StudentsPage
from .teachers import TeachersPage


class MainWindow(QMainWindow):
    def __init__(self, store, data_dir: Path, backup_callback, restore_callback):
        super().__init__()
        self.store = store
        self.backup_callback = backup_callback
        self.restore_callback = restore_callback
        self.setWindowTitle(f"{store.settings()['academy_name']} - {APP_NAME}")
        self.resize(1280, 780)

        is_admin = store.user is None or store.user.is_admin
        self.pages: dict[str, QWidget] = {
            "dashboard": DashboardPage(store),
            "students": StudentsPage(store),
            "attendance": AttendancePage(store),
            "payments": PaymentsPage(store),
            "groups": GroupsPage(store),
            "teachers": TeachersPage(store),
        }
        nav_items = [
            ("dashboard", "🏠  لوحة اليوم"),
            ("students", "🎓  التلاميذ والدفع"),
            ("attendance", "✔  الحضور"),
            ("payments", "🧾  سجل المدفوعات"),
            ("groups", "👥  الأفواج"),
            ("teachers", "👨‍🏫  الأساتذة"),
        ]
        if is_admin:
            self.pages["reports"] = ReportsPage(store)
            self.pages["settings"] = SettingsPage(store, data_dir, backup_callback)
            nav_items += [("reports", "📊  التقارير"), ("settings", "⚙  الإعدادات")]
            backup_tab = self.pages["settings"].backup
            backup_tab.backup_requested.connect(self._backup_now)
            backup_tab.restore_requested.connect(self.restore_callback)

        self.stack = QStackedWidget()
        for page in self.pages.values():
            self.stack.addWidget(page)

        nav = QFrame()
        nav.setObjectName("nav")
        nav.setFixedWidth(230)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)
        title = QLabel(store.settings()["academy_name"])
        title.setObjectName("navTitle")
        title.setWordWrap(True)
        nav_layout.addWidget(title)
        self.buttons = QButtonGroup(self)
        self.nav_buttons: dict[str, QPushButton] = {}
        for key, text in nav_items:
            button = QPushButton(text)
            button.setCheckable(True)
            button.clicked.connect(lambda _=False, k=key: self.show_page(k))
            self.buttons.addButton(button)
            self.nav_buttons[key] = button
            nav_layout.addWidget(button)
        nav_layout.addStretch()
        user = store.user
        if user:
            password_btn = QPushButton("🔑  تغيير كلمة السر")
            password_btn.clicked.connect(self._change_password)
            nav_layout.addWidget(password_btn)
            role = "مدير" if user.is_admin else "موظف استقبال"
            who = QLabel(f"{user.full_name or user.username} ({role})\nالإصدار {APP_VERSION}")
            who.setObjectName("navUser")
            nav_layout.addWidget(who)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(nav)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 12, 16, 12)
        content_layout.addWidget(self.stack)
        layout.addWidget(content, 1)
        self.setCentralWidget(central)

        dashboard = self.pages["dashboard"]
        dashboard.go_to.connect(self.show_page)
        dashboard.open_attendance.connect(self._open_attendance)
        self.show_page("dashboard")

    def show_page(self, key: str):
        self.nav_buttons[key].setChecked(True)
        self.stack.setCurrentWidget(self.pages[key])

    def _open_attendance(self, group_id: int, lesson_date: str):
        self.show_page("attendance")
        self.pages["attendance"].open_group(group_id, lesson_date)

    def _change_password(self):
        if ChangePasswordDialog(self.store, self.store.user.id, parent=self).exec():
            info(self, "تم تغيير كلمة السر.")

    def _backup_now(self):
        try:
            paths = self.backup_callback()
        except OSError as exc:
            error(self, f"فشل النسخ الاحتياطي:\n{exc}")
            return
        info(self, "تم حفظ النسخة الاحتياطية في:\n" + "\n".join(str(p) for p in paths))
