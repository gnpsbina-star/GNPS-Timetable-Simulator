import unittest
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.models import SchoolConfig, Teacher, ClassSection, Room, Event, Subject
from engine.precheck import audit_capacity

def normalize_wing(w: str) -> str:
    w = (w or '').lower().replace(' ', '').replace('-', '')
    if 'play' in w: return 'playgroup'
    if 'pre' in w or 'nur' in w or 'lkg' in w or 'ukg' in w: return 'pre_primary'
    if 'prim' in w or any(str(i) in w for i in range(1, 6)): return 'primary'
    if 'mid' in w or any(str(i) in w for i in range(6, 9)): return 'middle'
    if 'sen' in w or any(str(i) in w for i in [9, 10, 11, 12]): return 'senior'
    return 'middle'

def calculate_wing_active_slots(config: SchoolConfig, wing_name: str) -> int:
    w_key = normalize_wing(wing_name)
    cnt = 0
    for d in config.days:
        day_key = 'saturday' if d.lower() == 'saturday' else 'weekday'
        for p in (config.period_definitions or []):
            if p.get('is_lunch') or p.get('is_assembly'):
                continue
            sch = p.get('wing_schedule', {}).get(day_key, {}).get(w_key, 'study')
            if sch == 'study':
                cnt += 1
    return cnt

def calculate_class_payload(c_id: str, events: list) -> int:
    total = 0
    for ev in events:
        sec_ids = ev.section_ids if hasattr(ev, 'section_ids') else ev.get('section_ids', [])
        if c_id in sec_ids:
            q = ev.weekly_quota if hasattr(ev, 'weekly_quota') else ev.get('weekly_quota', 0)
            d = ev.duration if hasattr(ev, 'duration') else ev.get('duration', 1)
            total += q * d
    return total

class TestClassPayloadModule(unittest.TestCase):
    def setUp(self):
        self.config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "timetable_config.json"
        )
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.raw_data = json.load(f)

        cfg_data = self.raw_data.get("config", {})
        self.config = SchoolConfig(
            academic_year=cfg_data.get("academic_year", "2026-27"),
            title=cfg_data.get("title", "School Time Table"),
            days=cfg_data.get("days", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]),
            periods_per_day=cfg_data.get("periods_per_day", 8),
            period_definitions=cfg_data.get("period_definitions", []),
            enforce_class_teacher_p1=True
        )

    def test_wing_active_slots_calculation(self):
        """Pillar 4: Verify wing active teaching periods calculation across all 5 school wings."""
        slots_primary = calculate_wing_active_slots(self.config, "Primary")
        slots_middle = calculate_wing_active_slots(self.config, "Middle")
        slots_senior = calculate_wing_active_slots(self.config, "Senior")
        slots_pre_primary = calculate_wing_active_slots(self.config, "Pre-Primary")
        slots_playgroup = calculate_wing_active_slots(self.config, "Playgroup")

        self.assertEqual(slots_primary, 34, "Primary wing must have 34 active teaching periods (5x6 + 4)")
        self.assertEqual(slots_middle, 39, "Middle wing must have 39 active teaching periods (5x7 + 4)")
        self.assertEqual(slots_senior, 36, "Senior wing must have 36 active teaching periods (6x6)")
        self.assertEqual(slots_pre_primary, 34, "Pre-Primary wing must have 34 active teaching periods")
        self.assertEqual(slots_playgroup, 23, "Playgroup wing must have 23 active teaching periods")

    def test_class_payload_balance_meter_states(self):
        """Pillar 4: Verify live 100% balance meter states: Balanced, Under-allocated, and Over-allocated."""
        target_slots = 34
        mock_events = [
            Event(id="EV_1", subject="Math", teacher_ids=["T_MATH"], section_ids=["C_TEST"], weekly_quota=6, duration=1),
            Event(id="EV_2", subject="English", teacher_ids=["T_ENG"], section_ids=["C_TEST"], weekly_quota=6, duration=1),
            Event(id="EV_3", subject="Science", teacher_ids=["T_SCI"], section_ids=["C_TEST"], weekly_quota=6, duration=1),
            Event(id="EV_4", subject="Social Studies", teacher_ids=["T_SST"], section_ids=["C_TEST"], weekly_quota=6, duration=1),
            Event(id="EV_5", subject="Hindi", teacher_ids=["T_HIN"], section_ids=["C_TEST"], weekly_quota=6, duration=1),
            Event(id="EV_6", subject="Art", teacher_ids=["T_ART"], section_ids=["C_TEST"], weekly_quota=4, duration=1),
        ]

        # 1. State 1: Balanced (34 / 34 = 100%)
        total_p = calculate_class_payload("C_TEST", mock_events)
        self.assertEqual(total_p, 34)
        pct = (total_p / target_slots) * 100
        self.assertEqual(pct, 100.0)

        # 2. State 2: Under-allocated (28 / 34 = 82.35%, 6 free slots)
        under_events = [
            Event(id="EV_1", subject="Math", teacher_ids=["T_MATH"], section_ids=["C_TEST"], weekly_quota=6, duration=1),
            Event(id="EV_2", subject="English", teacher_ids=["T_ENG"], section_ids=["C_TEST"], weekly_quota=6, duration=1),
            Event(id="EV_3", subject="Science", teacher_ids=["T_SCI"], section_ids=["C_TEST"], weekly_quota=6, duration=1),
            Event(id="EV_4", subject="Social Studies", teacher_ids=["T_SST"], section_ids=["C_TEST"], weekly_quota=6, duration=1),
            Event(id="EV_5", subject="Hindi", teacher_ids=["T_HIN"], section_ids=["C_TEST"], weekly_quota=4, duration=1),
        ]
        under_p = calculate_class_payload("C_TEST", under_events)
        self.assertEqual(under_p, 28)
        self.assertLess(under_p, target_slots)
        free_slots = target_slots - under_p
        self.assertEqual(free_slots, 6)

        # 3. State 3: Over-allocated (37 / 34 = 108.82%, 3 surplus slots)
        over_events = [
            Event(id="EV_1", subject="Math", teacher_ids=["T_MATH"], section_ids=["C_TEST"], weekly_quota=6, duration=1),
            Event(id="EV_2", subject="English", teacher_ids=["T_ENG"], section_ids=["C_TEST"], weekly_quota=6, duration=1),
            Event(id="EV_3", subject="Science", teacher_ids=["T_SCI"], section_ids=["C_TEST"], weekly_quota=6, duration=1),
            Event(id="EV_4", subject="Social Studies", teacher_ids=["T_SST"], section_ids=["C_TEST"], weekly_quota=6, duration=1),
            Event(id="EV_5", subject="Hindi", teacher_ids=["T_HIN"], section_ids=["C_TEST"], weekly_quota=6, duration=1),
            Event(id="EV_6", subject="Art", teacher_ids=["T_ART"], section_ids=["C_TEST"], weekly_quota=4, duration=1),
            Event(id="EV_EXTRA", subject="Dance", teacher_ids=["T_DANCE"], section_ids=["C_TEST"], weekly_quota=3, duration=1),
        ]
        over_p = calculate_class_payload("C_TEST", over_events)
        self.assertEqual(over_p, 37)
        self.assertGreater(over_p, target_slots)
        excess = over_p - target_slots
        self.assertEqual(excess, 3)

    def test_quota_stepper_and_boundary_checks(self):
        """Pillar 4: Verify weekly quota stepper operations with clamping boundaries (1 <= quota <= 15)."""
        ev = Event(id="EV_TEST", subject="Math", teacher_ids=["T1"], section_ids=["C1"], weekly_quota=5, duration=1)

        def step_quota(event: Event, delta: int) -> int:
            new_q = max(1, min(15, event.weekly_quota + delta))
            event.weekly_quota = new_q
            return event.weekly_quota

        # Normal increment
        self.assertEqual(step_quota(ev, 1), 6)
        # Normal decrement
        self.assertEqual(step_quota(ev, -2), 4)

        # Lower boundary clamping (cannot drop below 1 period/week)
        step_quota(ev, -10)
        self.assertEqual(ev.weekly_quota, 1)

        # Upper boundary clamping (cannot exceed 15 periods/week)
        step_quota(ev, 20)
        self.assertEqual(ev.weekly_quota, 15)

    def test_practical_lab_double_period_payload(self):
        """Pillar 4: Verify that practical lab double-periods count as 2 contact periods per quota."""
        ev_theory = Event(id="EV_TH", subject="Physics", teacher_ids=["T_PHY"], section_ids=["C_SENIOR"], weekly_quota=4, duration=1)
        ev_lab = Event(id="EV_LAB", subject="Physics Lab", teacher_ids=["T_PHY"], section_ids=["C_SENIOR"], weekly_quota=2, duration=2)

        p_theory = ev_theory.weekly_quota * ev_theory.duration
        p_lab = ev_lab.weekly_quota * ev_lab.duration

        self.assertEqual(p_theory, 4)
        self.assertEqual(p_lab, 4) # 2 blocks * 2 periods = 4 contact periods
        self.assertEqual(p_theory + p_lab, 8)

    def test_add_and_delete_class_events(self):
        """Pillar 4: Verify dynamic addition and deletion of subject allocations in a class section."""
        events = [
            Event(id="EV_1", subject="Math", teacher_ids=["T1"], section_ids=["C1"], weekly_quota=6, duration=1),
            Event(id="EV_2", subject="Science", teacher_ids=["T2"], section_ids=["C1"], weekly_quota=6, duration=1)
        ]
        self.assertEqual(calculate_class_payload("C1", events), 12)

        # Add event
        new_ev = Event(id="EV_3", subject="Robotics", teacher_ids=["T3"], section_ids=["C1"], weekly_quota=4, duration=1)
        events.append(new_ev)
        self.assertEqual(calculate_class_payload("C1", events), 16)

        # Delete event
        events = [e for e in events if e.id != "EV_1"]
        self.assertEqual(calculate_class_payload("C1", events), 10)
        self.assertEqual(len(events), 2)

    def test_faculty_reassignment_preserves_class_payload(self):
        """Pillar 4: Verify reassigning faculty does not disrupt class payload balance."""
        ev = Event(id="EV_SST", subject="Social Studies", teacher_ids=["Old_Teacher"], section_ids=["C1"], weekly_quota=6, duration=1)
        events = [ev]
        initial_payload = calculate_class_payload("C1", events)

        # Reassign to new teacher
        ev.teacher_ids = ["New_Teacher"]
        updated_payload = calculate_class_payload("C1", events)

        self.assertEqual(initial_payload, updated_payload)
        self.assertEqual(ev.teacher_ids, ["New_Teacher"])

    def test_all_40_classes_100_percent_balanced_in_master_config(self):
        """Pillar 4: Master Audit — verify all 40 classes in timetable_config.json are 100% balanced."""
        classes = {c["id"]: c for c in self.raw_data.get("classes", [])}
        events = self.raw_data.get("events", [])

        self.assertEqual(len(classes), 40, "Must have exactly 40 active classes")

        class_event_map = {}
        for ev in events:
            for s_id in ev.get("section_ids", []):
                class_event_map.setdefault(s_id, []).append(ev)

        unbalanced_classes = []
        for c_id, c_data in classes.items():
            wing = c_data.get("wing", "Middle")
            target_capacity = calculate_wing_active_slots(self.config, wing)
            c_events = class_event_map.get(c_id, [])
            total_allocated = sum(e.get("weekly_quota", 0) * e.get("duration", 1) for e in c_events)

            if total_allocated != target_capacity:
                unbalanced_classes.append({
                    "class": c_data.get("name"),
                    "wing": wing,
                    "target": target_capacity,
                    "allocated": total_allocated,
                    "delta": total_allocated - target_capacity
                })

        self.assertEqual(
            len(unbalanced_classes), 0,
            f"All classes must be 100% balanced, but found mismatches: {unbalanced_classes}"
        )

if __name__ == "__main__":
    unittest.main()
