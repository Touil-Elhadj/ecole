"""تسجيل الدخول وتغيير كلمة السر."""

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout,
)

from .. import APP_NAME
from .common import error, guarded


class LoginDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle(f"{APP_NAME} - تسجيل الدخول")
        self.setMinimumWidth(380)

        title = QLabel(store.settings().get("academy_name", APP_NAME))
        title.setObjectName("pageTitle")
        self.username = QLineEdit("admin")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)

        form = QFormLayout()
        form.addRow("اسم المستخدم:", self.username)
        form.addRow("كلمة السر:", self.password)

        buttons = QDialogButtonBox()
        buttons.addButton("دخول", QDialogButtonBox.AcceptRole).setObjectName("primary")
        buttons.addButton("خروج", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._login)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.password.setFocus()

    def _login(self):
        if self.store.authenticate(self.username.text(), self.password.text()) is None:
            error(self, "اسم المستخدم أو كلمة السر غير صحيحة.")
            self.password.selectAll()
            return
        self.accept()


class ChangePasswordDialog(QDialog):
    def __init__(self, store, user_id: int, forced: bool = False, parent=None):
        super().__init__(parent)
        self.store = store
        self.user_id = user_id
        self.setWindowTitle("تغيير كلمة السر")
        self.setMinimumWidth(380)
        self.new = QLineEdit()
        self.new.setEchoMode(QLineEdit.Password)
        self.again = QLineEdit()
        self.again.setEchoMode(QLineEdit.Password)

        layout = QVBoxLayout(self)
        if forced:
            note = QLabel("لحماية البرنامج، يجب تغيير كلمة السر الافتراضية.")
            note.setWordWrap(True)
            layout.addWidget(note)
        form = QFormLayout()
        form.addRow("كلمة السر الجديدة:", self.new)
        form.addRow("أعد كتابتها:", self.again)
        layout.addLayout(form)
        buttons = QDialogButtonBox()
        buttons.addButton("حفظ", QDialogButtonBox.AcceptRole).setObjectName("primary")
        buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        if self.new.text() != self.again.text():
            error(self, "كلمتا السر غير متطابقتين.")
            return
        _, ok = guarded(self, self.store.change_password, self.user_id, self.new.text())
        if ok:
            self.accept()
