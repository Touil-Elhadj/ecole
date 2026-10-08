"""لوحة اليوم."""

from PySide6.QtCore import QDate, QLocale, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .common import cell, fill_table, make_table, money, title_label


class Card(QFrame):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.value = QLabel("-")
        self.value.setObjectName("cardValue")
        caption = QLabel(label)
        caption.setObjectName("cardLabel")
        layout = QVBoxLayout(self)
        layout.addWidget(self.value)
        layout.addWidget(caption)


class DashboardPage(QWidget):
    open_attendance = Signal(int, str)
    go_to = Signal(str)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.date_label = QLabel()
        self.date_label.setStyleSheet("color: #5b6b80; font-size: 12pt")

        self.cards = {
            "cash": Card("المقبوض اليوم"),
            "attendances": Card("الحضور اليوم"),
            "academy_share": Card("نصيب الأكاديمية اليوم"),
            "debtors": Card("تلاميذ مدينون"),
            "students": Card("التلاميذ النشطون"),
            "teachers": Card("الأساتذة"),
            "groups": Card("الأفواج"),
            "prepaid_sessions": Card("حصص مدفوعة مسبقاً"),
        }
        grid = QGridLayout()
        for i, card in enumerate(self.cards.values()):
            grid.addWidget(card, i // 4, i % 4)

        quick = QHBoxLayout()
        for text, page in (("💰 تسجيل دفعة", "students"), ("✔ تسجيل الحضور", "attendance"),
                           ("+ تلميذ جديد", "students")):
            b = QPushButton(text)
            b.setObjectName("primary")
            b.clicked.connect(lambda _=False, p=page: self.go_to.emit(p))
            quick.addWidget(b)
        quick.addStretch()

        self.lessons = make_table(["المادة", "المستوى", "الفوج", "الأستاذ", "الحاضرون",
                                   "الغائبون"])
        self.lessons.doubleClicked.connect(self._open_lesson)

        layout = QVBoxLayout(self)
        head = QHBoxLayout()
        head.addWidget(title_label("لوحة اليوم"))
        head.addStretch()
        head.addWidget(self.date_label)
        layout.addLayout(head)
        self.period_label = QLabel()
        self.period_label.setWordWrap(True)
        layout.addWidget(self.period_label)
        layout.addLayout(grid)
        layout.addLayout(quick)
        layout.addWidget(QLabel("حصص اليوم المسجّلة (نقرتان لفتح الحضور):"))
        layout.addWidget(self.lessons, 1)

    def showEvent(self, event):
        self.refresh()
        super().showEvent(event)

    def refresh(self):
        data = self.store.dashboard()
        self.date_label.setText(QLocale().toString(QDate.currentDate(), "dddd d MMMM yyyy"))
        period = self.store.current_period()
        if period is None:
            self.period_label.setVisible(False)
        else:
            week = (period["days"] - 1) // 7 + 1
            text = (f"فترة الحساب الحالية: من {period['start_date']} — الأسبوع {week} من "
                    f"{self.store.PERIOD_WEEKS} (اليوم {period['days']})")
            style = "font-weight: bold; color: #1f3a5f"
            if period["due"]:
                text += "   ⚠ حان موعد دفع رواتب الأساتذة (الحصيلة والرواتب ← بداية الحساب)"
                style = "font-weight: bold; color: #c62828"
            self.period_label.setText(text)
            self.period_label.setStyleSheet(style)
            self.period_label.setVisible(True)
        for key, card in self.cards.items():
            value = data[key]
            card.value.setText(money(value) if key in ("cash", "academy_share") else str(value))
        self._today = data["today_lessons"]
        fill_table(self.lessons, [[
            cell(le["subject_name"], data=le["group_id"], bold=True), le["level_name"],
            le["group_name"], le["teacher_name"],
            cell(le["present_count"], align_center=True),
            cell(le["absent_count"], align_center=True),
        ] for le in self._today])

    def _open_lesson(self, index):
        group_id = self.lessons.item(index.row(), 0).data(Qt.UserRole)
        self.open_attendance.emit(group_id, QDate.currentDate().toString("yyyy-MM-dd"))
