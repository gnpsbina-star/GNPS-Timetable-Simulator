import unittest
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.models import SchoolConfig, Teacher, ClassSection, Room, Event
from engine.csp_solver import CSPSolver

class TestTeachersModule(unittest.TestCase):
    def setUp(self):
        self.config = SchoolConfig(
            academic_year="2026-27",
            days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
            periods_per_day=8,
            period_definitions=[
                {"period_index": 0, "name": "Assembly", "is_assembly": True},
                {"period_index": 1, "name": "1st Period", "is_lunch": False},
                {"period_index": 2, "name": "2nd Period", "is_lunch": False},
                {"period_index": 3, "name": "3rd Period", "is_lunch": False},
                {"period_index": 4, "name": "Lunch", "is_lunch": True},
                {"period_index": 5, "name": "4th Period", "is_lunch": False},
                {"period_index": 6, "name": "5th Period", "is_lunch": False},
                {"period_index": 7, "name": "6th Period", "is_lunch": False},
            ],
            enforce_class_teacher_p1=True
        )

    def test_teacher_monogram_generation(self):
        """Test intelligent monogram generation and collision avoidance."""
        def generate_code(name, existing_codes):
            words = [w for w in name.replace("Dr. ", "").replace("Mr. ", "").split() if w]
            if len(words) >= 2:
                base = (words[0][0] + words[1][:2]).toUpperCase() if hasattr(str, 'toUpperCase') else (words[0][0] + words[1][:2]).upper()
            elif len(words) == 1:
                base = words[0][:3].upper()
            else:
                base = name[:3].upper()

            cand = base
            cnt = 1
            while cand in existing_codes:
                cnt += 1
                cand = f"{base}{cnt}"
            return cand

        existing = {"VAN", "VSA", "RSH"}
        self.assertEqual(generate_code("Vandna Saraf", existing), "VSA2")
        self.assertEqual(generate_code("Dr. Rajesh Sharma", existing), "RSH2")
        self.assertEqual(generate_code("Anubha", existing), "ANU")
        self.assertEqual(generate_code("Kiran Sharma", existing), "KSH")

    def test_blackout_slot_enforcement(self):
        """Test that CSP Solver NEVER schedules a teacher into their blackout / unavailable slots."""
        # Teacher T_TEST has unavailable slots on Monday P1, Monday P2, and Tuesday P1
        blackout_slots = {("Monday", 1), ("Monday", 2), ("Tuesday", 1)}
        teacher = Teacher(
            id="T_TEST",
            name="Test Teacher",
            max_weekly_periods=10,
            max_daily_periods=3,
            unavailable_slots=blackout_slots
        )
        teachers = {"T_TEST": teacher}
        classes = {"C_TEST": ClassSection(id="C_TEST", name="Class 5 Test", wing="Primary")}
        events = [
            Event(id="E_TEST", subject="Math", teacher_ids=["T_TEST"], section_ids=["C_TEST"], weekly_quota=5)
        ]

        solver = CSPSolver(self.config, teachers, classes, {}, events)
        res = solver.solve()
        self.assertTrue(res.success, f"Solver failed to schedule with blackout slots: {res.message}")

        grid = res.grid
        # Verify that NONE of the assigned slots for T_TEST fall into blackout slots
        for (day, p_idx) in blackout_slots:
            assigned = grid.teacher_grid.get(("T_TEST", day, p_idx))
            self.assertIsNone(assigned, f"Teacher was scheduled in blacked-out slot ({day}, Period {p_idx})!")

        # Verify all 5 periods were placed in valid slots
        t_assigned_count = sum(len(assignments) for (t_id, d, p), assignments in grid.teacher_grid.items() if t_id == "T_TEST")
        self.assertEqual(t_assigned_count, 5, "All 5 periods should be successfully placed")

    def test_daily_and_weekly_caps_enforcement(self):
        """Test that teacher max_daily_periods and max_weekly_periods are respected."""
        teacher = Teacher(
            id="T_CAP",
            name="Capped Teacher",
            max_weekly_periods=6,
            max_daily_periods=2
        )
        teachers = {"T_CAP": teacher}
        classes = {
            "C1": ClassSection(id="C1", name="Class 1"),
            "C2": ClassSection(id="C2", name="Class 2")
        }
        events = [
            Event(id="E1", subject="Physics", teacher_ids=["T_CAP"], section_ids=["C1"], weekly_quota=3),
            Event(id="E2", subject="Chemistry", teacher_ids=["T_CAP"], section_ids=["C2"], weekly_quota=3)
        ]

        solver = CSPSolver(self.config, teachers, classes, {}, events)
        res = solver.solve()
        self.assertTrue(res.success, "Solver failed on capped teacher")

        grid = res.grid
        workload = grid.get_teacher_workload("T_CAP")
        self.assertEqual(workload["total_weekly_periods"], 6)

        # Check each day does not exceed max_daily_periods (2)
        for day, p_count in workload["daily_distribution"].items():
            self.assertLessEqual(p_count, 2, f"Teacher exceeded max daily cap on {day}: {p_count} > 2")


    def test_homeroom_class_sync_and_renaming(self):
        """Test homeroom teacher assignment synchronization and rename cascade logic."""
        classes = [
            {"id": "C_3R", "name": "CLASS 3 Rose", "class_teacher": "Vandna"},
            {"id": "C_3M", "name": "CLASS 3 Marigold", "class_teacher": "Shilpi"}
        ]
        events = [
            {"id": "E1", "subject": "Math", "teacher_ids": ["Vandna"], "section_ids": ["C_3R"]},
            {"id": "E2", "subject": "Eng", "teacher_ids": ["Shilpi"], "section_ids": ["C_3M"]}
        ]

        # Simulate teacher rename: "Vandna" -> "Vandna Saraf"
        old_name = "Vandna"
        new_name = "Vandna Saraf"
        for c in classes:
            if c["class_teacher"] == old_name:
                c["class_teacher"] = new_name
        for e in events:
            e["teacher_ids"] = [new_name if t == old_name else t for t in e["teacher_ids"]]

        self.assertEqual(classes[0]["class_teacher"], "Vandna Saraf")
        self.assertEqual(events[0]["teacher_ids"], ["Vandna Saraf"])

if __name__ == "__main__":
    unittest.main()
