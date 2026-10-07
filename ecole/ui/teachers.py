"""صفحة الأساتذة."""

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from .common import (
    RED, cell, error, fill_table, guarded, make_table, selected_id, title_label,
)


class TeacherDialog(QDialog):
    def __init__(self, store, teacher_id=None, parent=None):
        super().__init__(parent)
        self.store = store
        self.teacher_id = teacher_id
        self.setWindowTitle("تعديل أستاذ" if teacher_id else "أستاذ جديد")
        self.setMinimumWidth(460)
        self.name = QLineEdit()
        self.phone = QLineEdit()
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(70)
        self.active = QCheckBox("يدرّس حالياً (نشط)")
        self.active.setChecked(True)
        if teacher_id:
            t = store.get_teacher(teacher_id)
            self.name.setText(t["full_name"])
            self.phone.setText(t["phone"])
            self.notes.setPlainText(t["notes"])
            self.active.setChecked(bool(t["active"]))

        form = QFormLayout()
        form.addRow("الاسم واللقب: *", self.name)
        form.addRow("الهاتف:", self.phone)
        form.addRow("ملاحظات:", self.notes)
        form.addRow("", self.active)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        buttons = QDialogButtonBox()
        buttons.addButton("حفظ", QDialogButtonBox.AcceptRole).setObjectName("primary")
        buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        data = {"id": self.teacher_id, "full_name": self.name.text(),
                "phone": self.phone.text(), "notes": self.notes.toPlainText(),
                "active": self.active.isChecked()}
        _, ok = guarded(self, self.store.save_teacher, data)
        if ok:
            self.accept()


class TeachersPage(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.search = QLineEdit()
        self.search.setPlaceholderText("بحث بالاسم أو الهاتف...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)

        self.table = make_table(["الرقم", "الاسم واللقب", "الهاتف", "المواد", "عدد الأفواج",
                                 "الحالة"])
        self.table.doubleClicked.connect(self._edit)
        self.count = QLabel()

        new_btn = QPushButton("+ أستاذ جديد")
        new_btn.setObjectName("primary")
        new_btn.clicked.connect(self._new)
        edit_btn = QPushButton("تعديل")
        edit_btn.clicked.connect(self._edit)
        actions = QHBoxLayout()
        actions.addWidget(new_btn)
        actions.addWidget(edit_btn)
        actions.addWidget(self.search, 1)
        actions.addWidget(self.count)

        layout = QVBoxLayout(self)
        layout.addWidget(title_label("الأساتذة"))
        layout.addLayout(actions)
        layout.addWidget(self.table)

    def showEvent(self, event):
        self.refresh()
        super().showEvent(event)

    def refresh(self):
        teachers = self.store.list_teachers(search=self.search.text().strip())
        fill_table(self.table, [[
            cell(t["id"], data=t["id"], align_center=True),
            cell(t["full_name"], bold=True),
            t["phone"],
            t["subjects"] or "",
            cell(t["groups_count"], align_center=True),
            cell("نشط" if t["active"] else "متوقف", color=None if t["active"] else RED),
        ] for t in teachers])
        self.count.setText(f"العدد: {len(teachers)}")

    def _new(self):
        if TeacherDialog(self.store, parent=self).exec():
            self.refresh()

    def _edit(self):
        tid = selected_id(self.table)
        if tid is None:
            error(self, "اختر أستاذاً من القائمة أولاً.")
            return
        if TeacherDialog(self.store, tid, parent=self).exec():
            self.refresh()
