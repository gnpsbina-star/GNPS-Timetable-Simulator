#!/usr/bin/env python3
"""Tests for transfer_faculty.py: handing one teacher's whole timetable to another."""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from transfer_faculty import transfer_faculty, find_clashes, TransferError


SCHEMA = """
CREATE TABLE classes (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, class_teacher TEXT);
CREATE TABLE teachers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT);
CREATE TABLE schedule_entries (
    id INTEGER PRIMARY KEY, class_name TEXT, class_teacher TEXT, day TEXT,
    period_index INTEGER, period_name TEXT, period_time TEXT, raw_value TEXT,
    subject TEXT, teacher TEXT, is_joint INTEGER DEFAULT 0, joint_label TEXT,
    parallel_group_id TEXT, elective_basket TEXT
);
"""


class TestTransferFaculty(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cfg = {
            "teachers": [
                {"id": "Old Teacher", "name": "Old Teacher", "max_weekly_periods": 34},
                {"id": "New Teacher", "name": "New Teacher", "max_weekly_periods": 34},
                {"id": "Busy Teacher", "name": "Busy Teacher", "max_weekly_periods": 34},
                {"id": "Partner", "name": "Partner", "max_weekly_periods": 34},
            ],
            "classes": [
                {"id": "C1", "name": "CLASS 1 A", "class_teacher": "Old Teacher"},
                {"id": "C2", "name": "CLASS 2 A", "class_teacher": "Busy Teacher"},
            ],
            "events": [
                {"id": "EV1", "subject": "Eng", "teacher_ids": ["Old Teacher"], "section_ids": ["C1"]},
                {"id": "EV2", "subject": "Math", "teacher_ids": ["Busy Teacher"], "section_ids": ["C2"]},
                {"id": "EV3", "subject": "Bio / Maths", "teacher_ids": ["Old Teacher", "Partner"], "section_ids": ["C1"]},
            ],
        }
        with open(os.path.join(self.dir, "timetable_config.json"), "w", encoding="utf-8") as f:
            json.dump(self.cfg, f)

        conn = sqlite3.connect(os.path.join(self.dir, "timetable.sqlite"))
        conn.executescript(SCHEMA)
        conn.executemany("INSERT INTO classes (name, class_teacher) VALUES (?, ?)",
                         [("CLASS 1 A", "Old Teacher"), ("CLASS 2 A", "Busy Teacher")])
        conn.executemany("INSERT INTO teachers (name) VALUES (?)",
                         [("Old Teacher",), ("Busy Teacher",), ("Partner",)])
        rows = [
            ("CLASS 1 A", "Old Teacher", "Monday", 1, "Eng_Old Teacher", "Eng", "Old Teacher"),
            ("CLASS 1 A", "Old Teacher", "Monday", 2, "Bio_Old /Math_Partner", "Bio / Maths", "Old Teacher / Partner"),
            ("CLASS 1 A", "Old Teacher", "Monday", 3, "Lunch", "Lunch", "Old Teacher"),
            ("CLASS 2 A", "Busy Teacher", "Monday", 3, "Lunch", "Lunch", "Busy Teacher"),
            ("CLASS 2 A", "Busy Teacher", "Monday", 1, "Math_Busy Teacher", "Math", "Busy Teacher"),
            ("CLASS 2 A", "Busy Teacher", "Monday", 2, "Math_Busy Teacher", "Math", "Busy Teacher"),
        ]
        conn.executemany(
            "INSERT INTO schedule_entries (class_name, class_teacher, day, period_index, raw_value, subject, teacher) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
        conn.close()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _entries(self):
        conn = sqlite3.connect(os.path.join(self.dir, "timetable.sqlite"))
        try:
            return conn.execute(
                "SELECT class_name, class_teacher, day, period_index, raw_value, teacher FROM schedule_entries ORDER BY id"
            ).fetchall()
        finally:
            conn.close()

    def _config(self):
        with open(os.path.join(self.dir, "timetable_config.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_moves_all_periods_into_same_slots(self):
        summary = transfer_faculty("Old Teacher", "New Teacher", base_dir=self.dir, rebuild=False)
        # 2 lessons + the lunch duty
        self.assertEqual(summary["periods_moved"], 3)
        entries = self._entries()
        self.assertEqual(entries[0][2:], ("Monday", 1, "Eng_New Teacher", "New Teacher"))
        self.assertEqual(entries[1][5], "New Teacher / Partner")
        self.assertFalse(any("Old Teacher" in (e[5] or "") for e in entries))
        # Other teachers are untouched
        self.assertEqual(entries[2][5], "New Teacher")
        self.assertEqual(entries[4][5], "Busy Teacher")

    def test_moves_class_teacher_role_and_allocations(self):
        summary = transfer_faculty("Old Teacher", "New Teacher", base_dir=self.dir, rebuild=False)
        self.assertEqual(summary["class_teacher_of"], ["CLASS 1 A"])
        self.assertEqual(summary["events_moved"], 2)
        cfg = self._config()
        self.assertEqual(cfg["classes"][0]["class_teacher"], "New Teacher")
        self.assertEqual(cfg["events"][0]["teacher_ids"], ["New Teacher"])
        self.assertEqual(cfg["events"][2]["teacher_ids"], ["New Teacher", "Partner"])
        self.assertEqual(self._entries()[0][1], "New Teacher")

        conn = sqlite3.connect(os.path.join(self.dir, "timetable.sqlite"))
        try:
            self.assertEqual(conn.execute("SELECT class_teacher FROM classes WHERE name='CLASS 1 A'").fetchone()[0],
                             "New Teacher")
            self.assertIsNotNone(conn.execute("SELECT 1 FROM teachers WHERE name='New Teacher'").fetchone())
        finally:
            conn.close()

    def test_source_teacher_stays_in_catalog(self):
        transfer_faculty("Old Teacher", "New Teacher", base_dir=self.dir, rebuild=False)
        names = [t["name"] for t in self._config()["teachers"]]
        self.assertIn("Old Teacher", names)

    def test_target_must_exist_in_catalog(self):
        with self.assertRaises(TransferError):
            transfer_faculty("Old Teacher", "Nobody", base_dir=self.dir, rebuild=False)

    def test_same_teacher_rejected(self):
        with self.assertRaises(TransferError):
            transfer_faculty("Old Teacher", "old teacher", base_dir=self.dir, rebuild=False)

    def test_clash_refused_without_force(self):
        clashes = find_clashes(os.path.join(self.dir, "timetable.sqlite"), "Old Teacher", "Busy Teacher")
        self.assertEqual([(c["day"], c["period_index"]) for c in clashes], [("Monday", 1), ("Monday", 2)])
        before = self._entries()
        with self.assertRaises(TransferError) as ctx:
            transfer_faculty("Old Teacher", "Busy Teacher", base_dir=self.dir, rebuild=False)
        self.assertEqual(len(ctx.exception.clashes), 2)
        # Nothing was changed
        self.assertEqual(self._entries(), before)
        self.assertEqual(self._config()["classes"][0]["class_teacher"], "Old Teacher")

    def test_clash_allowed_with_force(self):
        summary = transfer_faculty("Old Teacher", "Busy Teacher", base_dir=self.dir, force=True, rebuild=False)
        self.assertEqual(summary["periods_moved"], 3)
        self.assertEqual(len(summary["clashes"]), 2)

    def test_joint_period_with_target_does_not_duplicate_name(self):
        transfer_faculty("Old Teacher", "Partner", base_dir=self.dir, rebuild=False)
        self.assertEqual(self._entries()[1][5], "Partner")
        self.assertEqual(self._config()["events"][2]["teacher_ids"], ["Partner"])

    def test_overload_warning(self):
        cfg = self._config()
        cfg["teachers"][1]["max_weekly_periods"] = 1
        with open(os.path.join(self.dir, "timetable_config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        summary = transfer_faculty("Old Teacher", "New Teacher", base_dir=self.dir, rebuild=False)
        self.assertEqual(summary["new_weekly_load"], 2)
        self.assertIn("above their cap", summary["warning"])


if __name__ == "__main__":
    unittest.main()
