#!/usr/bin/env python3
import sys
import json
import calendar
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                           QCheckBox, QPushButton, QLabel, QSystemTrayIcon, QMenu,
                           QLineEdit, QDialog, QRadioButton, QFrame, QInputDialog,
                           QScrollArea)
from PyQt6.QtCore import Qt, QTimer, QTime, QRectF, pyqtSignal
from PyQt6.QtGui import QIcon, QAction, QColor, QPixmap, QPainter, QPen, QFont

try:
    import objc
    from AppKit import (NSApplication, NSFloatingWindowLevel,
                        NSWindowCollectionBehaviorCanJoinAllSpaces,
                        NSWindowCollectionBehaviorStationary,
                        NSWindowCollectionBehaviorIgnoresCycle)
    from Quartz import CGWindowLevelForKey, kCGDesktopIconWindowLevelKey
    HAS_APPKIT = True
except ImportError:
    HAS_APPKIT = False


# Sampled from the native macOS desktop widgets
WIDGET_BG = "#414141"
TEXT = "#ffffff"
MUTED = "#a9a9a9"
FAINT = "#575757"
DIVIDER = "#545454"
RING = "#707070"
BUTTON = "#59595a"

# Native widget geometry (points)
WIDGET_WIDTH = 342
MEDIUM_HEIGHT = 162
LARGE_HEIGHT = 342
DEFAULT_POSITION = [54, 54]  # top-left, where macOS places the first desktop widget

STYLE = f"""
    QWidget {{
        color: {TEXT};
        font-family: ".AppleSystemUIFont";
        font-size: 13px;
    }}
    QDialog, #history {{
        background-color: #262626;
    }}
    #card {{
        background-color: {WIDGET_BG};
        border-radius: 23px;
    }}
    #panel {{
        background-color: {WIDGET_BG};
        border-radius: 16px;
    }}
    #heading {{
        font-size: 12px;
        font-weight: bold;
    }}
    #summary, #ratio, #empty, #caption, #hint {{
        color: {MUTED};
        font-size: 11px;
    }}
    #caption {{
        font-weight: bold;
    }}
    #title {{
        font-size: 20px;
        font-weight: bold;
    }}
    #month {{
        font-size: 13px;
        font-weight: bold;
    }}
    #divider {{
        background-color: {DIVIDER};
    }}
    QCheckBox {{
        spacing: 12px;
    }}
    QCheckBox:checked {{
        color: {MUTED};
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 2px solid {RING};
        border-radius: 10px;
        background-color: transparent;
    }}
    QCheckBox::indicator:checked {{
        background-color: {TEXT};
        border-color: {TEXT};
    }}
    QRadioButton {{
        spacing: 8px;
    }}
    QRadioButton::indicator {{
        width: 13px;
        height: 13px;
        border: 1px solid {RING};
        border-radius: 7px;
        background-color: transparent;
    }}
    QRadioButton::indicator:checked {{
        background-color: {TEXT};
        border-color: {TEXT};
    }}
    QLineEdit {{
        background-color: #1c1c1c;
        border: 1px solid {DIVIDER};
        border-radius: 6px;
        padding: 6px 8px;
        selection-background-color: #555555;
    }}
    QPushButton {{
        background-color: #3a3a3a;
        border: 1px solid {DIVIDER};
        border-radius: 6px;
        padding: 6px 12px;
    }}
    QPushButton:hover {{
        background-color: #484848;
    }}
    QPushButton#add {{
        background-color: {BUTTON};
        border: none;
        border-radius: 11px;
        padding: 0;
        font-size: 15px;
    }}
    QPushButton#add:hover {{
        background-color: #6a6a6a;
    }}
    QPushButton#hide, QPushButton#nav {{
        background-color: transparent;
        border: none;
        color: {MUTED};
        padding: 0 6px;
    }}
    QPushButton#hide {{
        font-size: 11px;
    }}
    QPushButton#nav {{
        font-size: 18px;
    }}
    QPushButton#hide:hover, QPushButton#nav:hover {{
        color: {TEXT};
    }}
    QScrollArea, QScrollArea > QWidget > QWidget {{
        background-color: transparent;
        border: none;
    }}
    QMenu {{
        background-color: #2e2e2e;
        border: 1px solid {DIVIDER};
        padding: 4px;
    }}
    QMenu::item {{
        padding: 5px 14px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{
        background-color: #484848;
    }}
"""


# --- Stats over habit_data.json ({"YYYY-MM-DD": {habit: bool}}) ---

def dateStr(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def isDone(data: Dict[str, Dict[str, bool]], d: date, habit: str) -> bool:
    return data.get(dateStr(d), {}).get(habit, False)


def dayFraction(data: Dict[str, Dict[str, bool]], d: date, habit: Optional[str] = None) -> Optional[float]:
    """Share of habits done on a day (or 0/1 for one habit); None if nothing was logged."""
    entry = data.get(dateStr(d))
    if not entry:
        return None
    if habit is not None:
        if habit not in entry:
            return None
        return 1.0 if entry[habit] else 0.0
    return sum(entry.values()) / len(entry)


def firstDay(data: Dict[str, Dict[str, bool]]) -> Optional[date]:
    days = [datetime.strptime(k, "%Y-%m-%d").date() for k in data]
    return min(days) if days else None


def streaks(data: Dict[str, Dict[str, bool]], habit: str) -> Tuple[int, int]:
    """(current streak, best streak) in days."""
    start = firstDay(data)
    if start is None:
        return 0, 0
    today = date.today()
    best = run = 0
    d = start
    while d <= today:
        run = run + 1 if isDone(data, d, habit) else 0
        best = max(best, run)
        d += timedelta(days=1)
    # Today still counts as "in progress", so an unticked today doesn't break the streak
    current = 0
    d = today if isDone(data, today, habit) else today - timedelta(days=1)
    while isDone(data, d, habit):
        current += 1
        d -= timedelta(days=1)
    return current, best


def recentRate(data: Dict[str, Dict[str, bool]], habit: Optional[str], days: int = 30) -> float:
    """Average completion over the last `days` days (or since tracking began)."""
    start = firstDay(data)
    if start is None:
        return 0.0
    today = date.today()
    span = min(days, (today - start).days + 1)
    total = 0.0
    for i in range(span):
        f = dayFraction(data, today - timedelta(days=i), habit)
        total += f or 0.0
    return total / span


def shade(f: float) -> QColor:
    v = int(0x58 + (0xf5 - 0x58) * f)
    return QColor(v, v, v)


class InitialSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Advent of Habit")
        self.setModal(True)
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)

        layout.addWidget(QLabel("What habits do you want to track?"))

        self.habit_inputs = []
        for default in ["Meditation", "Journaling", "Exercise"]:
            input_field = QLineEdit(default)
            self.habit_inputs.append(input_field)
            layout.addWidget(input_field)

        hint = QLabel("Add more anytime with + on the widget.")
        hint.setObjectName("hint")
        layout.addWidget(hint)

        layout.addSpacing(8)
        layout.addWidget(QLabel("When should it remind you?"))

        time_layout = QHBoxLayout()
        self.morning_radio = QRadioButton("Morning (6–11 AM)")
        self.evening_radio = QRadioButton("Evening (6–11 PM)")
        self.morning_radio.setChecked(True)
        time_layout.addWidget(self.morning_radio)
        time_layout.addWidget(self.evening_radio)
        layout.addLayout(time_layout)

        layout.addSpacing(8)
        done_button = QPushButton("Start")
        done_button.clicked.connect(self.accept)
        layout.addWidget(done_button)

        self.setLayout(layout)

    def getHabits(self) -> List[str]:
        return [f.text().strip() for f in self.habit_inputs if f.text().strip()]

    def getTimeWindow(self) -> Tuple[QTime, QTime]:
        if self.morning_radio.isChecked():
            return QTime(6, 0), QTime(11, 0)
        else:
            return QTime(18, 0), QTime(23, 0)


class WeekDots(QWidget):
    """Last 7 days for one habit, oldest on the left."""
    SIZE = 7
    GAP = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.days: List[bool] = [False] * 7
        self.setFixedSize(7 * self.SIZE + 6 * self.GAP, self.SIZE)

    def setDays(self, days: List[bool]) -> None:
        self.days = days
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        for i, done in enumerate(self.days):
            painter.setBrush(QColor(TEXT if done else FAINT))
            painter.drawRoundedRect(QRectF(i * (self.SIZE + self.GAP), 0, self.SIZE, self.SIZE), 2, 2)
        painter.end()


# --- History window ---

class MonthCalendar(QWidget):
    """Month grid; each day is shaded by how much got done."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data: Dict[str, Dict[str, bool]] = {}
        self.habit: Optional[str] = None
        self.year, self.month = date.today().year, date.today().month
        self.setMinimumSize(300, 270)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        today = date.today()
        weeks = calendar.Calendar(firstweekday=6).monthdatescalendar(self.year, self.month)

        head, gap = 20, 5
        cell = min((self.width() - 6 * gap) / 7,
                   (self.height() - head - len(weeks) * gap) / len(weeks))
        x0 = (self.width() - (7 * cell + 6 * gap)) / 2

        font = QFont(".AppleSystemUIFont", 10)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(MUTED))
        for i, name in enumerate("SMTWTFS"):
            painter.drawText(QRectF(x0 + i * (cell + gap), 0, cell, head), Qt.AlignmentFlag.AlignCenter, name)

        painter.setFont(QFont(".AppleSystemUIFont", 11))
        for r, week in enumerate(weeks):
            for c, d in enumerate(week):
                if d.month != self.month:
                    continue
                rect = QRectF(x0 + c * (cell + gap), head + gap + r * (cell + gap), cell, cell)
                f = dayFraction(self.data, d, self.habit) if d <= today else None
                if f is not None:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(shade(f))
                    painter.drawRoundedRect(rect, 6, 6)
                if d == today:
                    painter.setPen(QPen(QColor(TEXT), 1.5))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRoundedRect(rect.adjusted(0.75, 0.75, -0.75, -0.75), 6, 6)
                if f is not None and f > 0.55:
                    painter.setPen(QColor("#1a1a1a"))
                elif d <= today:
                    painter.setPen(QColor(TEXT))
                else:
                    painter.setPen(QColor("#6a6a6a"))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(d.day))
        painter.end()


class DailyBars(QWidget):
    """Bar per day for the last 30 days."""
    DAYS = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data: Dict[str, Dict[str, bool]] = {}
        self.habit: Optional[str] = None
        self.setMinimumHeight(110)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        today = date.today()
        label_h, gap = 16, 3
        chart_h = self.height() - label_h - 4
        bar_w = (self.width() - (self.DAYS - 1) * gap) / self.DAYS

        # 50% and 100% guides
        painter.setPen(QPen(QColor(DIVIDER), 1))
        for frac in (0.5, 1.0):
            y = chart_h - chart_h * frac
            painter.drawLine(0, int(y), self.width(), int(y))

        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(self.DAYS):
            d = today - timedelta(days=self.DAYS - 1 - i)
            f = dayFraction(self.data, d, self.habit)
            x = i * (bar_w + gap)
            if f:
                h = max(3, chart_h * f)
                painter.setBrush(QColor(TEXT))
            else:
                h = 3
                painter.setBrush(QColor(FAINT if f is None else "#7a7a7a"))
            painter.drawRoundedRect(QRectF(x, chart_h - h, bar_w, h), 2, 2)

        painter.setFont(QFont(".AppleSystemUIFont", 10))
        painter.setPen(QColor(MUTED))
        start = today - timedelta(days=self.DAYS - 1)
        painter.drawText(QRectF(0, chart_h + 4, 100, label_h), Qt.AlignmentFlag.AlignLeft, start.strftime("%b %-d"))
        painter.drawText(QRectF(self.width() - 100, chart_h + 4, 100, label_h), Qt.AlignmentFlag.AlignRight, "Today")
        painter.end()


class RateBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = 0.0
        self.setFixedHeight(4)

    def setValue(self, value: float) -> None:
        self.value = value
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(FAINT))
        painter.drawRoundedRect(QRectF(0, 0, self.width(), 4), 2, 2)
        if self.value > 0:
            painter.setBrush(QColor(TEXT))
            painter.drawRoundedRect(QRectF(0, 0, max(4, self.width() * self.value), 4), 2, 2)
        painter.end()


class StatRow(QFrame):
    clicked = pyqtSignal()

    def __init__(self, name: str, rate: float, detail: str, selected: bool, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"StatRow {{ border-radius: 8px; background-color: {'#4f4f4f' if selected else 'transparent'}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        top = QHBoxLayout()
        top.addWidget(QLabel(name), 1)
        percent = QLabel(f"{round(rate * 100)}%")
        percent.setStyleSheet("font-weight: bold;")
        top.addWidget(percent)
        layout.addLayout(top)

        bar = RateBar()
        bar.setValue(rate)
        layout.addWidget(bar)

        detail_label = QLabel(detail)
        detail_label.setObjectName("summary")
        layout.addWidget(detail_label)

    def mouseReleaseEvent(self, event) -> None:
        self.clicked.emit()


class HistoryWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("history")
        self.setWindowTitle("Habit History")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.habits: List[str] = []
        self.data: Dict[str, Dict[str, bool]] = {}
        self.selected: Optional[str] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("History")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        prev_button = QPushButton("‹")
        prev_button.setObjectName("nav")
        prev_button.clicked.connect(lambda: self.shiftMonth(-1))
        self.month_label = QLabel()
        self.month_label.setObjectName("month")
        next_button = QPushButton("›")
        next_button.setObjectName("nav")
        next_button.clicked.connect(lambda: self.shiftMonth(1))
        header.addWidget(prev_button)
        header.addWidget(self.month_label)
        header.addWidget(next_button)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(14)

        cal_panel, cal_layout = self.panel()
        self.cal_caption = QLabel()
        self.cal_caption.setObjectName("caption")
        cal_layout.addWidget(self.cal_caption)
        self.calendar = MonthCalendar()
        cal_layout.addWidget(self.calendar, 1)
        body.addWidget(cal_panel, 3)

        stats_panel, stats_panel_layout = self.panel()
        caption = QLabel("LAST 30 DAYS")
        caption.setObjectName("caption")
        stats_panel_layout.addWidget(caption)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        stats_container = QWidget()
        self.stats_layout = QVBoxLayout(stats_container)
        self.stats_layout.setContentsMargins(0, 0, 0, 0)
        self.stats_layout.setSpacing(4)
        scroll.setWidget(stats_container)
        stats_panel_layout.addWidget(scroll, 1)
        body.addWidget(stats_panel, 2)
        root.addLayout(body, 1)

        bars_panel, bars_layout = self.panel()
        self.bars_caption = QLabel()
        self.bars_caption.setObjectName("caption")
        bars_layout.addWidget(self.bars_caption)
        self.bars = DailyBars()
        bars_layout.addWidget(self.bars)
        root.addWidget(bars_panel)

        self.resize(780, 600)

    @staticmethod
    def panel() -> Tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)
        return frame, layout

    def shiftMonth(self, delta: int) -> None:
        month = self.calendar.month + delta
        self.calendar.year += (month - 1) // 12
        self.calendar.month = (month - 1) % 12 + 1
        self.refresh()

    def setData(self, habits: List[str], data: Dict[str, Dict[str, bool]]) -> None:
        self.habits = habits
        self.data = data
        if self.selected not in habits:
            self.selected = None
        self.refresh()

    def select(self, habit: Optional[str]) -> None:
        self.selected = habit
        self.refresh()

    def refresh(self) -> None:
        name = self.selected or "All habits"
        self.month_label.setText(date(self.calendar.year, self.calendar.month, 1).strftime("%B %Y"))
        self.cal_caption.setText(name.upper())
        self.bars_caption.setText(f"{name.upper()} · DAILY")
        for chart in (self.calendar, self.bars):
            chart.data = self.data
            chart.habit = self.selected
            chart.update()

        while self.stats_layout.count():
            widget = self.stats_layout.takeAt(0).widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        today_entry = self.data.get(dateStr(date.today()), {})
        done_today = sum(today_entry.get(h, False) for h in self.habits)
        rows = [(None, "All habits", recentRate(self.data, None),
                 f"{done_today} of {len(self.habits)} done today")]
        for habit in self.habits:
            current, best = streaks(self.data, habit)
            rows.append((habit, habit, recentRate(self.data, habit),
                         f"{current}-day streak · best {best}"))
        for key, label, rate, detail in rows:
            row = StatRow(label, rate, detail, key == self.selected)
            row.clicked.connect(lambda k=key: self.select(k))
            self.stats_layout.addWidget(row)
        self.stats_layout.addStretch()

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()


# --- Desktop widget ---

class HabitWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()

        app_support = Path.home() / "Library/Application Support/Advent of Habit"
        app_support.mkdir(parents=True, exist_ok=True)
        self.data_file = app_support / "habit_data.json"
        self.config_file = app_support / "config.json"

        self.position: List[int] = list(DEFAULT_POSITION)
        self.locked = False  # new installs start movable; lock it from the menu bar
        if not self.config_file.exists():
            self.setupInitialConfig()
        else:
            self.loadConfig()

        self.today = self.todayStr()
        self.front = False          # True while floating above other windows
        self.hidden_on: Optional[str] = None  # day the check-in reminder was dismissed
        self.press_pos = None
        self.drag_offset = None
        self.history = HistoryWindow()

        self.initUI()
        self.setupTrayIcon()
        self.rebuildHabits()

        # Every minute: roll over at midnight, pop up during the check-in window
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(60000)

    @staticmethod
    def todayStr() -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def setupInitialConfig(self) -> None:
        dialog = InitialSetupDialog()
        if dialog.exec():
            self.habits = dialog.getHabits()
            self.start_time, self.end_time = dialog.getTimeWindow()
        else:
            self.habits = ["Meditation", "Journaling", "Exercise"]
            self.start_time = QTime(6, 0)
            self.end_time = QTime(11, 0)
        self.saveConfig()

    def loadConfig(self) -> None:
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                self.habits = config.get('habits', ["Meditation", "Journaling", "Exercise"])
                self.start_time = QTime.fromString(config.get('start_time', '06:00'), "HH:mm")
                self.end_time = QTime.fromString(config.get('end_time', '11:00'), "HH:mm")
                self.position = config.get('position', self.position)
                self.locked = config.get('locked', False)
        except (json.JSONDecodeError, FileNotFoundError):
            self.habits = ["Meditation", "Journaling", "Exercise"]
            self.start_time = QTime(6, 0)
            self.end_time = QTime(11, 0)

    def saveConfig(self) -> None:
        with open(self.config_file, 'w') as f:
            json.dump({
                'habits': self.habits,
                'start_time': self.start_time.toString("HH:mm"),
                'end_time': self.end_time.toString("HH:mm"),
                'position': self.position,
                'locked': self.locked,
            }, f, indent=2)

    def initUI(self) -> None:
        self.setWindowTitle("Advent of Habit")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("card")
        outer.addWidget(card)

        self.card_layout = QVBoxLayout(card)
        self.card_layout.setContentsMargins(17, 15, 15, 12)
        self.card_layout.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(8)
        heading = QLabel("HABITS")
        heading.setObjectName("heading")
        header.addWidget(heading)
        self.summary_label = QLabel()
        self.summary_label.setObjectName("summary")
        header.addWidget(self.summary_label)
        header.addStretch()

        self.hide_button = QPushButton("hide")
        self.hide_button.setObjectName("hide")
        self.hide_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hide_button.clicked.connect(self.dismiss)
        self.hide_button.hide()
        header.addWidget(self.hide_button)

        add_button = QPushButton("+")
        add_button.setObjectName("add")
        add_button.setFixedSize(22, 22)
        add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        add_button.setToolTip("Add habit")
        add_button.clicked.connect(self.promptAddHabit)
        header.addWidget(add_button)
        self.card_layout.addLayout(header)

        self.card_layout.addSpacing(8)
        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        self.card_layout.addWidget(divider)
        self.card_layout.addSpacing(4)

        self.habits_layout = QVBoxLayout()
        self.habits_layout.setSpacing(0)
        self.card_layout.addLayout(self.habits_layout)
        self.card_layout.addStretch()

        self.move(*self.position)

    def rebuildHabits(self) -> None:
        while self.habits_layout.count():
            widget = self.habits_layout.takeAt(0).widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        self.checkboxes: Dict[str, QCheckBox] = {}
        self.dots: Dict[str, WeekDots] = {}
        self.ratio_labels: Dict[str, QLabel] = {}

        for habit in self.habits:
            row = QWidget()
            row.setFixedHeight(32)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)

            checkbox = QCheckBox(habit)
            checkbox.stateChanged.connect(self.saveData)
            self.checkboxes[habit] = checkbox
            row_layout.addWidget(checkbox, 1)

            dots = WeekDots()
            dots.setToolTip("Last 7 days")
            self.dots[habit] = dots
            row_layout.addWidget(dots)

            ratio = QLabel()
            ratio.setObjectName("ratio")
            ratio.setToolTip("Days done in the last 21")
            ratio.setMinimumWidth(30)
            ratio.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.ratio_labels[habit] = ratio
            row_layout.addWidget(ratio)

            for w in (row, checkbox):
                w.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                w.customContextMenuRequested.connect(
                    lambda pos, h=habit, src=w: self.showHabitMenu(h, src.mapToGlobal(pos)))

            self.habits_layout.addWidget(row)

        if not self.habits:
            empty = QLabel("Add a habit with +")
            empty.setObjectName("empty")
            empty.setFixedHeight(32)
            self.habits_layout.addWidget(empty)

        self.loadData()
        self.fitSize()

    def fitSize(self) -> None:
        # Snap to the native medium or large widget size, growing past large if needed
        margins = self.card_layout.contentsMargins()
        header = 22 + 8 + 1 + 4  # header row, spacing, divider, spacing
        needed = margins.top() + header + 32 * max(1, len(self.habits)) + margins.bottom()
        if needed <= MEDIUM_HEIGHT:
            height = MEDIUM_HEIGHT
        elif needed <= LARGE_HEIGHT:
            height = LARGE_HEIGHT
        else:
            height = needed
        self.setFixedSize(WIDGET_WIDTH, height)

    def showHabitMenu(self, habit: str, pos) -> None:
        menu = QMenu()
        remove_action = menu.addAction(f"Remove “{habit}”")
        if menu.exec(pos) == remove_action:
            self.habits.remove(habit)
            self.saveConfig()
            self.rebuildHabits()

    def promptAddHabit(self) -> None:
        self.activateApp()
        name, ok = QInputDialog.getText(None, "New habit", "Habit")
        name = name.strip()
        if ok and name and name not in self.habits:
            self.habits.append(name)
            self.saveConfig()
            self.rebuildHabits()

    def openHistory(self) -> None:
        self.history.setData(self.habits, self.readData())
        self.history.show()
        self.history.raise_()
        self.activateApp()

    # --- Window level: pinned to the desktop, or floating while it wants attention ---

    def nsWindow(self):
        if not HAS_APPKIT:
            return None
        try:
            return objc.objc_object(c_void_p=int(self.winId())).window()
        except Exception:
            return None

    def applyLevel(self) -> None:
        # Qt offsets frameless windows positioned before they're shown, so re-place it
        self.move(*self.position)
        nswin = self.nsWindow()
        if nswin is None:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.front)
            self.setWindowFlag(Qt.WindowType.WindowStaysOnBottomHint, not self.front)
            self.show()
            return
        if self.front:
            nswin.setLevel_(NSFloatingWindowLevel)
        else:
            nswin.setLevel_(CGWindowLevelForKey(kCGDesktopIconWindowLevelKey) + 1)
        nswin.setHasShadow_(False)
        nswin.setHidesOnDeactivate_(False)
        nswin.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces |
                                     NSWindowCollectionBehaviorStationary |
                                     NSWindowCollectionBehaviorIgnoresCycle)
        nswin.orderFrontRegardless()

    def activateApp(self) -> None:
        if HAS_APPKIT:
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    def bringToFront(self) -> None:
        self.front = True
        self.hide_button.show()
        self.applyLevel()
        self.activateApp()

    def sendToDesktop(self) -> None:
        self.front = False
        self.hide_button.hide()
        self.applyLevel()

    def dismiss(self) -> None:
        self.hidden_on = self.today
        self.sendToDesktop()

    def tick(self) -> None:
        if self.todayStr() != self.today:
            self.today = self.todayStr()
            self.loadData()
        self.checkCheckIn()

    def checkCheckIn(self) -> None:
        # Float above other windows during the check-in window until something
        # is logged today or the reminder is dismissed
        if self.front or self.hidden_on == self.today:
            return
        if self.start_time <= QTime.currentTime() <= self.end_time:
            if self.today not in self.readData():
                self.bringToFront()

    # --- Click opens history; dragging only when unlocked ---

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_pos = event.globalPosition().toPoint()
            if not self.locked:
                self.drag_offset = self.press_pos - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self.drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        if self.press_pos is None:
            return
        moved = (event.globalPosition().toPoint() - self.press_pos).manhattanLength() > 4
        if self.drag_offset is not None and moved:
            self.position = [self.x(), self.y()]
            self.saveConfig()
        elif not moved:
            self.openHistory()
        self.press_pos = None
        self.drag_offset = None

    def setLocked(self, locked: bool) -> None:
        self.locked = locked
        self.saveConfig()

    # --- Menu bar ---

    def setupTrayIcon(self) -> None:
        self.tray_icon = QSystemTrayIcon(self)

        # Monochrome checkmark; as a mask it follows the menu bar's light/dark tint
        pixmap = QPixmap(36, 36)
        pixmap.setDevicePixelRatio(2)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(Qt.GlobalColor.black, 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(4, 9, 7, 12)
        painter.drawLine(7, 12, 14, 5)
        painter.end()
        icon = QIcon(pixmap)
        icon.setIsMask(True)

        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("Advent of Habit")

        tray_menu = QMenu()
        history_action = QAction("Show History", self)
        show_action = QAction("Bring Widget to Front", self)
        add_action = QAction("Add Habit…", self)
        move_action = QAction("Allow Moving Widget", self)
        move_action.setCheckable(True)
        move_action.setChecked(not self.locked)
        quit_action = QAction("Quit", self)
        history_action.triggered.connect(self.openHistory)
        show_action.triggered.connect(self.bringToFront)
        add_action.triggered.connect(self.promptAddHabit)
        move_action.toggled.connect(lambda on: self.setLocked(not on))
        quit_action.triggered.connect(QApplication.instance().quit)

        tray_menu.addAction(history_action)
        tray_menu.addAction(show_action)
        tray_menu.addAction(add_action)
        tray_menu.addSeparator()
        tray_menu.addAction(move_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    # --- Data ---

    def readData(self) -> Dict[str, Dict[str, bool]]:
        try:
            with open(self.data_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def calculateStats(self, habit: str, data: Dict[str, Dict[str, bool]]) -> Tuple[int, int]:
        today = datetime.now().date()
        completed_days = 0
        total_days = 0

        for i in range(21):
            date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            if date_str in data:
                total_days += 1
                if data[date_str].get(habit, False):
                    completed_days += 1

        return completed_days, total_days if total_days > 0 else 1

    def refreshStats(self, data: Dict[str, Dict[str, bool]]) -> None:
        today = datetime.now().date()
        for habit in self.habits:
            completed, total = self.calculateStats(habit, data)
            self.ratio_labels[habit].setText(f"{completed}/{total}")
            self.dots[habit].setDays([isDone(data, today - timedelta(days=i), habit)
                                      for i in range(6, -1, -1)])
        done = sum(cb.isChecked() for cb in self.checkboxes.values())
        self.summary_label.setText(f"{done} of {len(self.habits)}" if self.habits else "")
        if self.history.isVisible():
            self.history.setData(self.habits, data)

    def loadData(self) -> None:
        data = self.readData()
        today_entry = data.get(self.today, {})
        for habit, checkbox in self.checkboxes.items():
            # Don't let restoring state count as checking in
            checkbox.blockSignals(True)
            checkbox.setChecked(today_entry.get(habit, False))
            checkbox.blockSignals(False)
        self.refreshStats(data)

    def saveData(self) -> None:
        data = self.readData()
        data[self.today] = {
            habit: checkbox.isChecked()
            for habit, checkbox in self.checkboxes.items()
        }
        with open(self.data_file, 'w') as f:
            json.dump(data, f, indent=2)
        self.refreshStats(data)

    def closeEvent(self, event) -> None:
        event.ignore()


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)
    window = HabitWidget()
    window.show()
    QTimer.singleShot(0, window.applyLevel)
    QTimer.singleShot(0, window.checkCheckIn)
    sys.exit(app.exec())
