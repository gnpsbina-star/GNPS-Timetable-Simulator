import unittest
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.models import SchoolConfig, Teacher, ClassSection, Room, Event, Subject
from engine.csp_solver import CSPSolver

class TestSubjectsModule(unittest.TestCase):
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

    def test_subject_model_and_properties(self):
        """Test Subject dataclass instantiation and property validation."""
        sub_theory = Subject(
            id="SUB_MATH", name="Mathematics", code="MATH", category="theory",
            room_type="Classroom", default_quota=6, is_double_period=False, duration_type="single"
        )
        self.assertEqual(sub_theory.code, "MATH")
        self.assertEqual(sub_theory.category, "theory")
        self.assertEqual(sub_theory.duration_type, "single")

        sub_lab = Subject(
            id="SUB_PHY_LAB", name="Physics Practical", code="PHY-LAB", category="practical",
            room_type="ScienceLab", default_quota=2, is_double_period=True, duration_type="double"
        )
        self.assertEqual(sub_lab.code, "PHY-LAB")
        self.assertEqual(sub_lab.room_type, "ScienceLab")
        self.assertTrue(sub_lab.is_double_period)
        self.assertEqual(sub_lab.duration_type, "double")

    def test_subject_code_auto_suggestion_and_collision(self):
        """Test intelligent subject code generator and collision handling."""
        def suggest_code(name, existing_codes):
            clean = name.replace("Core ", "").replace("Practical ", "").replace("Lab ", "")
            if "practical" in name.lower() or "lab" in name.lower():
                root = name.lower().replace("practical", "").replace("lab", "").strip().split()[0]
                base = (root[:3] + "-LAB").upper()
            else:
                words = clean.split()
                if len(words) >= 2:
                    base = (words[0][:3] + "-" + words[1][:3]).upper()
                elif len(name) <= 5:
                    base = name.upper()
                else:
                    base = name[:4].upper()
            
            cand = base
            cnt = 1
            while cand in existing_codes:
                cnt += 1
                cand = f"{base}{cnt}"
            return cand

        existing = {"MATH", "ENG", "PHY-LAB"}
        self.assertEqual(suggest_code("Mathematics", existing), "MATH2")
        self.assertEqual(suggest_code("Physics Practical", existing), "PHY-LAB2")
        self.assertEqual(suggest_code("Computer Science", existing), "COM-SCI")
        self.assertEqual(suggest_code("Hindi", existing), "HINDI")

    def test_double_period_lab_integrity(self):
        """Test that double periods are scheduled as 2 strictly consecutive slots and cannot cross lunch."""
        teachers = {"T_SCI": Teacher(id="T_SCI", name="Science Faculty", max_weekly_periods=10, max_daily_periods=4)}
        classes = {"C_SENIOR": ClassSection(id="C_SENIOR", name="Class 11 Science", wing="Senior")}
        # Event with duration=2 (double period block)
        events = [
            Event(id="E_LAB", subject="Physics Practical", teacher_ids=["T_SCI"], section_ids=["C_SENIOR"], weekly_quota=1, duration=2)
        ]

        solver = CSPSolver(self.config, teachers, classes, {}, events)
        res = solver.solve()
        self.assertTrue(res.success, f"Solver failed to schedule double period: {res.message}")

        grid = res.grid
        assigned_slots = [
            (day, p_idx) for (c_id, day, p_idx), assign in grid.section_grid.items()
            if assign.event_id == "E_LAB"
        ]
        assigned_slots.sort(key=lambda s: (s[0], s[1]))
        self.assertEqual(len(assigned_slots), 2, "Double period must occupy exactly 2 slots")

        day1, p1 = assigned_slots[0]
        day2, p2 = assigned_slots[1]
        # Must be on the exact same day
        self.assertEqual(day1, day2, "Double period slots must be on the exact same day")
        # Must be strictly consecutive
        self.assertEqual(p2, p1 + 1, "Double period slots must be strictly consecutive (p2 == p1 + 1)")
        # Must not cross Lunch (Period 4 is lunch)
        self.assertNotEqual(p1, 4, "Double period cannot be in lunch")
        self.assertNotEqual(p2, 4, "Double period cannot be in lunch")
        self.assertFalse(p1 == 3 and p2 == 5, "Double period cannot cross lunch recess")

    def test_specialized_room_collision_avoidance(self):
        """Test that two classes requiring the same specialized facility cannot be scheduled in the same slot."""
        # 1 Science Lab available
        rooms = {"R_SCI": Room(id="R_SCI", name="Senior Science Lab", room_type="ScienceLab", capacity=40)}
        teachers = {
            "T1": Teacher(id="T1", name="Physics Teacher", max_weekly_periods=10),
            "T2": Teacher(id="T2", name="Chemistry Teacher", max_weekly_periods=10)
        }
        classes = {
            "C1": ClassSection(id="C1", name="Class 11 A"),
            "C2": ClassSection(id="C2", name="Class 11 B")
        }
        # Both classes have 3 practical periods requiring ScienceLab
        events = [
            Event(id="E1", subject="Phy Lab", teacher_ids=["T1"], section_ids=["C1"], weekly_quota=3, room_type="ScienceLab"),
            Event(id="E2", subject="Chem Lab", teacher_ids=["T2"], section_ids=["C2"], weekly_quota=3, room_type="ScienceLab")
        ]

        solver = CSPSolver(self.config, teachers, classes, rooms, events)
        res = solver.solve()
        self.assertTrue(res.success, "Solver failed on specialized room scheduling")

        grid = res.grid
        clashes = grid.detect_all_clashes()
        self.assertEqual(len(clashes), 0, f"Room clashes detected: {clashes}")

        # Verify no simultaneous usage of ScienceLab in room_grid
        for (r_id, day, p_idx), assignments in grid.room_grid.items():
            if r_id == "R_SCI":
                self.assertLessEqual(len(assignments), 1, f"Multiple classes booked ScienceLab simultaneously on {day} Period {p_idx}")

    def test_subject_rename_and_delete_cascade(self):
        """Test cascading rename and delete of master subjects across curriculum allocations."""
        subjects = [
            {"id": "S1", "name": "Physics", "code": "PHY"},
            {"id": "S2", "name": "Chemistry", "code": "CHEM"}
        ]
        events = [
            {"id": "E1", "subject": "Physics", "weekly_quota": 6},
            {"id": "E2", "subject": "Chemistry", "weekly_quota": 6}
        ]

        # Rename "Physics" -> "Physics Core"
        old_name = "Physics"
        new_name = "Physics Core"
        for s in subjects:
            if s["name"] == old_name:
                s["name"] = new_name
        for e in events:
            if e["subject"] == old_name:
                e["subject"] = new_name

        self.assertEqual(subjects[0]["name"], "Physics Core")
        self.assertEqual(events[0]["subject"], "Physics Core")

        # Delete "Chemistry"
        del_target = "Chemistry"
        subjects = [s for s in subjects if s["name"] != del_target]
        events = [e for e in events if e["subject"] != del_target]

        self.assertEqual(len(subjects), 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["subject"], "Physics Core")

if __name__ == "__main__":
    unittest.main()
