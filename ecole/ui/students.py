"""صفحة التلاميذ: الإضافة والتعديل والدفع وكشف الحساب."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QRadioButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from .. import printing
from .common import (
    GREEN, RED, balance_cell, cell, error, fill_combo, fill_table, guarded, make_table,
    money, selected_id, title_label,
)


def group_label(g) -> str:
    return f"{g['subject_name']} - {g['level_name']} - {g['teacher_name']} ({g['name']})"


class StudentDialog(QDialog):
    def __init__(self, store, student_id=None, parent=None):
        super().__init__(parent)
        self.store = store
        self.student_id = student_id
        self.setWindowTitle("تعديل تلميذ" if student_id else "تلميذ جديد")
        self.setMinimumWidth(560)

        self.name = QLineEdit()
        self.phone = QLineEdit()
        self.parent_phone = QLineEdit()
        self.level = QComboBox()
        fill_combo(self.level, [(l["name"], l["id"]) for l in store.list_levels()], "— اختر —")
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(60)
        self.active = QCheckBox("مسجّل حالياً (نشط)")
        self.active.setChecked(True)

        self.same_level = QCheckBox("إظهار أفواج نفس المستوى فقط")
        self.same_level.setChecked(True)
        self.groups = QListWidget()
        self.groups.setMinimumHeight(160)
        self._checked: set[int] = set()

        form = QFormLayout()
        form.addRow("الاسم واللقب: *", self.name)
        form.addRow("هاتف التلميذ:", self.phone)
        form.addRow("هاتف الولي:", self.parent_phone)
        form.addRow("المستوى:", self.level)
        form.addRow("ملاحظات:", self.notes)
        form.addRow("", self.active)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("الأفواج المسجّل فيها:"))
        layout.addWidget(self.same_level)
        layout.addWidget(self.groups)
        buttons = QDialogButtonBox()
        buttons.addButton("حفظ", QDialogButtonBox.AcceptRole).setObjectName("primary")
        buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if student_id:
            s = store.get_student(student_id)
            self.name.setText(s["full_name"])
            self.phone.setText(s["phone"])
            self.parent_phone.setText(s["parent_phone"])
            fill_combo(self.level, [(l["name"], l["id"]) for l in store.list_levels()],
                       "— اختر —", s["level_id"])
            self.notes.setPlainText(s["notes"])
            self.active.setChecked(bool(s["active"]))
            self._checked = {g["id"] for g in store.student_groups(student_id)}

        self.level.currentIndexChanged.connect(self._load_groups)
        self.same_level.toggled.connect(self._load_groups)
        self._load_groups()

    def _remember_checks(self):
        for i in range(self.groups.count()):
            item = self.groups.item(i)
            gid = item.data(Qt.UserRole)
            if item.checkState() == Qt.Checked:
                self._checked.add(gid)
            else:
                self._checked.discard(gid)

    def _load_groups(self):
        self._remember_checks()
        level_id = self.level.currentData()
        self.groups.clear()
        for g in self.store.list_groups(active_only=True):
            if (self.same_level.isChecked() and level_id and g["level_id"] != level_id
                    and g["id"] not in self._checked):
                continue
            item = QListWidgetItem(group_label(g))
            item.setData(Qt.UserRole, g["id"])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if g["id"] in self._checked else Qt.Unchecked)
            self.groups.addItem(item)

    def _save(self):
        self._remember_checks()
        data = {
            "id": self.student_id, "full_name": self.name.text(), "phone": self.phone.text(),
            "parent_phone": self.parent_phone.text(), "level_id": self.level.currentData(),
            "notes": self.notes.toPlainText(), "active": self.active.isChecked(),
        }
        student_id, ok = guarded(self, self.store.save_student, data)
        if not ok:
            return
        self.store.set_student_groups(student_id, self._checked)
        self.student_id = student_id
        self.accept()


class PaymentDialog(QDialog):
    def __init__(self, store, student_id: int, parent=None):
        super().__init__(parent)
        self.store = store
        self.student_id = student_id
        self.payment_id = None
        self.opts = store.payment_options()
        student = store.get_student(student_id)
        self.setWindowTitle("تسجيل دفعة")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        name = QLabel(student["full_name"])
        name.setObjectName("pageTitle")
        layout.addWidget(name)
        balance = student["balance"]
        if balance < 0:
            note = QLabel(f"عليه دَين: {-balance} حصة ({money(-balance * self.opts['session_price'])})")
            note.setStyleSheet(f"color: {RED.name()}; font-weight: bold")
        else:
            note = QLabel(f"الرصيد الحالي: {balance} حصة")
            note.setStyleSheet(f"color: {GREEN.name()}; font-weight: bold")
        layout.addWidget(note)

        self.pack = QRadioButton(
            f"باقة {self.opts['pack_sessions']} حصص ({money(self.opts['pack_price'])})")
        self.single = QRadioButton(f"حصص فردية ({money(self.opts['session_price'])} للحصة)")
        self.pack.setChecked(True)
        self.count = QSpinBox()
        self.count.setRange(1, 50)
        self.total = QLabel()
        self.total.setStyleSheet("font-size: 15pt; font-weight: bold")

        form = QFormLayout()
        form.addRow(self.pack)
        form.addRow(self.single)
        form.addRow("العدد:", self.count)
        form.addRow("المبلغ المطلوب:", self.total)
        layout.addLayout(form)

        buttons = QDialogButtonBox()
        buttons.addButton("تسجيل الدفع", QDialogButtonBox.AcceptRole).setObjectName("primary")
        buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        for w in (self.pack, self.single):
            w.toggled.connect(self._update)
        self.count.valueChanged.connect(self._update)
        self._update()

    def _kind(self) -> str:
        return "pack" if self.pack.isChecked() else "single"

    def _update(self):
        n = self.count.value()
        if self._kind() == "pack":
            sessions = n * self.opts["pack_sessions"]
            amount = n * self.opts["pack_price"]
        else:
            sessions, amount = n, n * self.opts["session_price"]
        self.total.setText(f"{money(amount)}  ←  {sessions} حصة")

    def _save(self):
        payment, ok = guarded(self, self.store.create_payment, self.student_id, self._kind(),
                              self.count.value())
        if ok:
            self.payment_id = payment["id"]
            self.accept()


class StatementDialog(QDialog):
    def __init__(self, store, student_id: int, parent=None):
        super().__init__(parent)
        self.store = store
        student = store.get_student(student_id)
        self.student = student
        self.setWindowTitle(f"كشف حساب - {student['full_name']}")
        self.resize(820, 560)
        layout = QVBoxLayout(self)
        header = QLabel(f"{student['full_name']} — {student['level_name'] or ''} — "
                        f"الرصيد الحالي: {student['balance']} حصة")
        header.setObjectName("pageTitle")
        layout.addWidget(header)
        groups = ", ".join(group_label(g) for g in store.student_groups(student_id)) or "لا يوجد"
        groups_label = QLabel(f"الأفواج: {groups}")
        groups_label.setWordWrap(True)
        layout.addWidget(groups_label)

        self.events = store.student_statement(student_id)
        self.table = make_table(["التاريخ", "العملية", "المبلغ", "الحصص", "الرصيد"])
        rows = []
        for e in self.events:
            change = f"+{e['change']}" if e["change"] > 0 else str(e["change"])
            rows.append([
                cell(e["date"][:16], color=RED if e["cancelled"] else None),
                cell(e["label"], color=RED if e["cancelled"] else None),
                money(e["amount"]) if e["amount"] else "",
                cell(change, align_center=True),
                balance_cell(e["balance"]),
            ])
        fill_table(self.table, rows)
        self.table.setSortingEnabled(False)
        self.table.scrollToBottom()
        layout.addWidget(self.table)

        bar = QHBoxLayout()
        print_btn = QPushButton("طباعة الكشف")
        print_btn.clicked.connect(self._print)
        close = QPushButton("إغلاق")
        close.clicked.connect(self.accept)
        bar.addWidget(print_btn)
        bar.addStretch()
        bar.addWidget(close)
        layout.addLayout(bar)

    def _print(self):
        rows = [[e["date"][:16], e["label"], money(e["amount"]) if e["amount"] else "",
                 e["change"], e["balance"]] for e in self.events]
        html = printing.table_html(
            f"كشف حساب التلميذ: {self.student['full_name']}",
            f"الرصيد الحالي: {self.student['balance']} حصة",
            ["التاريخ", "العملية", "المبلغ", "الحصص", "الرصيد"], rows, self.store.settings())
        printing.print_html(self, html)


class StudentsPage(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store

        self.search = QLineEdit()
        self.search.setPlaceholderText("بحث بالاسم أو الهاتف أو الرقم...")
        self.search.setClearButtonEnabled(True)
        self.level = QComboBox()
        self.debtors = QCheckBox("المدينون فقط")
        self.show_inactive = QCheckBox("إظهار غير النشطين")

        filters = QHBoxLayout()
        filters.addWidget(self.search, 3)
        filters.addWidget(self.level, 1)
        filters.addWidget(self.debtors)
        filters.addWidget(self.show_inactive)

        self.table = make_table(["الرقم", "الاسم واللقب", "المستوى", "المواد", "هاتف الولي",
                                 "رصيد الحصص"])
        self.table.doubleClicked.connect(self._edit)
        self.count = QLabel()

        new_btn = QPushButton("+ تلميذ جديد")
        new_btn.clicked.connect(self._new)
        edit_btn = QPushButton("تعديل")
        edit_btn.clicked.connect(self._edit)
        pay_btn = QPushButton("💰 دفع")
        pay_btn.setObjectName("primary")
        pay_btn.clicked.connect(self._pay)
        statement_btn = QPushButton("كشف الحساب")
        statement_btn.clicked.connect(self._statement)

        actions = QHBoxLayout()
        for b in (new_btn, edit_btn, pay_btn, statement_btn):
            actions.addWidget(b)
        actions.addStretch()
        actions.addWidget(self.count)

        layout = QVBoxLayout(self)
        layout.addWidget(title_label("التلاميذ"))
        layout.addLayout(filters)
        layout.addLayout(actions)
        layout.addWidget(self.table)

        self.search.textChanged.connect(self.refresh)
        self.level.currentIndexChanged.connect(self.refresh)
        self.debtors.toggled.connect(self.refresh)
        self.show_inactive.toggled.connect(self.refresh)

    def showEvent(self, event):
        fill_combo(self.level, [(l["name"], l["id"]) for l in self.store.list_levels()],
                   "كل المستويات", self.level.currentData())
        self.refresh()
        super().showEvent(event)

    def refresh(self):
        students = self.store.list_students(
            search=self.search.text().strip(), active_only=not self.show_inactive.isChecked(),
            level_id=self.level.currentData(), only_debtors=self.debtors.isChecked())
        rows = []
        for s in students:
            muted = None if s["active"] else RED
            rows.append([
                cell(s["id"], data=s["id"], align_center=True),
                cell(s["full_name"], color=muted, bold=True),
                s["level_name"] or "",
                s["subjects"] or "",
                s["parent_phone"] or s["phone"],
                balance_cell(s["balance"]),
            ])
        fill_table(self.table, rows)
        self.count.setText(f"العدد: {len(students)}")

    def _current(self):
        sid = selected_id(self.table)
        if sid is None:
            error(self, "اختر تلميذاً من القائمة أولاً.")
        return sid

    def _new(self):
        if StudentDialog(self.store, parent=self).exec():
            self.refresh()

    def _edit(self):
        sid = self._current()
        if sid and StudentDialog(self.store, sid, parent=self).exec():
            self.refresh()

    def _pay(self):
        sid = self._current()
        if sid is None:
            return
        dialog = PaymentDialog(self.store, sid, parent=self)
        if dialog.exec():
            self.refresh()
            printing.print_receipt(self, self.store, dialog.payment_id)

    def _statement(self):
        sid = self._current()
        if sid:
            StatementDialog(self.store, sid, parent=self).exec()
