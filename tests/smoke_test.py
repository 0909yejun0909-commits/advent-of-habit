#!/usr/bin/env python3
"""Headless smoke test: builds the widget and history window against a throwaway
data folder, exercises the main paths, and saves screenshots.

    QT_QPA_PLATFORM=offscreen python tests/smoke_test.py [screenshot_dir]
"""
import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

# Point the app's data folder at a temp dir before anything reads it
tmp = tempfile.mkdtemp()
os.environ["HOME"] = tmp
os.environ["APPDATA"] = tmp
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication  # noqa: E402
import habit_tracker as h  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "screenshots")
out.mkdir(parents=True, exist_ok=True)

habits = ["Meditate", "Gym", "Read", "Sleep by 12"]
data_dir = h.dataDir()
data_dir.mkdir(parents=True, exist_ok=True)
(data_dir / "config.json").write_text(json.dumps({
    "habits": habits, "start_time": "06:00", "end_time": "11:00",
    "position": [54, 54], "locked": True,
}))
today = date.today()
history = {
    (today - timedelta(days=i)).isoformat(): {name: (i + j) % 3 != 0 for j, name in enumerate(habits)}
    for i in range(1, 45)
}
(data_dir / "habit_data.json").write_text(json.dumps(history))

app = QApplication(sys.argv)
h.configureApp(app)
widget = h.HabitWidget()
widget.show()
if not h.HAS_APPKIT:
    # Exercise the Qt stay-on-bottom/top fallback used on Windows and Linux
    widget.applyLevel()
    widget.bringToFront()
    widget.sendToDesktop()
app.processEvents()

assert widget.size().width() == h.WIDGET_WIDTH, widget.size()
assert widget.size().height() == h.LARGE_HEIGHT, widget.size()  # 4 habits -> large

widget.checkboxes["Gym"].setChecked(True)
saved = json.loads((data_dir / "habit_data.json").read_text())
assert saved[today.isoformat()]["Gym"] is True, saved[today.isoformat()]
assert widget.summary_label.text() == "1 of 4", widget.summary_label.text()

current, best = h.streaks(saved, "Gym")
assert current >= 1 and best >= current, (current, best)
assert 0 < h.recentRate(saved, None) <= 1

widget.grab().save(str(out / "widget.png"))

widget.openHistory()
widget.history.shiftMonth(-1)
widget.history.shiftMonth(1)
widget.history.select("Gym")
app.processEvents()
widget.history.grab().save(str(out / "history.png"))

print(f"smoke test passed on {sys.platform}; screenshots in {out}")
