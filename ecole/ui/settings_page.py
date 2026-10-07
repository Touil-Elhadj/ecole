"""الإعدادات: معلومات الأكاديمية، الأسعار، المستويات والمواد، المستخدمون، النسخ الاحتياطي."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from .common import (
    RED, cell, confirm, error, fill_table, guarded, info, make_table, money, selected_id,
    title_label,
)
from .login import ChangePasswordDialog


class GeneralTab(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.name = QLineEdit()
        self.address = QLineEdit()
        self.phone = QLineEdit()
        self.footer = QLineEdit()
        self.price = QSpinBox()
        self.price.setRange(0, 100000)
        self.price.setSingleStep(50)
        self.price.setSuffix(" دج")
        self.pack_sessions = QSpinBox()
        self.pack_sessions.setRange(1, 100)
        self.pack_price = QSpinBox()
        self.pack_price.setRange(0, 1000000)
        self.pack_price.setSingleStep(100)
        self.pack_price.setSuffix(" دج")
        self.share_num = QSpinBox()
        self.share_num.setRange(0, 100)
        self.share_den = QSpinBox()
        self.share_den.setRange(1, 100)
        self.share_preview = QLabel()

        academy = QGroupBox("معلومات الأكاديمية (تظهر على الوصل)")
        f1 = QFormLayout(academy)
        f1.addRow("اسم الأكاديمية:", self.name)
        f1.addRow("العنوان:", self.address)
        f1.addRow("الهاتف:", self.phone)
        f1.addRow("عبارة أسفل الوصل:", self.footer)

        prices = QGroupBox("الأسعار والنسبة")
        f2 = QFormLayout(prices)
        f2.addRow("سعر الحصة الواحدة:", self.price)
        f2.addRow("عدد حصص الباقة:", self.pack_sessions)
        f2.addRow("سعر الباقة:", self.pack_price)
        share = QHBoxLayout()
        share.addWidget(self.share_num)
        share.addWidget(QLabel("من"))
        share.addWidget(self.share_den)
        share.addStretch()
        f2.addRow("نسبة الأكاديمية:", share)
        f2.addRow("", self.share_preview)

        save = QPushButton("💾 حفظ الإعدادات")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        layout = QVBoxLayout(self)
        layout.addWidget(academy)
        layout.addWidget(prices)
        bar = QHBoxLayout()
        bar.addStretch()
        bar.addWidget(save)
        layout.addLayout(bar)
        layout.addStretch()

        for w in (self.price, self.share_num, self.share_den):
            w.valueChanged.connect(self._preview)

    def refresh(self):
        s = self.store.settings()
        self.name.setText(s["academy_name"])
        self.address.setText(s["academy_address"])
        self.phone.setText(s["academy_phone"])
        self.footer.setText(s["receipt_footer"])
        self.price.setValue(int(s["session_price"]))
        self.pack_sessions.setValue(int(s["pack_sessions"]))
        self.pack_price.setValue(int(s["pack_price"]))
        self.share_num.setValue(int(s["academy_share_num"]))
        self.share_den.setValue(int(s["academy_share_den"]))
        self._preview()

    def _preview(self):
        price = self.price.value()
        den = self.share_den.value() or 1
        academy = price * self.share_num.value() / den
        self.share_preview.setText(
            f"مثال: من حصة بـ {money(price)} تأخذ الأكاديمية حوالي {academy:.0f} دج "
            f"والأستاذ حوالي {price - academy:.0f} دج (يُحسب بدقة على المجموع الشهري).")

    def _save(self):
        if self.share_num.value() > self.share_den.value():
            error(self, "نسبة الأكاديمية لا يمكن أن تتجاوز 100%.")
            return
        _, ok = guarded(self, self.store.save_settings, {
            "academy_name": self.name.text().strip(),
            "academy_address": self.address.text().strip(),
            "academy_phone": self.phone.text().strip(),
            "receipt_footer": self.footer.text().strip(),
            "session_price": self.price.value(),
            "pack_sessions": self.pack_sessions.value(),
            "pack_price": self.pack_price.value(),
            "academy_share_num": self.share_num.value(),
            "academy_share_den": self.share_den.value(),
        })
        if ok:
            info(self, "تم حفظ الإعدادات.")


class NamedListBox(QGroupBox):
    """قائمة بسيطة (المستويات أو المواد) مع إضافة وتعديل وحذف."""

    def __init__(self, title, loader, saver, deleter, parent=None):
        super().__init__(title, parent)
        self.loader, self.saver, self.deleter = loader, saver, deleter
        self.list = QListWidget()
        add = QPushButton("إضافة")
        add.clicked.connect(self._add)
        rename = QPushButton("تعديل")
        rename.clicked.connect(self._rename)
        delete = QPushButton("حذف")
        delete.setObjectName("danger")
        delete.clicked.connect(self._delete)
        bar = QHBoxLayout()
        for b in (add, rename, delete):
            bar.addWidget(b)
        layout = QVBoxLayout(self)
        layout.addWidget(self.list)
        layout.addLayout(bar)

    def refresh(self):
        self.list.clear()
        for row in self.loader():
            item = QListWidgetItem(row["name"])
            item.setData(Qt.UserRole, row["id"])
            self.list.addItem(item)

    def _add(self):
        name, ok = QInputDialog.getText(self, self.title(), "الاسم:")
        if ok:
            guarded(self, self.saver, None, name)
            self.refresh()

    def _rename(self):
        item = self.list.currentItem()
        if item is None:
            return
        name, ok = QInputDialog.getText(self, self.title(), "الاسم:", text=item.text())
        if ok:
            guarded(self, self.saver, item.data(Qt.UserRole), name)
            self.refresh()

    def _delete(self):
        item = self.list.currentItem()
        if item and confirm(self, f"حذف «{item.text()}»؟"):
            guarded(self, self.deleter, item.data(Qt.UserRole))
            self.refresh()


class ListsTab(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.levels = NamedListBox("المستويات", store.list_levels, store.save_level,
                                   store.delete_level)
        self.subjects = NamedListBox("المواد", store.list_subjects, store.save_subject,
                                     store.delete_subject)
        layout = QHBoxLayout(self)
        layout.addWidget(self.levels)
        layout.addWidget(self.subjects)

    def refresh(self):
        self.levels.refresh()
        self.subjects.refresh()


class UserDialog(QDialog):
    def __init__(self, store, user=None, parent=None):
        super().__init__(parent)
        self.store = store
        self.user = user
        self.setWindowTitle("تعديل مستخدم" if user else "مستخدم جديد")
        self.username = QLineEdit(user["username"] if user else "")
        self.full_name = QLineEdit(user["full_name"] if user else "")
        self.role = QComboBox()
        self.role.addItem("موظف استقبال (دفع وحضور فقط)", "reception")
        self.role.addItem("مدير (كل الصلاحيات)", "admin")
        if user:
            self.role.setCurrentIndex(self.role.findData(user["role"]))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.active = QCheckBox("حساب نشط")
        self.active.setChecked(bool(user["active"]) if user else True)
        form = QFormLayout(self)
        form.addRow("اسم الدخول:", self.username)
        form.addRow("الاسم الكامل:", self.full_name)
        form.addRow("الصلاحية:", self.role)
        if not user:
            form.addRow("كلمة السر:", self.password)
        form.addRow("", self.active)
        buttons = QDialogButtonBox()
        buttons.addButton("حفظ", QDialogButtonBox.AcceptRole).setObjectName("primary")
        buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _save(self):
        _, ok = guarded(self, self.store.save_user, {
            "id": self.user["id"] if self.user else None,
            "username": self.username.text(), "full_name": self.full_name.text(),
            "role": self.role.currentData(), "password": self.password.text(),
            "active": self.active.isChecked(),
        })
        if ok:
            self.accept()


class UsersTab(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.table = make_table(["اسم الدخول", "الاسم الكامل", "الصلاحية", "الحالة"])
        add = QPushButton("+ مستخدم جديد")
        add.clicked.connect(self._add)
        edit = QPushButton("تعديل")
        edit.clicked.connect(self._edit)
        reset = QPushButton("تغيير كلمة السر")
        reset.clicked.connect(self._reset)
        bar = QHBoxLayout()
        for b in (add, edit, reset):
            bar.addWidget(b)
        bar.addStretch()
        layout = QVBoxLayout(self)
        layout.addLayout(bar)
        layout.addWidget(self.table)

    def refresh(self):
        self.users = {u["id"]: u for u in self.store.list_users()}
        fill_table(self.table, [[
            cell(u["username"], data=u["id"], bold=True), u["full_name"],
            "مدير" if u["role"] == "admin" else "موظف استقبال",
            cell("نشط" if u["active"] else "موقوف", color=None if u["active"] else RED),
        ] for u in self.users.values()])

    def _selected(self):
        uid = selected_id(self.table)
        if uid is None:
            error(self, "اختر مستخدماً أولاً.")
        return uid

    def _add(self):
        if UserDialog(self.store, parent=self).exec():
            self.refresh()

    def _edit(self):
        uid = self._selected()
        if uid and UserDialog(self.store, self.users[uid], parent=self).exec():
            self.refresh()

    def _reset(self):
        uid = self._selected()
        if uid and ChangePasswordDialog(self.store, uid, parent=self).exec():
            info(self, "تم تغيير كلمة السر.")


class BackupTab(QWidget):
    backup_requested = Signal()
    restore_requested = Signal(str)

    def __init__(self, store, data_dir, parent=None):
        super().__init__(parent)
        self.store = store
        self.local_dir = QLabel(str(data_dir / "backups"))
        self.local_dir.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.extra_dir = QLineEdit()
        self.extra_dir.setReadOnly(True)
        self.extra_dir.setPlaceholderText("مثال: فلاشة USB أو مجلد Google Drive")
        browse = QPushButton("اختيار...")
        browse.clicked.connect(self._browse)
        clear = QPushButton("إزالة")
        clear.clicked.connect(lambda: self._set_dir(""))
        self.keep = QSpinBox()
        self.keep.setRange(5, 365)
        self.keep.valueChanged.connect(
            lambda v: self.store.save_settings({"backup_keep": v}))

        box = QGroupBox("النسخ الاحتياطي التلقائي")
        form = QFormLayout(box)
        note = QLabel("يأخذ البرنامج نسخة احتياطية تلقائياً عند كل إغلاق. ننصح بشدة باختيار "
                      "مجلد ثانٍ على فلاشة أو في Google Drive حتى لا تضيع البيانات إذا تعطّل "
                      "الحاسوب.")
        note.setWordWrap(True)
        form.addRow(note)
        form.addRow("المجلد المحلي:", self.local_dir)
        extra = QHBoxLayout()
        extra.addWidget(self.extra_dir, 1)
        extra.addWidget(browse)
        extra.addWidget(clear)
        form.addRow("مجلد إضافي:", extra)
        form.addRow("عدد النسخ المحتفظ بها:", self.keep)

        now = QPushButton("💾 نسخة احتياطية الآن")
        now.setObjectName("primary")
        now.clicked.connect(self.backup_requested.emit)
        restore = QPushButton("استرجاع نسخة احتياطية...")
        restore.setObjectName("danger")
        restore.clicked.connect(self._restore)
        bar = QHBoxLayout()
        bar.addWidget(now)
        bar.addWidget(restore)
        bar.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(box)
        layout.addLayout(bar)
        layout.addStretch()

    def refresh(self):
        s = self.store.settings()
        self.extra_dir.setText(s.get("backup_dir", ""))
        self.keep.blockSignals(True)
        self.keep.setValue(int(s.get("backup_keep", 30)))
        self.keep.blockSignals(False)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "اختر مجلد النسخ الاحتياطي")
        if path:
            self._set_dir(path)

    def _set_dir(self, path):
        self.store.save_settings({"backup_dir": path})
        self.refresh()

    def _restore(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "اختر النسخة الاحتياطية", self.local_dir.text(), "قاعدة بيانات (*.db)")
        if path and confirm(self, "سيتم استبدال كل البيانات الحالية بهذه النسخة، وسيُعاد تشغيل "
                                  "البرنامج. (ستُحفظ نسخة من البيانات الحالية قبل ذلك). متابعة؟"):
            self.restore_requested.emit(path)


class AuditTab(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.table = make_table(["الوقت", "المستخدم", "العملية", "التفاصيل"])
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("آخر العمليات المسجّلة في البرنامج:"))
        layout.addWidget(self.table)

    def refresh(self):
        fill_table(self.table, [[a["at"], a["user_name"] or "", a["action"], a["details"]]
                                for a in self.store.audit_log()])


class SettingsPage(QWidget):
    def __init__(self, store, data_dir, parent=None):
        super().__init__(parent)
        self.general = GeneralTab(store)
        self.lists = ListsTab(store)
        self.users = UsersTab(store)
        self.backup = BackupTab(store, data_dir)
        self.audit = AuditTab(store)
        self.tabs = QTabWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.general)
        self.tabs.addTab(scroll, "عام والأسعار")
        self.tabs.addTab(self.lists, "المستويات والمواد")
        self.tabs.addTab(self.users, "المستخدمون")
        self.tabs.addTab(self.backup, "النسخ الاحتياطي")
        self.tabs.addTab(self.audit, "سجل العمليات")
        self.tabs.currentChanged.connect(lambda _: self.refresh())
        layout = QVBoxLayout(self)
        layout.addWidget(title_label("الإعدادات"))
        layout.addWidget(self.tabs)

    def showEvent(self, event):
        self.refresh()
        super().showEvent(event)

    def refresh(self):
        for tab in (self.general, self.lists, self.users, self.backup, self.audit):
            tab.refresh()
