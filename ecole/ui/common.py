"""أدوات مشتركة للواجهة: التنسيق، الجداول، الرسائل."""

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDateEdit, QHeaderView, QLabel, QMessageBox,
    QTableWidget, QTableWidgetItem, QWidget,
)

from ..services import ServiceError

GREEN = QColor("#1b7f3b")
RED = QColor("#c62828")
GREY = QColor("#888888")

STYLE = """
* { font-size: 11pt; }
QMainWindow, QDialog { background: #f4f6f9; }
#nav { background: #1f3a5f; }
#nav QPushButton {
    color: white; background: transparent; border: none; text-align: right;
    padding: 12px 18px; font-size: 12pt;
}
#nav QPushButton:hover { background: #2c4f7c; }
#nav QPushButton:checked { background: #f4f6f9; color: #1f3a5f; font-weight: bold; }
#navTitle { color: white; font-size: 14pt; font-weight: bold; padding: 18px 12px; }
#navUser { color: #c9d6e8; padding: 8px 12px; }
#pageTitle { font-size: 17pt; font-weight: bold; color: #1f3a5f; padding-bottom: 6px; }
QPushButton {
    background: #ffffff; border: 1px solid #b8c4d6; border-radius: 5px; padding: 6px 14px;
}
QPushButton:hover { background: #e8eef7; }
QPushButton#primary { background: #1f6fd1; color: white; border: none; font-weight: bold; }
QPushButton#primary:hover { background: #185bb0; }
QPushButton#danger { color: #c62828; }
QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {
    background: white; border: 1px solid #b8c4d6; border-radius: 4px; padding: 4px 6px;
}
QTableWidget { background: white; gridline-color: #e3e8ef; selection-background-color: #cfe0f7;
               selection-color: black; alternate-background-color: #f8fafc; }
QHeaderView::section { background: #e8eef7; padding: 6px; border: none;
                       border-bottom: 1px solid #b8c4d6; font-weight: bold; }
QGroupBox { font-weight: bold; border: 1px solid #ccd5e1; border-radius: 6px;
            margin-top: 14px; padding-top: 10px; background: white; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top right; padding: 0 8px; }
#card { background: white; border: 1px solid #dde3ec; border-radius: 8px; }
#cardValue { font-size: 20pt; font-weight: bold; color: #1f3a5f; }
#cardLabel { color: #5b6b80; }
QSpinBox, QDateEdit { padding: 4px; min-height: 22px; }
"""


LRM = "\u200e"


def has_arabic(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06ff" for ch in text)


def ltr(text: str) -> str:
    """يحمي الأرقام والهواتف من الانعكاس داخل نص عربي (اتجاه يمين-يسار)."""
    return f"{LRM}{text}{LRM}"


def money(value) -> str:
    return ltr(f"{int(value or 0):,}".replace(",", " ")) + " دج"


def money_cell(value, **kwargs) -> QTableWidgetItem:
    return cell(money(value), sort_key=int(value or 0), **kwargs)


def title_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("pageTitle")
    return label


def info(parent: QWidget, text: str) -> None:
    QMessageBox.information(parent, "معلومة", text)


def error(parent: QWidget, text: str) -> None:
    QMessageBox.warning(parent, "تنبيه", text)


def confirm(parent: QWidget, text: str) -> bool:
    box = QMessageBox(QMessageBox.Question, "تأكيد", text, parent=parent)
    yes = box.addButton("نعم", QMessageBox.YesRole)
    box.addButton("لا", QMessageBox.NoRole)
    box.exec()
    return box.clickedButton() is yes


def guarded(parent: QWidget, func, *args, **kwargs):
    """ينفذ عملية ويعرض رسالة الخطأ للمستخدم بدلاً من إيقاف البرنامج."""
    try:
        return func(*args, **kwargs), True
    except ServiceError as exc:
        error(parent, str(exc))
        return None, False


def make_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.horizontalHeader().setHighlightSections(False)
    # بدون ترتيب افتراضي: نحتفظ بترتيب البيانات حتى ينقر المستخدم على عنوان عمود.
    table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
    return table


class SortItem(QTableWidgetItem):
    """خانة تُرتّب حسب قيمة رقمية بدل النص."""

    def __lt__(self, other):
        a, b = self.data(SORT_ROLE), other.data(SORT_ROLE)
        if a is not None and b is not None:
            return a < b
        # لا نستعمل super().__lt__ لأنها تعود إلى هذه الدالة في PySide6.
        return self.text() < other.text()


SORT_ROLE = Qt.UserRole + 1


def cell(value, data=None, color: QColor | None = None, bold: bool = False,
         align_center: bool = False, sort_key=None) -> QTableWidgetItem:
    text = "" if value is None else str(value)
    if text and not has_arabic(text):
        text = ltr(text)
    item = SortItem(text)
    if isinstance(value, int) and sort_key is None:
        sort_key = value
    if sort_key is not None:
        item.setData(SORT_ROLE, sort_key)
    if data is not None:
        item.setData(Qt.UserRole, data)
    if color is not None:
        item.setForeground(color)
    if bold:
        font = item.font()
        font.setBold(True)
        item.setFont(font)
    if align_center:
        item.setTextAlignment(Qt.AlignCenter)
    return item


def fill_table(table: QTableWidget, rows: list[list]) -> None:
    """rows: قائمة صفوف، كل خانة إما قيمة أو QTableWidgetItem. الخانة الأولى تحمل المعرف."""
    table.setSortingEnabled(False)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            table.setItem(r, c, value if isinstance(value, QTableWidgetItem) else cell(value))
    table.setSortingEnabled(True)


def selected_id(table: QTableWidget):
    row = table.currentRow()
    if row < 0:
        return None
    item = table.item(row, 0)
    return item.data(Qt.UserRole) if item else None


def balance_cell(balance: int) -> QTableWidgetItem:
    if balance > 0:
        color, text = GREEN, f"{balance}"
    elif balance < 0:
        color, text = RED, f"{ltr(balance)} (دَين)"
    else:
        color, text = GREY, "0"
    return cell(text, color=color, bold=True, align_center=True, sort_key=balance)


def fill_combo(combo: QComboBox, items, placeholder: str | None = None,
               current=None) -> None:
    """items: قائمة (نص، قيمة)."""
    combo.blockSignals(True)
    combo.clear()
    if placeholder is not None:
        combo.addItem(placeholder, None)
    for text, value in items:
        combo.addItem(text, value)
    if current is not None:
        index = combo.findData(current)
        if index >= 0:
            combo.setCurrentIndex(index)
    combo.blockSignals(False)


def date_edit(value: QDate | None = None) -> QDateEdit:
    edit = QDateEdit(value or QDate.currentDate())
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("yyyy-MM-dd")
    edit.setLayoutDirection(Qt.LeftToRight)
    return edit


def iso(edit: QDateEdit) -> str:
    return edit.date().toString("yyyy-MM-dd")
