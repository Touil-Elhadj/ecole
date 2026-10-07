"""طباعة الوصولات والتقارير على طابعة عادية (A4) أو طابعة وصولات حرارية (80 ملم)."""

from html import escape

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import QMessageBox, QWidget

A4 = "a4"
THERMAL = "thermal"


LRM = "\u200e"


def _fmt(value) -> str:
    return LRM + f"{int(value or 0):,}".replace(",", " ") + LRM + " دج"


def _text(value) -> str:
    """نص آمن للـ HTML، والأرقام/الهواتف محمية من الانعكاس."""
    text = str(value)
    if text and not any("\u0600" <= ch <= "\u06ff" for ch in text):
        text = LRM + text + LRM
    return escape(text)


def receipt_html(payment, settings: dict, balance_after: int, paper: str) -> str:
    big = "16pt" if paper == A4 else "11pt"
    normal = "11pt" if paper == A4 else "8pt"
    status = '<p style="color:#c62828; font-weight:bold">دفعة ملغاة</p>' if payment["cancelled"] else ""
    lines = [
        ("رقم الوصل", payment["receipt_no"]),
        ("التاريخ", payment["paid_at"][:16]),
        ("التلميذ", payment["student_name"]),
        ("المستوى", payment["level_name"] or "-"),
        ("عدد الحصص", payment["sessions"]),
        ("المبلغ", _fmt(payment["amount"])),
        ("الرصيد بعد الدفع", f"{balance_after} حصة"),
        ("المستلم", payment["user_name"] or "-"),
    ]
    rows = "".join(
        f'<tr><td style="padding:3px; color:#555">{escape(k)}</td>'
        f'<td style="padding:3px; font-weight:bold">{_text(v)}</td></tr>'
        for k, v in lines)
    contact = " - ".join(x for x in (settings.get("academy_address", ""),
                                     settings.get("academy_phone", "")) if x)
    return f"""
    <html><body dir="rtl" style="font-family:'Segoe UI', Tahoma, Arial; font-size:{normal}">
      <div align="center">
        <div style="font-size:{big}; font-weight:bold">{escape(settings.get('academy_name', ''))}</div>
        <div>{escape(contact)}</div>
        <hr/>
        <div style="font-size:{big}; font-weight:bold">وصل دفع</div>
        {status}
      </div>
      <table width="100%" dir="rtl">{rows}</table>
      <hr/>
      <div align="center">{escape(settings.get('receipt_footer', ''))}</div>
    </body></html>"""


def table_html(title: str, subtitle: str, headers: list[str], rows: list[list],
               settings: dict, totals: list | None = None) -> str:
    head = "".join(f'<th style="background:#e8eef7; padding:5px; border:1px solid #999">'
                   f"{escape(h)}</th>" for h in headers)

    def tr(values, bold=False):
        weight = "font-weight:bold;" if bold else ""
        return "<tr>" + "".join(
            f'<td style="padding:4px; border:1px solid #999; {weight}">{_text(v)}</td>'
            for v in values) + "</tr>"

    body = "".join(tr(r) for r in rows)
    if totals:
        body += tr(totals, bold=True)
    return f"""
    <html><body dir="rtl" style="font-family:'Segoe UI', Tahoma, Arial; font-size:10pt">
      <div align="center">
        <div style="font-size:15pt; font-weight:bold">{escape(settings.get('academy_name', ''))}</div>
        <div style="font-size:13pt; font-weight:bold">{escape(title)}</div>
        <div>{escape(subtitle)}</div>
      </div><br/>
      <table width="100%" cellspacing="0" dir="rtl">
        <thead><tr>{head}</tr></thead>{body}
      </table>
    </body></html>"""


def _configure(printer: QPrinter, paper: str) -> None:
    if paper == THERMAL:
        # ورق 80 ملم بطول كافٍ لوصل واحد.
        printer.setPageSize(QPageSize(QSizeF(80, 140), QPageSize.Millimeter, "80mm"))
        printer.setPageMargins(QMarginsF(3, 3, 3, 3), QPageLayout.Millimeter)
    else:
        printer.setPageSize(QPageSize(QPageSize.A4))
        printer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Millimeter)


def _document(html: str, printer: QPrinter) -> QTextDocument:
    doc = QTextDocument()
    doc.setHtml(html)
    doc.setPageSize(printer.pageRect(QPrinter.Point).size())
    return doc


def print_html(parent: QWidget, html: str, paper: str = A4, preview: bool = True) -> None:
    printer = QPrinter(QPrinter.HighResolution)
    _configure(printer, paper)
    if preview:
        dialog = QPrintPreviewDialog(printer, parent)
        dialog.setWindowTitle("معاينة قبل الطباعة")
        dialog.paintRequested.connect(lambda p: _document(html, p).print_(p))
        dialog.resize(900, 700)
        dialog.exec()
        return
    dialog = QPrintDialog(printer, parent)
    if dialog.exec() == QPrintDialog.Accepted:
        _document(html, printer).print_(printer)


def save_pdf(html: str, path: str, paper: str = A4) -> None:
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(path)
    _configure(printer, paper)
    _document(html, printer).print_(printer)


def ask_paper(parent: QWidget) -> str | None:
    box = QMessageBox(QMessageBox.Question, "الطباعة", "اختر نوع الطابعة:", parent=parent)
    thermal = box.addButton("طابعة وصولات (80 ملم)", QMessageBox.AcceptRole)
    a4 = box.addButton("طابعة عادية A4", QMessageBox.AcceptRole)
    box.addButton("بدون طباعة", QMessageBox.RejectRole)
    box.exec()
    clicked = box.clickedButton()
    if clicked is thermal:
        return THERMAL
    if clicked is a4:
        return A4
    return None


def print_receipt(parent: QWidget, store, payment_id: int) -> None:
    paper = ask_paper(parent)
    if paper is None:
        return
    payment = store.get_payment(payment_id)
    balance = _balance_after(store, payment)
    print_html(parent, receipt_html(payment, store.settings(), balance, paper), paper)


def _balance_after(store, payment) -> int:
    """الرصيد مباشرة بعد هذه الدفعة (حسب كشف الحساب)."""
    for event in store.student_statement(payment["student_id"]):
        if event["receipt_no"] == payment["receipt_no"]:
            return event["balance"]
    return store.student_balance(payment["student_id"])
