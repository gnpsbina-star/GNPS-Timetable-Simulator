import unittest
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.generator import TimetableGenerator

class TestClassTeacherPeriod1Rule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.config_path = os.path.join(base_dir, "timetable_config.json")
        with open(cls.config_path, "r", encoding="utf-8") as f:
            cls.raw_config = json.load(f)

    def test_class_teacher_p1_priority(self):
        """Test that Class Teacher lessons are prioritized for Period 1 across sections."""
        from engine.models import SchoolConfig, Teacher, ClassSection, Room, Event
        from engine.csp_solver import CSPSolver

        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        target_class_ids = {"CLASS_3_Rose", "CLASS_3_Marigold", "CLASS_3_Lily", "CLASS_3_Sunflower"}
        classes = {c["id"]: ClassSection(id=c["id"], name=c["name"], wing=c.get("wing", "Primary"), class_teacher=c.get("class_teacher", "")) 
                   for c in data["classes"] if c["id"] in target_class_ids}
        events = [Event(
            id=e["id"], subject=e["subject"], teacher_ids=e.get("teacher_ids", []),
            section_ids=e.get("section_ids", []), weekly_quota=e.get("weekly_quota", 1),
            duration=e.get("duration", 1), room_type=e.get("room_type", "Classroom")
        ) for e in data["events"] if any(s in target_class_ids for s in e.get("section_ids", []))]
        active_t = {t for e in events for t in e.teacher_ids}
        teachers = {t["id"]: Teacher(id=t["id"], name=t["name"], max_weekly_periods=t.get("max_weekly_periods", 34), max_daily_periods=t.get("max_daily_periods", 6)) 
                    for t in data["teachers"] if t["id"] in active_t or t["name"] in active_t}

        cfg_dict = data["config"]
        config = SchoolConfig(
            academic_year=cfg_dict.get("academic_year", "2026-27"),
            title=cfg_dict.get("title", "School Time Table"),
            days=cfg_dict.get("days", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]),
            periods_per_day=cfg_dict.get("periods_per_day", 8),
            period_definitions=cfg_dict.get("period_definitions", []),
            wing_bell_schedules=cfg_dict.get("wing_bell_schedules", {}),
            enforce_class_teacher_p1=True
        )

        solver = CSPSolver(config, teachers, classes, {}, events, max_steps=50000)
        res = solver.solve()
        self.assertTrue(res.success, f"Solver failed: {res.message}")
        grid = res.grid
        self.assertEqual(len(grid.detect_all_clashes()), 0, "Clashes detected")

        # Verify Period 1 placement for Class Teachers
        ct_p1_slots = 0
        max_possible_ct_p1 = 0
        for c_id, c in classes.items():
            ct = c.class_teacher
            # Calculate total periods CT teaches this class
            class_ct_quota = sum(
                e.weekly_quota for e in events 
                if c_id in e.section_ids and any(ct.lower() in t.lower() or t.lower() in ct.lower() for t in e.teacher_ids)
            )
            # A week has 6 days, so at most 6 lessons can be in Period 1 for this section
            max_possible_ct_p1 += min(len(config.days), class_ct_quota)

            for d in config.days:
                a = grid.section_grid.get((c_id, d, 1))
                if a and any(ct.lower() in t.lower() or t.lower() in ct.lower() for t in a.teacher_ids):
                    ct_p1_slots += 1

        print(f"\n[Test CT P1] Placed {ct_p1_slots} of {max_possible_ct_p1} mathematically maximum possible CT lessons into Period 1.")
        # In our 4 sections, Vandna (min(6,5)=5) + Shilpi (min(6,8)=6) + Anubha (min(6,2)=2) + Neha (min(6,6)=6) = 19 max possible.
        self.assertEqual(ct_p1_slots, max_possible_ct_p1, "Every available Period 1 slot eligible for Class Teacher must be occupied by Class Teacher")


    def test_ct_rule_toggle_off(self):
        """Test that turning off enforce_class_teacher_p1 changes the placement distribution."""
        from engine.models import SchoolConfig, Teacher, ClassSection, Room, Event
        from engine.csp_solver import CSPSolver

        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        target_class_ids = {"CLASS_3_Rose", "CLASS_3_Marigold", "CLASS_3_Lily", "CLASS_3_Sunflower"}
        classes = {c["id"]: ClassSection(id=c["id"], name=c["name"], wing=c.get("wing", "Primary"), class_teacher=c.get("class_teacher", "")) 
                   for c in data["classes"] if c["id"] in target_class_ids}
        events = [Event(
            id=e["id"], subject=e["subject"], teacher_ids=e.get("teacher_ids", []),
            section_ids=e.get("section_ids", []), weekly_quota=e.get("weekly_quota", 1),
            duration=e.get("duration", 1), room_type=e.get("room_type", "Classroom")
        ) for e in data["events"] if any(s in target_class_ids for s in e.get("section_ids", []))]
        active_t = {t for e in events for t in e.teacher_ids}
        teachers = {t["id"]: Teacher(id=t["id"], name=t["name"], max_weekly_periods=t.get("max_weekly_periods", 34), max_daily_periods=t.get("max_daily_periods", 6)) 
                    for t in data["teachers"] if t["id"] in active_t or t["name"] in active_t}

        cfg_dict = data["config"]
        config = SchoolConfig(
            academic_year=cfg_dict.get("academic_year", "2026-27"),
            title=cfg_dict.get("title", "School Time Table"),
            days=cfg_dict.get("days", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]),
            periods_per_day=cfg_dict.get("periods_per_day", 8),
            period_definitions=cfg_dict.get("period_definitions", []),
            wing_bell_schedules=cfg_dict.get("wing_bell_schedules", {}),
            enforce_class_teacher_p1=False
        )

        solver = CSPSolver(config, teachers, classes, {}, events, max_steps=50000)
        res = solver.solve()
        self.assertTrue(res.success, f"Solver failed with CT off: {res.message}")
        grid = res.grid
        self.assertEqual(len(grid.detect_all_clashes()), 0)

        # Count CT in P1 when disabled
        ct_p1_slots = 0
        for c_id, c in classes.items():
            ct = c.class_teacher
            for d in config.days:
                a = grid.section_grid.get((c_id, d, 1))
                if a and any(ct.lower() in t.lower() or t.lower() in ct.lower() for t in a.teacher_ids):
                    ct_p1_slots += 1

        print(f"[Test CT P1 Off] CT lessons in Period 1 when rule disabled: {ct_p1_slots} (expected < 19)")
        self.assertLess(ct_p1_slots, 19, "With rule disabled, CT lessons should not all concentrate in Period 1")

if __name__ == "__main__":
    unittest.main()

