"""صفحة الأفواج وإدارة تلاميذ كل فوج."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from .common import (
    RED, cell, error, fill_combo, fill_table, guarded, make_table, selected_id, title_label,
)


class GroupDialog(QDialog):
    def __init__(self, store, group_id=None, parent=None):
        super().__init__(parent)
        self.store = store
        self.group_id = group_id
        self.setWindowTitle("تعديل فوج" if group_id else "فوج جديد")
        self.setMinimumWidth(480)
        g = store.get_group(group_id) if group_id else None

        self.name = QLineEdit(g["name"] if g else "فوج 1")
        self.teacher = QComboBox()
        teachers = store.list_teachers(active_only=not g)
        fill_combo(self.teacher, [(t["full_name"], t["id"]) for t in teachers], "— اختر —",
                   g["teacher_id"] if g else None)
        self.subject = QComboBox()
        fill_combo(self.subject, [(s["name"], s["id"]) for s in store.list_subjects()],
                   "— اختر —", g["subject_id"] if g else None)
        self.level = QComboBox()
        fill_combo(self.level, [(l["name"], l["id"]) for l in store.list_levels()],
                   "— اختر —", g["level_id"] if g else None)
        self.room = QLineEdit(g["room"] if g else "")
        self.schedule = QLineEdit(g["schedule"] if g else "")
        self.schedule.setPlaceholderText("مثال: السبت 14:00 و الثلاثاء 16:00")
        self.capacity = QSpinBox()
        self.capacity.setRange(0, 200)
        self.capacity.setSpecialValueText("غير محدد")
        self.capacity.setValue(g["capacity"] if g else 0)
        self.active = QCheckBox("فوج نشط")
        self.active.setChecked(bool(g["active"]) if g else True)

        form = QFormLayout()
        form.addRow("اسم الفوج: *", self.name)
        form.addRow("الأستاذ: *", self.teacher)
        form.addRow("المادة: *", self.subject)
        form.addRow("المستوى: *", self.level)
        form.addRow("القاعة:", self.room)
        form.addRow("التوقيت:", self.schedule)
        form.addRow("الحد الأقصى للتلاميذ:", self.capacity)
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
        data = {
            "id": self.group_id, "name": self.name.text(),
            "teacher_id": self.teacher.currentData(), "subject_id": self.subject.currentData(),
            "level_id": self.level.currentData(), "room": self.room.text(),
            "schedule": self.schedule.text(), "capacity": self.capacity.value(),
            "active": self.active.isChecked(),
        }
        _, ok = guarded(self, self.store.save_group, data)
        if ok:
            self.accept()


class MembersDialog(QDialog):
    """اختيار تلاميذ الفوج من قائمة بحث مع خانات تأشير."""

    def __init__(self, store, group_id: int, parent=None):
        super().__init__(parent)
        self.store = store
        self.group = store.get_group(group_id)
        self.checked = store.group_member_ids(group_id)
        self.setWindowTitle(f"تلاميذ الفوج - {self.group['subject_name']} "
                            f"{self.group['level_name']} ({self.group['name']})")
        self.resize(560, 600)

        self.search = QLineEdit()
        self.search.setPlaceholderText("بحث...")
        self.search.setClearButtonEnabled(True)
        self.same_level = QCheckBox("تلاميذ نفس المستوى فقط")
        self.same_level.setChecked(True)
        self.list = QListWidget()
        self.summary = QLabel()

        layout = QVBoxLayout(self)
        layout.addWidget(self.search)
        layout.addWidget(self.same_level)
        layout.addWidget(self.list)
        layout.addWidget(self.summary)
        buttons = QDialogButtonBox()
        buttons.addButton("حفظ", QDialogButtonBox.AcceptRole).setObjectName("primary")
        buttons.addButton("إلغاء", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.search.textChanged.connect(self._load)
        self.same_level.toggled.connect(self._load)
        self.list.itemChanged.connect(self._toggled)
        self._load()

    def _load(self):
        self.list.blockSignals(True)
        self.list.clear()
        level = self.group["level_id"] if self.same_level.isChecked() else None
        for s in self.store.list_students(search=self.search.text().strip(), active_only=True):
            if level and s["level_id"] != level and s["id"] not in self.checked:
                continue
            item = QListWidgetItem(f"{s['full_name']}  —  {s['level_name'] or ''}")
            item.setData(Qt.UserRole, s["id"])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if s["id"] in self.checked else Qt.Unchecked)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._update_summary()

    def _toggled(self, item):
        sid = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked:
            self.checked.add(sid)
        else:
            self.checked.discard(sid)
        self._update_summary()

    def _update_summary(self):
        cap = self.group["capacity"]
        text = f"عدد التلاميذ المختارين: {len(self.checked)}"
        if cap:
            text += f" / {cap}"
            if len(self.checked) > cap:
                text += "  (تجاوز الحد الأقصى!)"
        self.summary.setText(text)

    def _save(self):
        self.store.set_group_members(self.group["id"], self.checked)
        self.accept()


class GroupsPage(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.search = QLineEdit()
        self.search.setPlaceholderText("بحث بالمادة أو الأستاذ أو المستوى...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        self.show_inactive = QCheckBox("إظهار الأفواج المتوقفة")
        self.show_inactive.toggled.connect(self.refresh)

        self.table = make_table(["الرقم", "المادة", "المستوى", "الفوج", "الأستاذ", "التوقيت",
                                 "القاعة", "التلاميذ"])
        self.table.doubleClicked.connect(self._edit)

        new_btn = QPushButton("+ فوج جديد")
        new_btn.setObjectName("primary")
        new_btn.clicked.connect(self._new)
        edit_btn = QPushButton("تعديل")
        edit_btn.clicked.connect(self._edit)
        members_btn = QPushButton("👥 تلاميذ الفوج")
        members_btn.clicked.connect(self._members)
        actions = QHBoxLayout()
        for b in (new_btn, edit_btn, members_btn):
            actions.addWidget(b)
        actions.addWidget(self.search, 1)
        actions.addWidget(self.show_inactive)

        layout = QVBoxLayout(self)
        layout.addWidget(title_label("الأفواج"))
        layout.addLayout(actions)
        layout.addWidget(self.table)

    def showEvent(self, event):
        self.refresh()
        super().showEvent(event)

    def refresh(self):
        groups = self.store.list_groups(active_only=not self.show_inactive.isChecked(),
                                        search=self.search.text().strip())
        rows = []
        for g in groups:
            members = f"{g['members']}" + (f" / {g['capacity']}" if g["capacity"] else "")
            rows.append([
                cell(g["id"], data=g["id"], align_center=True),
                cell(g["subject_name"], bold=True, color=None if g["active"] else RED),
                g["level_name"], g["name"], g["teacher_name"], g["schedule"], g["room"],
                cell(members, align_center=True, sort_key=g["members"]),
            ])
        fill_table(self.table, rows)

    def _current(self):
        gid = selected_id(self.table)
        if gid is None:
            error(self, "اختر فوجاً من القائمة أولاً.")
        return gid

    def _new(self):
        if not self.store.list_teachers(active_only=True):
            error(self, "أضف أستاذاً أولاً من صفحة الأساتذة.")
            return
        if GroupDialog(self.store, parent=self).exec():
            self.refresh()

    def _edit(self):
        gid = self._current()
        if gid and GroupDialog(self.store, gid, parent=self).exec():
            self.refresh()

    def _members(self):
        gid = self._current()
        if gid and MembersDialog(self.store, gid, parent=self).exec():
            self.refresh()
