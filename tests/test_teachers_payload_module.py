import unittest
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.models import SchoolConfig, Teacher, ClassSection, Room, Event
from engine.precheck import audit_capacity
from engine.csp_solver import CSPSolver

def compute_teacher_load(teacher_name: str, events: list) -> int:
    t_key = teacher_name.lower().strip()
    total = 0
    for ev in events:
        t_ids = ev.teacher_ids if hasattr(ev, 'teacher_ids') else ev.get('teacher_ids', [])
        if any(tid.lower().strip() == t_key for tid in t_ids):
            q = ev.weekly_quota if hasattr(ev, 'weekly_quota') else ev.get('weekly_quota', 0)
            d = ev.duration if hasattr(ev, 'duration') else ev.get('duration', 1)
            total += q * d
    return total

class TestTeachersPayloadModule(unittest.TestCase):
    def setUp(self):
        self.config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "timetable_config.json"
        )
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.raw_data = json.load(f)

    def test_teacher_assigned_load_calculation(self):
        """Pillar 5: Verify precise assigned workload calculation across single and double periods."""
        events = [
            Event(id="EV_1", subject="Math", teacher_ids=["T_ALPHA"], section_ids=["C1"], weekly_quota=6, duration=1),
            Event(id="EV_2", subject="Math", teacher_ids=["T_ALPHA"], section_ids=["C2"], weekly_quota=6, duration=1),
            Event(id="EV_3", subject="Lab", teacher_ids=["T_ALPHA"], section_ids=["C1"], weekly_quota=2, duration=2), # 4 periods
        ]
        total_load = compute_teacher_load("T_ALPHA", events)
        self.assertEqual(total_load, 16) # 6 + 6 + 4

    def test_teacher_utilization_and_status_categories(self):
        """Pillar 5: Verify color-coded fatigue thresholds and status categorization."""
        def get_status(load: int, max_cap: int) -> str:
            if load > max_cap: return "OVERLOADED"
            pct = (load / max_cap) * 100 if max_cap > 0 else 0
            free_slots = max_cap - load
            if pct >= 70 and pct <= 95: return "OPTIMAL"
            if pct > 95: return "HIGH"
            if free_slots >= 8: return "FREE"
            return "NORMAL"

        max_cap = 34
        # Optimal (70% - 95%): e.g. 28 periods (82.4%)
        self.assertEqual(get_status(28, max_cap), "OPTIMAL")

        # High (> 95%): e.g. 33 periods (97.1%)
        self.assertEqual(get_status(33, max_cap), "HIGH")

        # Overloaded (> 100%): e.g. 36 periods (105.9%)
        self.assertEqual(get_status(36, max_cap), "OVERLOADED")

        # Free Capacity (>= 8 free slots, load < 70%): e.g. 18 periods (16 free slots)
        self.assertEqual(get_status(18, max_cap), "FREE")

    def test_teacher_payload_stepper_boundaries(self):
        """Pillar 5: Verify weekly payload cap stepper logic and boundaries (1 <= cap <= 48)."""
        t = Teacher(id="T_BETA", name="Beta Teacher", max_weekly_periods=34, max_daily_periods=6)

        def step_cap(teacher: Teacher, delta: int) -> int:
            new_cap = max(1, min(48, teacher.max_weekly_periods + delta))
            teacher.max_weekly_periods = new_cap
            return teacher.max_weekly_periods

        self.assertEqual(step_cap(t, 2), 36)
        self.assertEqual(step_cap(t, -6), 30)

        # Clamping lower bound
        step_cap(t, -100)
        self.assertEqual(t.max_weekly_periods, 1)

        # Clamping upper bound
        step_cap(t, 100)
        self.assertEqual(t.max_weekly_periods, 48)

    def test_specialist_bottleneck_detection_in_audit(self):
        """Pillar 5: Verify pre-check audit catches overloaded teachers and flags fatigue bottlenecks."""
        config = SchoolConfig(
            academic_year="2026-27",
            days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
            periods_per_day=8,
            period_definitions=[
                {"period_index": p, "name": f"P{p}", "is_lunch": (p == 4), "is_assembly": (p == 0)}
                for p in range(9)
            ]
        )
        t_over = Teacher(id="T_OVER", name="Overloaded Teacher", max_weekly_periods=20, max_daily_periods=6)
        c1 = ClassSection(id="C1", name="Class 1", wing="Primary")
        ev = Event(id="EV_OVER", subject="Math", teacher_ids=["T_OVER"], section_ids=["C1"], weekly_quota=25, duration=1)

        report = audit_capacity(
            config,
            teachers={"T_OVER": t_over},
            classes={"C1": c1},
            rooms={},
            events=[ev]
        )
        self.assertFalse(report.is_feasible)
        self.assertTrue(any("exceeding their maximum cap" in err for err in report.errors))

    def test_daily_fatigue_cap_respected_by_solver(self):
        """Pillar 5: Verify that CSP solver strictly enforces max_daily_periods to prevent faculty burn-out."""
        config = SchoolConfig(
            academic_year="2026-27",
            days=["Monday", "Tuesday", "Wednesday"],
            periods_per_day=4,
            period_definitions=[
                {"period_index": 1, "name": "P1", "is_lunch": False, "is_assembly": False},
                {"period_index": 2, "name": "P2", "is_lunch": False, "is_assembly": False},
                {"period_index": 3, "name": "P3", "is_lunch": False, "is_assembly": False},
            ],
            enforce_class_teacher_p1=False
        )
        # Teacher capped at max 2 periods per day
        t1 = Teacher(id="T1", name="Capped Teacher", max_weekly_periods=6, max_daily_periods=2)
        c1 = ClassSection(id="C1", name="Class 1", wing="Primary")
        events = [
            Event(id="EV_1", subject="Math", teacher_ids=["T1"], section_ids=["C1"], weekly_quota=6, duration=1)
        ]

        solver = CSPSolver(config, {"T1": t1}, {"C1": c1}, {}, events)
        result = solver.solve()

        self.assertTrue(result.success)
        # Check daily load across all 3 days
        for day in config.days:
            daily_lessons = [
                assignments for (tid, d, p), assignments in result.grid.teacher_grid.items()
                if d == day and tid == "T1"
            ]
            self.assertLessEqual(
                len(daily_lessons), 2,
                f"Teacher exceeded max_daily_periods (2) on {day}: {len(daily_lessons)} lessons"
            )

    def test_master_config_faculty_kpis_and_zero_overloads(self):
        """Pillar 5: Master Faculty Workload Audit — verify all 50 teachers have valid workloads."""
        teachers = self.raw_data.get("teachers", [])
        events = self.raw_data.get("events", [])

        self.assertGreaterEqual(len(teachers), 49, "Master config must have at least 49 faculty members")

        total_load = 0
        overloaded_teachers = []
        free_reserve = 0

        for t in teachers:
            t_name = t.get("name", "")
            assigned = compute_teacher_load(t_name, events)
            max_cap = t.get("max_weekly_periods", 34)
            total_load += assigned
            free_slots = max(0, max_cap - assigned)
            free_reserve += free_slots

            if assigned > max_cap:
                overloaded_teachers.append({
                    "teacher": t_name,
                    "assigned": assigned,
                    "max_cap": max_cap,
                    "excess": assigned - max_cap
                })

        # Ensure no teacher is overloaded beyond their contractual weekly cap
        self.assertEqual(
            len(overloaded_teachers), 0,
            f"Expected 0 overloaded teachers, but found: {overloaded_teachers}"
        )

        avg_load = total_load / len(teachers)
        self.assertGreater(avg_load, 15.0, "Average faculty load should reflect realistic curriculum demand")
        self.assertGreater(free_reserve, 100, "Capacity reserve must be available for substitutions and cover")

if __name__ == "__main__":
    unittest.main()
