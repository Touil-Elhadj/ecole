"""صفحة تسجيل الحضور: الحاضر فقط يُخصم من رصيده."""

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QSplitter, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import printing
from .common import (
    RED, balance_cell, cell, confirm, error, fill_combo, fill_table, guarded, info,
    make_table, date_edit, iso, title_label,
)
from .students import PaymentDialog, group_label


class PickStudentDialog(QDialog):
    def __init__(self, store, exclude: set[int], parent=None):
        super().__init__(parent)
        self.store = store
        self.exclude = exclude
        self.student_id = None
        self.setWindowTitle("إضافة تلميذ من خارج الفوج")
        self.resize(460, 480)
        self.search = QLineEdit()
        self.search.setPlaceholderText("اكتب اسم التلميذ...")
        self.list = QListWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self.search)
        layout.addWidget(self.list)
        buttons = QDialogButtonBox()
        buttons.addButton("إضافة", QDialogButtonBox.AcceptRole).setObjectName("primary")
        buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._pick)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.search.textChanged.connect(self._load)
        self.list.itemDoubleClicked.connect(lambda _: self._pick())
        self._load()

    def _load(self):
        self.list.clear()
        for s in self.store.list_students(search=self.search.text().strip(), active_only=True):
            if s["id"] in self.exclude:
                continue
            item = QListWidgetItem(f"{s['full_name']} — {s['level_name'] or ''} "
                                   f"(الرصيد: {s['balance']})")
            item.setData(Qt.UserRole, s["id"])
            self.list.addItem(item)

    def _pick(self):
        item = self.list.currentItem()
        if item is None:
            error(self, "اختر تلميذاً.")
            return
        self.student_id = item.data(Qt.UserRole)
        self.accept()


class AttendancePage(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.lesson_id = None
        self.rows: list[dict] = []
        self.extra: list[int] = []

        self.group = QComboBox()
        self.group.setMinimumWidth(380)
        self.date = date_edit()
        today_btn = QPushButton("اليوم")
        today_btn.clicked.connect(lambda: self.date.setDate(QDate.currentDate()))

        top = QHBoxLayout()
        top.addWidget(QLabel("الفوج:"))
        top.addWidget(self.group, 1)
        top.addWidget(QLabel("التاريخ:"))
        top.addWidget(self.date)
        top.addWidget(today_btn)

        self.status = QLabel()
        self.status.setStyleSheet("font-weight: bold")

        self.table = make_table(["حاضر", "الاسم واللقب", "المستوى", "الرصيد", "ملاحظة"])
        self.table.setSortingEnabled(False)
        self.table.cellClicked.connect(self._toggle_row)

        all_btn = QPushButton("✔ الكل حاضر")
        all_btn.clicked.connect(lambda: self._set_all(True))
        none_btn = QPushButton("✘ الكل غائب")
        none_btn.clicked.connect(lambda: self._set_all(False))
        add_btn = QPushButton("+ تلميذ من خارج الفوج")
        add_btn.clicked.connect(self._add_extra)
        pay_btn = QPushButton("💰 دفع للتلميذ المحدد")
        pay_btn.clicked.connect(self._pay)
        print_btn = QPushButton("طباعة القائمة")
        print_btn.clicked.connect(self._print)
        self.delete_btn = QPushButton("حذف الحصة")
        self.delete_btn.setObjectName("danger")
        self.delete_btn.clicked.connect(self._delete)
        save_btn = QPushButton("💾 حفظ الحضور")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save)

        actions = QHBoxLayout()
        for b in (all_btn, none_btn, add_btn, pay_btn, print_btn, self.delete_btn):
            actions.addWidget(b)
        actions.addStretch()
        actions.addWidget(save_btn)

        self.history = make_table(["التاريخ", "الحاضرون", "الغائبون"])
        self.history.cellDoubleClicked.connect(self._open_history)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.status)
        left_layout.addWidget(self.table)
        left_layout.addLayout(actions)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("الحصص السابقة لهذا الفوج (نقرتان للفتح):"))
        right_layout.addWidget(self.history)
        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(title_label("تسجيل الحضور"))
        layout.addLayout(top)
        layout.addWidget(splitter, 1)

        self.group.currentIndexChanged.connect(self.load)
        self.date.dateChanged.connect(self.load)

    def showEvent(self, event):
        current = self.group.currentData()
        groups = self.store.list_groups(active_only=True)
        fill_combo(self.group, [(group_label(g), g["id"]) for g in groups], "— اختر الفوج —",
                   current)
        self.delete_btn.setVisible(self.store.user is None or self.store.user.is_admin)
        self.load()
        super().showEvent(event)

    def open_group(self, group_id: int, lesson_date: str):
        index = self.group.findData(group_id)
        if index >= 0:
            self.group.setCurrentIndex(index)
        self.date.setDate(QDate.fromString(lesson_date, "yyyy-MM-dd"))
        self.load()

    # -------------------------------------------------------------- العرض
    def load(self):
        group_id = self.group.currentData()
        self.extra = []
        if not group_id:
            self.lesson_id, self.rows = None, []
            self.status.setText("اختر الفوج والتاريخ.")
            self._render()
            fill_table(self.history, [])
            return
        self.lesson_id, self.rows = self.store.attendance_for(group_id, iso(self.date))
        if self.lesson_id:
            self.status.setText("✔ حضور هذه الحصة مسجّل مسبقاً — يمكنك تعديله ثم الحفظ.")
            self.status.setStyleSheet("font-weight: bold; color: #1b7f3b")
        else:
            self.status.setText("حصة جديدة — أشّر على الحاضرين ثم اضغط حفظ.")
            self.status.setStyleSheet("font-weight: bold; color: #1f3a5f")
        self._render()
        self._load_history(group_id)

    def _load_history(self, group_id):
        lessons = self.store.lessons_between("2000-01-01", "2999-12-31", group_id)
        fill_table(self.history, [[
            cell(le["lesson_date"], data=le["lesson_date"]),
            cell(le["present_count"], align_center=True),
            cell(le["absent_count"], align_center=True),
        ] for le in lessons[:60]])

    def _render(self):
        rows = []
        for r in self.rows:
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            check.setCheckState(Qt.Checked if r["present"] else Qt.Unchecked)
            check.setData(Qt.UserRole, r["id"])
            notes = []
            if not r.get("is_member", True):
                notes.append("من خارج الفوج")
            if r["balance"] <= 0:
                notes.append("لا يملك رصيداً")
            rows.append([check, cell(r["full_name"], bold=True), r["level_name"] or "",
                         balance_cell(r["balance"]),
                         cell("، ".join(notes), color=RED if notes else None)])
        fill_table(self.table, rows)
        self.table.setSortingEnabled(False)
        self.table.setColumnWidth(0, 60)

    def _toggle_row(self, row, column):
        if column == 0:
            return
        item = self.table.item(row, 0)
        item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)

    def _set_all(self, present: bool):
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(Qt.Checked if present else Qt.Unchecked)

    def _presence(self) -> dict[int, bool]:
        return {self.table.item(r, 0).data(Qt.UserRole):
                self.table.item(r, 0).checkState() == Qt.Checked
                for r in range(self.table.rowCount())}

    # ----------------------------------------------------------- العمليات
    def _save(self):
        group_id = self.group.currentData()
        if not group_id:
            error(self, "اختر الفوج أولاً.")
            return
        presence = self._presence()
        if not presence:
            error(self, "لا يوجد تلاميذ في هذا الفوج. أضفهم من صفحة الأفواج.")
            return
        present = [sid for sid, p in presence.items() if p]
        if not present and not confirm(self, "لم تؤشّر على أي حاضر. هل تريد الحفظ رغم ذلك؟"):
            return
        lesson_id = self.lesson_id or self.store.create_lesson(group_id, iso(self.date))
        _, ok = guarded(self, self.store.save_attendance, lesson_id, presence)
        if not ok:
            return
        debtors = [r["full_name"] for r in self.store.attendance_sheet(lesson_id)
                   if r["present"] and r["balance"] < 0]
        message = f"تم حفظ الحضور: {len(present)} حاضر، {len(presence) - len(present)} غائب."
        if debtors:
            message += "\n\nتلاميذ أصبح عليهم دَين:\n- " + "\n- ".join(debtors)
        info(self, message)
        self.load()

    def _add_extra(self):
        if not self.group.currentData():
            error(self, "اختر الفوج أولاً.")
            return
        presence = self._presence()
        dialog = PickStudentDialog(self.store, set(presence), parent=self)
        if not dialog.exec():
            return
        s = self.store.get_student(dialog.student_id)
        for row in self.rows:
            row["present"] = presence.get(row["id"], False)
        self.rows.append({"id": s["id"], "full_name": s["full_name"],
                          "level_name": s["level_name"], "balance": s["balance"],
                          "present": True, "is_member": False})
        self._render()

    def _selected_student(self):
        row = self.table.currentRow()
        if row < 0:
            error(self, "اختر تلميذاً من القائمة أولاً.")
            return None
        return self.table.item(row, 0).data(Qt.UserRole)

    def _pay(self):
        sid = self._selected_student()
        if sid is None:
            return
        dialog = PaymentDialog(self.store, sid, parent=self)
        if dialog.exec():
            presence = self._presence()
            for row in self.rows:
                row["present"] = presence.get(row["id"], False)
                if row["id"] == sid:
                    row["balance"] = self.store.student_balance(sid)
            self._render()
            printing.print_receipt(self, self.store, dialog.payment_id)

    def _open_history(self, row, _column):
        self.date.setDate(QDate.fromString(self.history.item(row, 0).data(Qt.UserRole),
                                           "yyyy-MM-dd"))

    def _delete(self):
        if not self.lesson_id:
            error(self, "هذه الحصة غير محفوظة.")
            return
        if confirm(self, "حذف هذه الحصة وكل حضورها؟ سيُعاد الرصيد للتلاميذ الحاضرين."):
            _, ok = guarded(self, self.store.delete_lesson, self.lesson_id)
            if ok:
                self.load()

    def _print(self):
        group = self.store.get_group(self.group.currentData()) if self.group.currentData() else None
        if group is None:
            error(self, "اختر الفوج أولاً.")
            return
        presence = self._presence()
        rows = [[i + 1, r["full_name"], r["level_name"] or "",
                 "حاضر" if presence.get(r["id"]) else "", r["balance"]]
                for i, r in enumerate(self.rows)]
        html = printing.table_html(
            f"قائمة الحضور - {group_label(group)}", f"التاريخ: {iso(self.date)}",
            ["#", "الاسم واللقب", "المستوى", "الحضور", "الرصيد"], rows, self.store.settings())
        printing.print_html(self, html)
