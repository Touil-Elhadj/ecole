"""صفحة سجل المدفوعات: إعادة طباعة الوصل وإلغاء الدفعات الخاطئة."""

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from .. import printing
from .common import (
    RED, cell, confirm, date_edit, error, fill_table, guarded, iso, make_table, money,
    money_cell, selected_id, title_label,
)


class PaymentsPage(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.date_from = date_edit(QDate.currentDate().addDays(1 - QDate.currentDate().day()))
        self.date_to = date_edit()
        self.search = QLineEdit()
        self.search.setPlaceholderText("بحث باسم التلميذ أو رقم الوصل...")
        self.search.setClearButtonEnabled(True)
        today_btn = QPushButton("اليوم")
        today_btn.clicked.connect(self._today)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("من:"))
        filters.addWidget(self.date_from)
        filters.addWidget(QLabel("إلى:"))
        filters.addWidget(self.date_to)
        filters.addWidget(today_btn)
        filters.addWidget(self.search, 1)

        self.table = make_table(["رقم الوصل", "التاريخ", "التلميذ", "الحصص", "المبلغ",
                                 "المستلم", "الحالة"])
        self.total = QLabel()
        self.total.setStyleSheet("font-size: 13pt; font-weight: bold")

        reprint = QPushButton("🖨 إعادة طباعة الوصل")
        reprint.clicked.connect(self._reprint)
        self.cancel_btn = QPushButton("إلغاء الدفعة")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.clicked.connect(self._cancel)
        print_list = QPushButton("طباعة السجل")
        print_list.clicked.connect(self._print)
        actions = QHBoxLayout()
        actions.addWidget(reprint)
        actions.addWidget(self.cancel_btn)
        actions.addWidget(print_list)
        actions.addStretch()
        actions.addWidget(self.total)

        layout = QVBoxLayout(self)
        layout.addWidget(title_label("سجل المدفوعات"))
        layout.addLayout(filters)
        layout.addWidget(self.table)
        layout.addLayout(actions)

        for w in (self.date_from, self.date_to):
            w.dateChanged.connect(self.refresh)
        self.search.textChanged.connect(self.refresh)

    def showEvent(self, event):
        self.cancel_btn.setVisible(self.store.user is None or self.store.user.is_admin)
        self.refresh()
        super().showEvent(event)

    def _today(self):
        self.date_from.setDate(QDate.currentDate())
        self.date_to.setDate(QDate.currentDate())

    def refresh(self):
        self.payments = self.store.list_payments(iso(self.date_from), iso(self.date_to),
                                                 self.search.text().strip())
        rows = []
        total = 0
        for p in self.payments:
            color = RED if p["cancelled"] else None
            if not p["cancelled"]:
                total += p["amount"]
            rows.append([
                cell(p["receipt_no"], data=p["id"], color=color),
                cell(p["paid_at"][:16], color=color),
                cell(p["student_name"], bold=True, color=color),
                cell(p["sessions"], align_center=True, color=color),
                money_cell(p["amount"], color=color),
                p["user_name"] or "",
                cell(f"ملغاة: {p['cancel_reason']}" if p["cancelled"] else "مقبوضة", color=color),
            ])
        fill_table(self.table, rows)
        self.total.setText(f"مجموع المقبوض: {money(total)}  ({len(self.payments)} وصل)")

    def _current(self):
        pid = selected_id(self.table)
        if pid is None:
            error(self, "اختر دفعة من القائمة أولاً.")
        return pid

    def _reprint(self):
        pid = self._current()
        if pid:
            printing.print_receipt(self, self.store, pid)

    def _cancel(self):
        pid = self._current()
        if pid is None:
            return
        p = self.store.get_payment(pid)
        if p["cancelled"]:
            error(self, "هذه الدفعة ملغاة مسبقاً.")
            return
        if not confirm(self, f"إلغاء الوصل {p['receipt_no']} للتلميذ {p['student_name']} "
                             f"({money(p['amount'])})؟\nسيُنقص {p['sessions']} حصة من رصيده."):
            return
        reason, ok = QInputDialog.getText(self, "سبب الإلغاء", "اكتب سبب الإلغاء:")
        if ok:
            _, done = guarded(self, self.store.cancel_payment, pid, reason)
            if done:
                self.refresh()

    def _print(self):
        rows = [[p["receipt_no"], p["paid_at"][:16], p["student_name"], p["sessions"],
                 money(p["amount"]), "ملغاة" if p["cancelled"] else ""] for p in self.payments]
        total = sum(p["amount"] for p in self.payments if not p["cancelled"])
        html = printing.table_html(
            "سجل المدفوعات", f"من {iso(self.date_from)} إلى {iso(self.date_to)}",
            ["رقم الوصل", "التاريخ", "التلميذ", "الحصص", "المبلغ", "ملاحظة"], rows,
            self.store.settings(), ["", "", "المجموع", "", money(total), ""])
        printing.print_html(self, html)
