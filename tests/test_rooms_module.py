import unittest
import os
import sys
import json
import copy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.models import SchoolConfig, Teacher, ClassSection, Room, Event, SlotAssignment, TimetableGrid
from engine.precheck import audit_capacity
from engine.csp_solver import CSPSolver

class TestRoomsModule(unittest.TestCase):
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
            enforce_class_teacher_p1=False
        )

    def test_room_model_properties_and_serialization(self):
        """Module 3: Verify Room dataclass properties, defaults, and JSON serialization."""
        r_lab = Room(id="R_CHEM", name="Chemistry Lab", room_type="ScienceLab", capacity=35, max_concurrent_classes=1, building="Science Block")
        self.assertEqual(r_lab.room_type, "ScienceLab")
        self.assertEqual(r_lab.max_concurrent_classes, 1)
        self.assertEqual(r_lab.building, "Science Block")

        d = r_lab.to_dict()
        self.assertEqual(d["id"], "R_CHEM")
        self.assertEqual(d["max_concurrent_classes"], 1)

        r_reloaded = Room.from_dict(d)
        self.assertEqual(r_reloaded.id, "R_CHEM")
        self.assertEqual(r_reloaded.max_concurrent_classes, 1)

        # Ground default multi-class sharing allowance
        r_ground = Room.from_dict({"id": "R_FIELD", "name": "Sports Ground", "room_type": "Ground", "capacity": 100})
        self.assertEqual(r_ground.max_concurrent_classes, 2, "Ground should default to 2 concurrent classes")

    def test_room_collision_shield_single_class_lab(self):
        """Module 3: Verify that single-class labs strictly forbid simultaneous booking by multiple classes."""
        grid = TimetableGrid(self.config)
        room_sci = Room(id="R_SCI", name="Science Lab", room_type="ScienceLab", capacity=40, max_concurrent_classes=1)
        rooms_by_type = {"ScienceLab": [room_sci]}

        ev1 = Event(id="EV_PHYS_9", subject="Physics", teacher_ids=["T_ANUJ"], section_ids=["C_9_ROSE"], weekly_quota=1, room_type="ScienceLab")
        ev2 = Event(id="EV_CHEM_10", subject="Chemistry", teacher_ids=["T_RAKESH"], section_ids=["C_10_ROSE"], weekly_quota=1, room_type="ScienceLab")

        # 1. Assign ev1 to Monday Period 2 in ScienceLab
        assign1 = SlotAssignment(
            event_id=ev1.id, day="Monday", period_index=2, subject=ev1.subject,
            teacher_ids=ev1.teacher_ids, section_ids=ev1.section_ids, room_type="ScienceLab"
        )
        grid.assign(assign1)

        # 2. Candidate check for ev2 in the exact same slot -> MUST CLASH
        clashes_same_slot = grid.check_clash(ev2, "Monday", 2, rooms_by_type)
        self.assertTrue(len(clashes_same_slot) > 0)
        self.assertTrue(any("maximum concurrent capacity" in c for c in clashes_same_slot))

        # 3. Candidate check for ev2 in another slot (Monday Period 3) -> MUST BE CLEAR
        clashes_other_slot = grid.check_clash(ev2, "Monday", 3, rooms_by_type)
        self.assertEqual(len(clashes_other_slot), 0)

    def test_multi_class_ground_sharing(self):
        """Module 3: Verify sports field allows up to max_concurrent_classes (2), blocking a 3rd class."""
        grid = TimetableGrid(self.config)
        room_ground = Room(id="R_GROUND", name="Playground", room_type="Ground", capacity=100, max_concurrent_classes=2)
        rooms_by_type = {"Ground": [room_ground]}

        ev1 = Event(id="EV_GAMES_1", subject="PE", teacher_ids=["T_GEETESH"], section_ids=["C_6_ROSE"], weekly_quota=1, room_type="Ground")
        ev2 = Event(id="EV_GAMES_2", subject="PE", teacher_ids=["T_KAPIL"], section_ids=["C_7_ROSE"], weekly_quota=1, room_type="Ground")
        ev3 = Event(id="EV_GAMES_3", subject="PE", teacher_ids=["T_SPORTS3"], section_ids=["C_8_ROSE"], weekly_quota=1, room_type="Ground")

        # Slot 1: Class 1 books ground
        grid.assign(SlotAssignment(event_id=ev1.id, day="Tuesday", period_index=5, subject="PE", teacher_ids=ev1.teacher_ids, section_ids=ev1.section_ids, room_type="Ground"))

        # Slot 2: Class 2 checks ground in same slot -> ALLOWED (1 < 2)
        clashes_2nd = grid.check_clash(ev2, "Tuesday", 5, rooms_by_type)
        self.assertEqual(len(clashes_2nd), 0, "Second concurrent class on Ground should be permitted")
        grid.assign(SlotAssignment(event_id=ev2.id, day="Tuesday", period_index=5, subject="PE", teacher_ids=ev2.teacher_ids, section_ids=ev2.section_ids, room_type="Ground"))

        # Slot 3: Class 3 checks ground in same slot -> BLOCKED (2 >= 2)
        clashes_3rd = grid.check_clash(ev3, "Tuesday", 5, rooms_by_type)
        self.assertTrue(len(clashes_3rd) > 0)
        self.assertTrue(any("maximum concurrent capacity" in c for c in clashes_3rd))

    def test_double_period_lab_room_integrity(self):
        """Module 3: Verify double-period practical lab booking protects both consecutive slots."""
        grid = TimetableGrid(self.config)
        room_comp = Room(id="R_COMP", name="Computer Lab", room_type="ComputerLab", capacity=40, max_concurrent_classes=1)
        rooms_by_type = {"ComputerLab": [room_comp]}

        ev_double = Event(id="EV_CS_DOUBLE", subject="CS Practical", teacher_ids=["T_CS"], section_ids=["C_11_SCI"], weekly_quota=1, duration=2, room_type="ComputerLab")
        ev_single = Event(id="EV_CS_SINGLE", subject="IT", teacher_ids=["T_IT"], section_ids=["C_8_ROSE"], weekly_quota=1, duration=1, room_type="ComputerLab")

        # Assign double period at periods 2 & 3
        grid.assign(SlotAssignment(event_id=ev_double.id, day="Wednesday", period_index=2, subject="CS Practical", teacher_ids=ev_double.teacher_ids, section_ids=ev_double.section_ids, room_type="ComputerLab"))
        grid.assign(SlotAssignment(event_id=ev_double.id, day="Wednesday", period_index=3, subject="CS Practical", teacher_ids=ev_double.teacher_ids, section_ids=ev_double.section_ids, room_type="ComputerLab"))

        # ev_single tries Period 2 -> CLASH
        self.assertTrue(len(grid.check_clash(ev_single, "Wednesday", 2, rooms_by_type)) > 0)
        # ev_single tries Period 3 -> CLASH
        self.assertTrue(len(grid.check_clash(ev_single, "Wednesday", 3, rooms_by_type)) > 0)
        # ev_single tries Period 5 -> CLEAR
        self.assertEqual(len(grid.check_clash(ev_single, "Wednesday", 5, rooms_by_type)), 0)

    def test_precheck_facility_utilization_and_status(self):
        """Module 3: Verify capacity audit calculates facility utilization and flags bottleneck statuses."""
        rooms = {
            "R_SCI": Room(id="R_SCI", name="Science Lab", room_type="ScienceLab", capacity=40, max_concurrent_classes=1),
            "R_COMP": Room(id="R_COMP", name="Computer Lab", room_type="ComputerLab", capacity=40, max_concurrent_classes=1),
        }
        # 54 total slots per week (6 days * 9 period definitions)
        events = [
            Event(id="EV_1", subject="Physics Lab", teacher_ids=["T1"], section_ids=["C1"], weekly_quota=12, duration=2, room_type="ScienceLab"), # 24 slots (44.4% - Optimal)
            Event(id="EV_2", subject="CS Lab", teacher_ids=["T2"], section_ids=["C2"], weekly_quota=25, duration=2, room_type="ComputerLab"), # 50 slots (92.6% - Bottleneck)
        ]

        report = audit_capacity(
            self.config,
            teachers={"T1": Teacher(id="T1", name="Teacher 1"), "T2": Teacher(id="T2", name="Teacher 2")},
            classes={"C1": ClassSection(id="C1", name="C1"), "C2": ClassSection(id="C2", name="C2")},
            rooms=rooms,
            events=events
        )

        fac_util = report.stats.get("facility_utilization", {})
        self.assertIn("ScienceLab", fac_util)
        self.assertIn("ComputerLab", fac_util)

        self.assertEqual(fac_util["ScienceLab"]["status"], "Optimal")
        self.assertEqual(fac_util["ScienceLab"]["demanded_periods"], 24)

        self.assertEqual(fac_util["ComputerLab"]["status"], "Bottleneck")
        self.assertEqual(fac_util["ComputerLab"]["demanded_periods"], 50)
        self.assertTrue(any("Facility Bottleneck: 'ComputerLab'" in w for w in report.warnings))

    def test_room_deficit_detection_in_precheck(self):
        """Module 3: Verify precheck blocks solver feasibility if room demand exceeds physical capacity."""
        rooms = {
            "R_SCI": Room(id="R_SCI", name="Science Lab", room_type="ScienceLab", capacity=40, max_concurrent_classes=1)
        }
        # Demand 60 periods when total slots is 54 -> DEFICIT (+6)
        events = [
            Event(id="EV_EXCESS", subject="Science Lab", teacher_ids=["T1"], section_ids=["C1"], weekly_quota=30, duration=2, room_type="ScienceLab")
        ]

        report = audit_capacity(
            self.config,
            teachers={"T1": Teacher(id="T1", name="Teacher 1")},
            classes={"C1": ClassSection(id="C1", name="C1")},
            rooms=rooms,
            events=events
        )
        self.assertFalse(report.is_feasible)
        self.assertTrue(any("requires 60 periods/week, but maximum physical capacity is only 54" in e for e in report.errors))

    def test_master_config_room_audit(self):
        """Module 3: Master configuration audit — verify all rooms defined in timetable_config.json have valid specs."""
        rooms = self.raw_data.get("rooms", [])
        self.assertGreaterEqual(len(rooms), 3)

        room_ids = {r["id"] for r in rooms}
        self.assertIn("R_COMP", room_ids)
        self.assertIn("R_SCI", room_ids)
        self.assertIn("R_GROUND", room_ids)

        for r in rooms:
            self.assertTrue(len(r.get("name", "")) > 0)
            self.assertGreater(r.get("capacity", 0), 0)

    def test_timetable_rooms_json_export_integrity(self):
        """Module 3: Verify exported timetable_rooms.json file structure, schema, and capacity adherence."""
        rooms_json_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "timetable_rooms.json"
        )
        self.assertTrue(os.path.exists(rooms_json_path), "timetable_rooms.json must exist")
        with open(rooms_json_path, "r", encoding="utf-8") as f:
            rooms_data = json.load(f)

        required_rooms = ["Computer Lab", "Science Lab", "Playground", "Activity Hall"]
        for r_name in required_rooms:
            self.assertIn(r_name, rooms_data, f"{r_name} must be in timetable_rooms.json")
            r_info = rooms_data[r_name]
            self.assertIn("id", r_info)
            self.assertIn("building", r_info)
            self.assertIn("capacity", r_info)
            self.assertIn("max_concurrent_classes", r_info)
            self.assertIn("schedule", r_info)

            max_allowed = r_info["max_concurrent_classes"]
            for day, period_list in r_info["schedule"].items():
                for p in period_list:
                    occ = len(p.get("bookings", []))
                    self.assertLessEqual(
                        occ, max_allowed,
                        f"Occupancy in {r_name} on {day} period {p.get('period_index')} exceeds max cap: {occ} > {max_allowed}"
                    )

        # Confirm Ground multi-class sharing occurred safely
        playground = rooms_data["Playground"]
        self.assertGreater(playground["total_bookings_per_week"], 0)
        self.assertEqual(playground["max_concurrent_classes"], 3)

if __name__ == "__main__":
    unittest.main()
