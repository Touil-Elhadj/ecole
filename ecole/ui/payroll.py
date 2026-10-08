"""الحصيلة والرواتب: حصيلة الأسبوع، حصيلة الشهر (فترة 4 أسابيع)، وبداية الحساب (دفع الرواتب)."""

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QWidget,
)

from .. import printing
from .common import (
    GREEN, RED, cell, confirm, date_edit, error, fill_table, guarded, info, iso, make_table,
    money, money_cell, title_label,
)

HEADERS = ["الأستاذ", "الحصص", "الحضور", "المجموع", "نصيب الأكاديمية", "صافي الأستاذ"]


def period_label(p) -> str:
    if p["is_open"]:
        return f"الفترة الحالية: من {p['start_date']} (اليوم {p['days']})"
    return f"من {p['start_date']} إلى {p['end_date']}"


def summary_rows(rows, paid=None):
    """صفوف الجدول + سطر المجموع."""
    out = []
    for r in rows:
        line = [cell(r["teacher_name"], data=r["teacher_id"], bold=True),
                cell(r["lessons"], align_center=True), cell(r["attendances"], align_center=True),
                money_cell(r["total"]), money_cell(r["academy"]), money_cell(r["net"], bold=True)]
        if paid is not None:
            amount = paid.get(r["teacher_id"], {}).get("amount")
            line.append(money_cell(amount, color=GREEN) if amount is not None
                        else cell("—", align_center=True))
        out.append(line)
    totals = [sum(r[k] for r in rows) for k in ("lessons", "attendances", "total", "academy", "net")]
    line = [cell("المجموع", bold=True), cell(totals[0], align_center=True, bold=True),
            cell(totals[1], align_center=True, bold=True), money_cell(totals[2], bold=True),
            money_cell(totals[3], bold=True), money_cell(totals[4], bold=True)]
    if paid is not None:
        line.append(money_cell(sum(p["amount"] for p in paid.values()), bold=True))
    out.append(line)
    return out


class StartPeriodDialog(QDialog):
    """أول بداية للحساب: اختيار تاريخ البداية."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("بداية الحساب")
        self.date = date_edit()
        layout = QVBoxLayout(self)
        note = QLabel("اختر تاريخ بداية أول فترة حساب. تُحسب الأسابيع الأربعة ابتداءً من هذا اليوم، "
                      "وفي يوم الراتب تضغط «بداية الحساب» مرة أخرى لإغلاق الفترة ودفع الرواتب.")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        row.addWidget(QLabel("تاريخ البداية:"))
        row.addWidget(self.date)
        row.addStretch()
        layout.addLayout(row)
        buttons = QDialogButtonBox()
        buttons.addButton("بدء الحساب", QDialogButtonBox.AcceptRole).setObjectName("primary")
        buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class ClosePeriodDialog(QDialog):
    """يوم الراتب: عرض مستحقات كل أستاذ ثم إغلاق الفترة وبداية حساب جديد."""

    def __init__(self, store, period, parent=None):
        super().__init__(parent)
        self.store = store
        self.period = period
        self.setWindowTitle("بداية الحساب - دفع رواتب الأساتذة")
        self.resize(860, 560)
        self.end = date_edit()
        self.end.setMinimumDate(QDate.fromString(period["start_date"], "yyyy-MM-dd"))
        self.end.dateChanged.connect(self._refresh)
        self.table = make_table(HEADERS)
        self.next_label = QLabel()
        self.next_label.setStyleSheet("font-weight: bold")

        head = QLabel(f"الفترة تبدأ من {period['start_date']}. اختر آخر يوم يدخل في هذه الفترة "
                      "(عادة اليوم):")
        head.setWordWrap(True)
        row = QHBoxLayout()
        row.addWidget(head, 1)
        row.addWidget(self.end)
        layout = QVBoxLayout(self)
        layout.addLayout(row)
        layout.addWidget(self.table)
        layout.addWidget(self.next_label)
        buttons = QDialogButtonBox()
        buttons.addButton("✔ تسجيل دفع الرواتب وبداية حساب جديد",
                          QDialogButtonBox.AcceptRole).setObjectName("primary")
        buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh()

    def _refresh(self):
        self.rows = self.store.teachers_summary(self.period["start_date"], iso(self.end))
        fill_table(self.table, summary_rows(self.rows))
        self.table.setSortingEnabled(False)
        nxt = self.store._add_days(iso(self.end), 1)
        total = sum(r["net"] for r in self.rows)
        self.next_label.setText(f"مجموع الرواتب: {money(total)}   |   الحساب الجديد يبدأ من {nxt}")

    def _confirm(self):
        total = sum(r["net"] for r in self.rows)
        if confirm(self, f"تأكيد دفع {money(total)} للأساتذة عن الفترة من "
                         f"{self.period['start_date']} إلى {iso(self.end)}؟"):
            self.accept()


class PayrollPage(QWidget):
    WEEK, PERIOD = "week", "period"

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.mode = self.WEEK

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet("font-size: 12pt; font-weight: bold; padding: 6px")

        self.week_btn = QPushButton("📅 حصيلة الأسبوع")
        self.month_btn = QPushButton("📆 حصيلة الشهر (4 أسابيع)")
        self.start_btn = QPushButton("💰 بداية الحساب (دفع الرواتب)")
        self.start_btn.setObjectName("primary")
        for b in (self.week_btn, self.month_btn):
            b.setCheckable(True)
            b.setMinimumHeight(40)
        self.start_btn.setMinimumHeight(40)
        self.week_btn.clicked.connect(lambda: self._set_mode(self.WEEK))
        self.month_btn.clicked.connect(lambda: self._set_mode(self.PERIOD))
        self.start_btn.clicked.connect(self._start)
        buttons = QHBoxLayout()
        for b in (self.week_btn, self.month_btn, self.start_btn):
            buttons.addWidget(b)
        buttons.addStretch()

        self.period_combo = QComboBox()
        self.period_combo.setMinimumWidth(320)
        self.week_combo = QComboBox()
        self.week_combo.setMinimumWidth(260)
        self.week_label = QLabel("الأسبوع:")
        self.period_combo.currentIndexChanged.connect(self._period_changed)
        self.week_combo.currentIndexChanged.connect(self._show)
        print_btn = QPushButton("🖨 طباعة")
        print_btn.clicked.connect(self._print)
        self.undo_btn = QPushButton("تراجع عن آخر دفع")
        self.undo_btn.setObjectName("danger")
        self.undo_btn.clicked.connect(self._undo)
        selectors = QHBoxLayout()
        selectors.addWidget(QLabel("الفترة:"))
        selectors.addWidget(self.period_combo)
        selectors.addWidget(self.week_label)
        selectors.addWidget(self.week_combo)
        selectors.addStretch()
        selectors.addWidget(print_btn)
        selectors.addWidget(self.undo_btn)

        self.caption = QLabel()
        self.caption.setStyleSheet("font-size: 13pt; font-weight: bold; color: #1f3a5f")
        self.table = make_table(HEADERS)
        self.cards = QLabel()
        self.cards.setStyleSheet("font-size: 13pt; font-weight: bold")
        note = QLabel("الحصيلة تُحسب من الحصص المنجزة: كل حضور = سعر الحصة، تأخذ الأكاديمية نسبتها "
                      "والباقي للأستاذ. الأسبوع 1 = الأيام السبعة الأولى من بداية الفترة.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #5b6b80")

        layout = QVBoxLayout(self)
        layout.addWidget(title_label("الحصيلة والرواتب"))
        layout.addWidget(self.status)
        layout.addLayout(buttons)
        layout.addLayout(selectors)
        layout.addWidget(self.caption)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.cards)
        layout.addWidget(note)

    def showEvent(self, event):
        self.refresh()
        super().showEvent(event)

    # ------------------------------------------------------------ العرض
    def refresh(self):
        current = self.store.current_period()
        if current is None:
            self.status.setText("لم يبدأ الحساب بعد. اضغط «بداية الحساب» لتحديد تاريخ بداية أول فترة.")
            self.status.setStyleSheet("font-size: 12pt; font-weight: bold; padding: 6px; "
                                      f"color: {RED.name()}")
        else:
            week = min((current["days"] - 1) // 7 + 1, 99)
            text = (f"الفترة الحالية بدأت في {current['start_date']} — اليوم {current['days']} "
                    f"(الأسبوع {week} من {self.store.PERIOD_WEEKS})")
            color = "#1f3a5f"
            if current["due"]:
                text += "\n⚠ مرّت 4 أسابيع: حان موعد دفع رواتب الأساتذة (اضغط «بداية الحساب»)."
                color = RED.name()
            self.status.setText(text)
            self.status.setStyleSheet(f"font-size: 12pt; font-weight: bold; padding: 6px; "
                                      f"color: {color}")
        selected = self.period_combo.currentData()
        self.periods = {p["id"]: p for p in self.store.list_periods()}
        self.period_combo.blockSignals(True)
        self.period_combo.clear()
        for p in self.periods.values():
            self.period_combo.addItem(period_label(p), p["id"])
        index = self.period_combo.findData(selected)
        self.period_combo.setCurrentIndex(index if index >= 0 else 0)
        self.period_combo.blockSignals(False)
        self.undo_btn.setEnabled(any(not p["is_open"] for p in self.periods.values()))
        self._period_changed()

    def _set_mode(self, mode):
        self.mode = mode
        self._period_changed()

    def _period_changed(self):
        self.week_btn.setChecked(self.mode == self.WEEK)
        self.month_btn.setChecked(self.mode == self.PERIOD)
        self.week_label.setVisible(self.mode == self.WEEK)
        self.week_combo.setVisible(self.mode == self.WEEK)
        period = self.periods.get(self.period_combo.currentData())
        self.week_combo.blockSignals(True)
        self.week_combo.clear()
        if period:
            today = QDate.currentDate().toString("yyyy-MM-dd")
            current_index = 0
            for i, w in enumerate(self.store.period_weeks(period)):
                self.week_combo.addItem(f"الأسبوع {w['number']}: {w['start']} → {w['end']}",
                                        (w["start"], w["end"], w["number"]))
                if w["start"] <= today:
                    current_index = i
            self.week_combo.setCurrentIndex(current_index)
        self.week_combo.blockSignals(False)
        self._show()

    def _range(self):
        period = self.periods.get(self.period_combo.currentData())
        if period is None:
            return None
        if self.mode == self.WEEK:
            data = self.week_combo.currentData()
            if data is None:
                return None
            start, end, number = data
            return start, end, f"حصيلة الأسبوع {number}", period
        end = period["end_date"] or max(QDate.currentDate().toString("yyyy-MM-dd"),
                                        period["start_date"])
        return period["start_date"], end, "حصيلة الشهر (فترة 4 أسابيع)", period

    def _show(self):
        rng = self._range()
        if rng is None:
            fill_table(self.table, [])
            self.caption.setText("")
            self.cards.setText("")
            return
        start, end, title, period = rng
        self.rows = self.store.teachers_summary(start, end)
        paid = None
        headers = list(HEADERS)
        if self.mode == self.PERIOD and not period["is_open"]:
            paid = self.store.period_payouts(period["id"])
            headers.append("المدفوع")
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        fill_table(self.table, summary_rows(self.rows, paid))
        self.table.setSortingEnabled(False)
        self.caption.setText(f"{title}: من {start} إلى {end}")
        total = sum(r["total"] for r in self.rows)
        academy = sum(r["academy"] for r in self.rows)
        self.cards.setText(f"القيمة الإجمالية: {money(total)}   |   نصيب الأكاديمية: "
                           f"{money(academy)}   |   نصيب الأساتذة: {money(total - academy)}")

    # --------------------------------------------------------- العمليات
    def _start(self):
        current = self.store.current_period()
        if current is None:
            dialog = StartPeriodDialog(self)
            if dialog.exec():
                _, ok = guarded(self, self.store.start_first_period, iso(dialog.date))
                if ok:
                    info(self, "بدأ الحساب. ستظهر حصيلة كل أسبوع هنا.")
            self.refresh()
            return
        if not current["due"] and not confirm(
                self, f"لم تمرّ 4 أسابيع بعد (اليوم {current['days']} من الفترة). "
                      "هل تريد دفع الرواتب وبداية حساب جديد الآن؟"):
            return
        dialog = ClosePeriodDialog(self.store, current, self)
        if not dialog.exec():
            return
        closed, ok = guarded(self, self.store.close_period, iso(dialog.end))
        if not ok:
            return
        self.mode = self.PERIOD
        self.refresh()
        self.period_combo.setCurrentIndex(self.period_combo.findData(closed))
        if confirm(self, "تم تسجيل دفع الرواتب وبدأ حساب جديد.\nهل تريد طباعة كشف الرواتب؟"):
            self._print()

    def _undo(self):
        if confirm(self, "التراجع عن آخر «بداية حساب»؟ ستُدمج الفترة الحالية مع الفترة السابقة "
                         "ويُلغى تسجيل الرواتب المدفوعة لها."):
            guarded(self, self.store.reopen_last_period)
            self.refresh()

    def _print(self):
        rng = self._range()
        if rng is None:
            error(self, "لا توجد بيانات للطباعة.")
            return
        start, end, title, period = rng
        rows = [[r["teacher_name"], r["lessons"], r["attendances"], money(r["total"]),
                 money(r["academy"]), money(r["net"]), ""] for r in self.rows]
        totals = ["المجموع"] + [sum(r[k] for r in self.rows) for k in ("lessons", "attendances")] \
            + [money(sum(r[k] for r in self.rows)) for k in ("total", "academy", "net")] + [""]
        html = printing.table_html(
            title, f"من {start} إلى {end}", HEADERS + ["توقيع الأستاذ"], rows,
            self.store.settings(), totals)
        printing.print_html(self, html)
