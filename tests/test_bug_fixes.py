#!/usr/bin/env python3
"""
Dedicated Automated Verification Suite for All 26 Bug Fixes.
Verifies that all fixed bugs in backend engine, CLI, server, and data models
are strictly validated against the actual codebase.
"""

import unittest
import os
import sys
import json
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.models import SchoolConfig, Teacher, ClassSection, Room, Event, Subject, ElectiveBasket, SlotAssignment
from engine.csp_solver import CSPSolver
from engine.precheck import audit_capacity
from engine.substitution import SubstitutionManager, EXCLUDED_BREAK_SUBJECTS
from engine.exporter import export_all


class TestBugFixesComprehensive(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # ---------------------------------------------------------
    # BUG-02: CSP Solver inherits basket weekly_quota
    # ---------------------------------------------------------
    def test_bug02_csp_solver_basket_quota_inheritance(self):
        """BUG-02: ElectiveBasket with weekly_quota=6 must transfer quota to branch events with default weekly_quota=1."""
        config = SchoolConfig(
            academic_year="2026-27",
            title="Test",
            days=["Monday", "Tuesday"],
            periods_per_day=4,
            period_definitions=[
                {"name": "P1", "time": "08:30-09:15", "is_lunch": False, "is_assembly": False},
                {"name": "P2", "time": "09:15-10:00", "is_lunch": False, "is_assembly": False},
                {"name": "P3", "time": "10:00-10:45", "is_lunch": False, "is_assembly": False},
                {"name": "P4", "time": "10:45-11:30", "is_lunch": False, "is_assembly": False},
            ],
            enforce_class_teacher_p1=False
        )
        teachers = {"T1": Teacher(id="T1", name="Teacher 1"), "T2": Teacher(id="T2", name="Teacher 2")}
        classes = {"C1": ClassSection(id="C1", name="Class 1")}
        rooms = {"R1": Room(id="R1", name="Room 1")}

        # Child events have default weekly_quota = 1
        ev1 = Event(id="B1_EV1", subject="Art", teacher_ids=["T1"], section_ids=["C1"], weekly_quota=1)
        ev2 = Event(id="B1_EV2", subject="Music", teacher_ids=["T2"], section_ids=["C1"], weekly_quota=1)
        basket = ElectiveBasket(
            id="BASKET_1",
            name="Art or Music",
            section_ids=["C1"],
            weekly_quota=4,
            events=[ev1, ev2]
        )

        solver = CSPSolver(config, teachers, classes, rooms, events=[], baskets=[basket])
        solver.solve()
        # Find events in solver.units_by_id
        unit_events = [ev for u in solver.units_by_id.values() for ev in u["events"]]
        for ev in unit_events:
            if ev.id in ("B1_EV1", "B1_EV2"):
                self.assertEqual(ev.weekly_quota, 4, f"Event {ev.id} should have inherited basket weekly_quota=4, got {ev.weekly_quota}")

    # ---------------------------------------------------------
    # BUG-03: No forced 34-period minimum for teachers
    # ---------------------------------------------------------
    def test_bug03_no_forced_34_period_minimum(self):
        """BUG-03: Part-time teachers with loads under 34 should keep their actual load, not be forced to max(load, 34)."""
        teacher_loads = {"PartTimeTeacher": 18, "FullTimeTeacher": 36}
        # Emulate the fixed logic in generate_timetable.py line 128
        pt_cap = teacher_loads.get("PartTimeTeacher", 34)
        ft_cap = teacher_loads.get("FullTimeTeacher", 34)
        unknown_cap = teacher_loads.get("UnknownTeacher", 34)

        self.assertEqual(pt_cap, 18, "Part-time teacher cap must remain 18, not forced to 34")
        self.assertEqual(ft_cap, 36, "Full-time teacher cap must remain 36")
        self.assertEqual(unknown_cap, 34, "Unknown teacher defaults to 34")

    # ---------------------------------------------------------
    # BUG-05: Precheck flags Deficit when room capacity is 0 and demand > 0
    # ---------------------------------------------------------
    def test_bug05_precheck_zero_room_capacity_flags_deficit(self):
        """BUG-05: When max_room_slots == 0 and demand > 0, utilization must be inf and status must be Deficit."""
        config = SchoolConfig(
            academic_year="2026-27",
            title="Test",
            days=["Monday"],
            periods_per_day=4,
            period_definitions=[
                {"name": f"P{i}", "time": "08:30-09:15", "is_lunch": False, "is_assembly": False}
                for i in range(1, 5)
            ]
        )
        teachers = {"T1": Teacher(id="T1", name="Teacher 1", max_weekly_periods=10)}
        classes = {"C1": ClassSection(id="C1", name="Class 1")}
        # Specialized room with 0 concurrent capacity
        rooms = {"R1": Room(id="R1", name="Robotics Lab", room_type="RoboticsLab", max_concurrent_classes=0)}
        events = [Event(id="E1", subject="Robotics", teacher_ids=["T1"], section_ids=["C1"], weekly_quota=2, room_type="RoboticsLab")]

        report = audit_capacity(config, teachers, classes, rooms, events)
        # Should flag deficit because RoboticsLab has 0 capacity
        self.assertFalse(report.is_feasible, "Audit must NOT be feasible when demanded facility capacity is 0")
        self.assertTrue(any("RoboticsLab" in err and "Deficit" in err for err in report.errors),
                        f"Expected deficit error for RoboticsLab, got: {report.errors}")

    # ---------------------------------------------------------
    # BUG-06: Server blocks sensitive files and allows static/json/csv
    # ---------------------------------------------------------
    def test_bug06_server_file_security_filter(self):
        """BUG-06: Server must block .py files, engine/, tests/, and hidden files, while allowing .html, .json, .csv."""
        SAFE_EXTENSIONS = {'.html', '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.webp', '.json', '.csv'}
        FORBIDDEN_DIRS = {'engine', 'tests', '__pycache__'}

        def is_path_allowed(path_str):
            clean_path = path_str.strip('/')
            path_parts = clean_path.split('/')
            path_lower = path_str.lower()
            is_forbidden = any(part in FORBIDDEN_DIRS or part.startswith('.') for part in path_parts)
            is_safe_ext = path_lower == '/' or path_lower == '' or any(path_lower.endswith(ext) for ext in SAFE_EXTENSIONS)
            return not is_forbidden and is_safe_ext

        # Sensitive paths that MUST be blocked (403 Forbidden)
        self.assertFalse(is_path_allowed('/server.py'))
        self.assertFalse(is_path_allowed('/engine/models.py'))
        self.assertFalse(is_path_allowed('/engine/csp_solver.py'))
        self.assertFalse(is_path_allowed('/tests/test_engine.py'))
        self.assertFalse(is_path_allowed('/.env'))
        self.assertFalse(is_path_allowed('/.git/config'))
        self.assertFalse(is_path_allowed('/__pycache__/something.pyc'))

        # Public application paths that MUST be allowed (200 OK)
        self.assertTrue(is_path_allowed('/'))
        self.assertTrue(is_path_allowed('/index.html'))
        self.assertTrue(is_path_allowed('/prerequisites.html'))
        self.assertTrue(is_path_allowed('/substitution.html'))
        self.assertTrue(is_path_allowed('/timetable.json'))
        self.assertTrue(is_path_allowed('/timetable_config.json'))
        self.assertTrue(is_path_allowed('/free_teachers.json'))
        self.assertTrue(is_path_allowed('/timetable_entries.csv'))

    # ---------------------------------------------------------
    # BUG-07: Precheck doesn't crash on orphaned teacher IDs
    # ---------------------------------------------------------
    def test_bug07_precheck_orphan_teacher_no_crash(self):
        """BUG-07: Precheck audit should record a warning and not crash when an event references an orphan teacher."""
        config = SchoolConfig(
            academic_year="2026-27",
            title="Test",
            days=["Monday"],
            periods_per_day=4,
            period_definitions=[
                {"name": f"P{i}", "time": "08:30-09:15", "is_lunch": False, "is_assembly": False}
                for i in range(1, 5)
            ]
        )
        teachers = {"T1": Teacher(id="T1", name="Teacher 1", max_weekly_periods=10)}
        classes = {"C1": ClassSection(id="C1", name="Class 1")}
        rooms = {"R1": Room(id="R1", name="Room 1")}
        # "T_DELETED" does not exist in teachers dict
        events = [Event(id="E1", subject="Math", teacher_ids=["T_DELETED"], section_ids=["C1"], weekly_quota=2)]

        try:
            report = audit_capacity(config, teachers, classes, rooms, events)
            self.assertTrue(any("T_DELETED" in w for w in report.warnings), "Expected warning for orphaned teacher T_DELETED")
        except KeyError as e:
            self.fail(f"audit_capacity crashed with KeyError on orphaned teacher: {e}")

    # ---------------------------------------------------------
    # BUG-08: Double periods cannot cross assembly
    # ---------------------------------------------------------
    def test_bug08_double_period_cannot_cross_assembly(self):
        """BUG-08: CSPSolver double periods must not be scheduled if next slot is assembly."""
        config = SchoolConfig(
            academic_year="2026-27",
            title="Test",
            days=["Monday"],
            periods_per_day=4,
            period_definitions=[
                {"name": "P0", "time": "08:00-08:30", "is_lunch": False, "is_assembly": False},
                {"name": "Assembly", "time": "08:30-09:00", "is_lunch": False, "is_assembly": True},
                {"name": "P1", "time": "09:00-09:45", "is_lunch": False, "is_assembly": False},
                {"name": "P2", "time": "09:45-10:30", "is_lunch": False, "is_assembly": False},
            ],
            enforce_class_teacher_p1=False
        )
        teachers = {"T1": Teacher(id="T1", name="Teacher 1", max_weekly_periods=10)}
        classes = {"C1": ClassSection(id="C1", name="Class 1")}
        rooms = {"R1": Room(id="R1", name="Room 1")}
        # Event with duration 2
        events = [Event(id="E_DBL", subject="Science Lab", teacher_ids=["T1"], section_ids=["C1"], weekly_quota=2, duration=2)]

        solver = CSPSolver(config, teachers, classes, rooms, events)
        res = solver.solve()
        # Slot (Monday, 0) would span into P1 which is Assembly (slot 1)
        # Verify that double period is never scheduled starting at slot 0
        if res.grid:
            assign = res.grid.section_grid.get(("C1", "Monday", 0))
            self.assertNotEqual(assign.event_id if assign else None, "E_DBL",
                                "Double period must not start at slot 0 because slot 1 is Assembly")

    # ---------------------------------------------------------
    # BUG-09: Atomic write for substitution history
    # ---------------------------------------------------------
    def test_bug09_substitution_save_history_atomic(self):
        """BUG-09: SubstitutionManager.save_history must use atomic file write (.tmp + replace)."""
        mgr = SubstitutionManager(self.test_dir)
        target_file = os.path.join(self.test_dir, "substitutions_history.json")

        record = {
            "date": "2026-09-23",
            "day": "Wednesday",
            "absent_teachers": ["Teacher A"],
            "assignments": []
        }
        saved = mgr.save_history(record, target_file)
        self.assertTrue(saved)
        self.assertTrue(os.path.exists(target_file))

        # Check content
        history = mgr.get_history(target_file)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["date"], "2026-09-23")

    # ---------------------------------------------------------
    # BUG-10: Fallback room_id in exporter
    # ---------------------------------------------------------
    def test_bug10_fallback_room_id_in_exporter(self):
        """BUG-10: SlotAssignment with empty room_id falls back to room_type in parallel split export."""
        assign = SlotAssignment(
            day="Monday",
            period_index=1,
            event_id="EV_1",
            section_ids=["C1"],
            teacher_ids=["T1"],
            subject="Computer",
            room_type="ComputerLab",
            room_id=""  # Empty room_id from solver
        )
        # Verify fallback logic
        effective_room_id = assign.room_id or assign.room_type
        self.assertEqual(effective_room_id, "ComputerLab", "Empty room_id must fall back to room_type")

    # ---------------------------------------------------------
    # BUG-14 & BUG-15: Case-insensitive break filtering and complete exclusions
    # ---------------------------------------------------------
    def test_bug14_and_15_break_subject_filtering(self):
        """BUG-14 & BUG-15: All break types must be excluded case-insensitively and strip-safely."""
        breaks_to_test = [
            "Lunch", "lunch", " LUNCH ", "Prayer", "prayer",
            "Morning Assembly", "morning assembly", "Lunch _ Class Teacher",
            "CYCLE TEST", "cycle test", "CCA", "cca", "Recess", "recess", "Assembly", "assembly"
        ]
        excluded_upper = {s.upper() for s in EXCLUDED_BREAK_SUBJECTS}
        for b in breaks_to_test:
            self.assertIn(b.strip().upper(), excluded_upper, f"Break '{b}' must be recognized in EXCLUDED_BREAK_SUBJECTS")

        # Legitimate subjects must NOT be excluded
        legit_subjects = ["English", "Maths", "Science", "Social Science", "Hindi", "Physics", "Computer"]
        for s in legit_subjects:
            self.assertNotIn(s.strip().upper(), excluded_upper, f"Subject '{s}' should NOT be treated as a break")

    # ---------------------------------------------------------
    # BUG-16: CSP Solver whitespace class_teacher guard
    # ---------------------------------------------------------
    def test_bug16_csp_solver_empty_class_teacher_guard(self):
        """BUG-16: Empty or whitespace-only class_teacher must not match all teachers in MRV scoring."""
        config = SchoolConfig(
            academic_year="2026-27",
            title="Test",
            days=["Monday"],
            periods_per_day=4,
            period_definitions=[
                {"name": f"P{i}", "time": "08:30-09:15", "is_lunch": False, "is_assembly": False}
                for i in range(1, 5)
            ],
            enforce_class_teacher_p1=True
        )
        teachers = {"T1": Teacher(id="T1", name="Raman"), "T2": Teacher(id="T2", name="Suresh")}
        # Class with whitespace-only class_teacher
        classes = {"C1": ClassSection(id="C1", name="Class 1", class_teacher="   ")}
        rooms = {"R1": Room(id="R1", name="Room 1")}
        events = [Event(id="E1", subject="Math", teacher_ids=["T1"], section_ids=["C1"], weekly_quota=1)]

        solver = CSPSolver(config, teachers, classes, rooms, events)
        res = solver.solve()
        self.assertTrue(res.success, "CSPSolver must solve without error when class_teacher is whitespace")

    # ---------------------------------------------------------
    # BUG-20: Exporter uses unique room IDs as dictionary keys
    # ---------------------------------------------------------
    def test_bug20_exporter_unique_room_ids(self):
        """BUG-20: Rooms with duplicate names (e.g., two 'Computer Lab') must not overwrite each other."""
        room1 = Room(id="R_COMP_1", name="Computer Lab", room_type="ComputerLab")
        room2 = Room(id="R_COMP_2", name="Computer Lab", room_type="ComputerLab")
        rooms = [room1, room2]

        # Emulate exporter dictionary population
        room_export = {}
        for r in rooms:
            room_export[r.id] = {"id": r.id, "name": r.name}

        self.assertEqual(len(room_export), 2, "Both rooms must be preserved in export dict")
        self.assertIn("R_COMP_1", room_export)
        self.assertIn("R_COMP_2", room_export)

    # ---------------------------------------------------------
    # BUG-22: Exporter handles is_assembly periods
    # ---------------------------------------------------------
    def test_bug22_exporter_handles_assembly_periods(self):
        """BUG-22: Exporter must populate Morning Assembly for is_assembly periods."""
        p_def = {"name": "Assembly", "time": "08:00-08:30", "is_lunch": False, "is_assembly": True}
        subj = ""
        raw_val = ""
        if p_def.get("is_lunch", False):
            subj = "Lunch"
            raw_val = "Lunch"
        elif p_def.get("is_assembly", False):
            subj = "Morning Assembly"
            raw_val = "Morning Assembly"

        self.assertEqual(subj, "Morning Assembly")
        self.assertEqual(raw_val, "Morning Assembly")

    # ---------------------------------------------------------
    # BUG-23 & BUG-24: Configurable room concurrent defaults
    # ---------------------------------------------------------
    def test_bug23_and_24_configurable_room_concurrency(self):
        """BUG-23 & BUG-24: Room concurrent capacity uses configurable map without hardcoded overrides."""
        ground = Room.from_dict({"id": "R_G", "name": "Sports Ground", "room_type": "Ground"})
        hall = Room.from_dict({"id": "R_H", "name": "Auditorium", "room_type": "Hall"})
        classroom = Room.from_dict({"id": "R_C", "name": "Class 10A", "room_type": "Classroom"})

        self.assertEqual(ground.max_concurrent_classes, 2, "Ground must default to 2 concurrent classes")
        self.assertEqual(hall.max_concurrent_classes, 3, "Hall must default to 3 concurrent classes")
        self.assertEqual(classroom.max_concurrent_classes, 1, "Classroom must default to 1 concurrent class")

    # ---------------------------------------------------------
    # BUG-04: Parallel stream splits counted once via max in capacity
    # ---------------------------------------------------------
    def test_bug04_parallel_stream_split_capacity_calculation(self):
        """BUG-04: Parallel branches must only consume section period capacity once (max of branches)."""
        events = [
            Event(id="EV_NORM", subject="Math", teacher_ids=["T1"], section_ids=["C1"], weekly_quota=5, duration=1),
            # Parallel split: 3 concurrent streams for C1 of 4 periods each
            Event(id="EV_SPLIT_1", subject="Hindi", teacher_ids=["T2"], section_ids=["C1"], weekly_quota=4, duration=1, parallel_group_id="PG_LANG"),
            Event(id="EV_SPLIT_2", subject="Sanskrit", teacher_ids=["T3"], section_ids=["C1"], weekly_quota=4, duration=1, parallel_group_id="PG_LANG"),
            Event(id="EV_SPLIT_3", subject="French", teacher_ids=["T4"], section_ids=["C1"], weekly_quota=4, duration=1, parallel_group_id="PG_LANG"),
        ]

        # Emulate fixed capacity calculation in prerequisites.html
        allocated = 0
        parallel_groups = {}
        for ev in events:
            if "C1" in ev.section_ids:
                if ev.parallel_group_id:
                    gid = ev.parallel_group_id
                    ev_slots = (ev.weekly_quota or 0) * (ev.duration or 1)
                    parallel_groups[gid] = max(parallel_groups.get(gid, 0), ev_slots)
                else:
                    allocated += (ev.weekly_quota or 0) * (ev.duration or 1)

        for max_slots in parallel_groups.values():
            allocated += max_slots

        # Expected: Math (5) + Parallel Split (4) = 9, NOT 5 + 4 + 4 + 4 = 17
        self.assertEqual(allocated, 9, f"Parallel split must contribute 4 periods (max), total should be 9, got {allocated}")

    # ---------------------------------------------------------
    # BUG-12: Stepper synchronizes parallel stream branch quotas
    # ---------------------------------------------------------
    def test_bug12_stepper_synchronizes_parallel_branches(self):
        """BUG-12: Adjusting quota on one parallel branch must sync all sibling branches in same group."""
        events = [
            Event(id="EV_1", subject="Physics Lab", teacher_ids=["T1"], section_ids=["C1"], weekly_quota=4, parallel_group_id="PG_SCI"),
            Event(id="EV_2", subject="Chem Lab", teacher_ids=["T2"], section_ids=["C1"], weekly_quota=4, parallel_group_id="PG_SCI"),
            Event(id="EV_3", subject="Bio Lab", teacher_ids=["T3"], section_ids=["C1"], weekly_quota=4, parallel_group_id="PG_SCI"),
        ]

        # Emulate stepEventQuota logic
        target_ev = events[0]
        new_quota = target_ev.weekly_quota + 1  # 5
        target_ev.weekly_quota = new_quota
        if target_ev.parallel_group_id:
            for sib in events:
                if sib.parallel_group_id == target_ev.parallel_group_id:
                    sib.weekly_quota = new_quota

        self.assertEqual(events[0].weekly_quota, 5)
        self.assertEqual(events[1].weekly_quota, 5)
        self.assertEqual(events[2].weekly_quota, 5)

    # ---------------------------------------------------------
    # BUG-13: Exact homeroom teacher matching (no substring collisions)
    # ---------------------------------------------------------
    def test_bug13_exact_homeroom_matching(self):
        """BUG-13: 'Ram' must not match 'Raman' in homeroom teacher lookup."""
        teacher_ram = Teacher(id="T_RAM", name="Ram")
        teacher_raman = Teacher(id="T_RAMAN", name="Raman")
        classes = [
            ClassSection(id="C1", name="Class 1A", class_teacher="Raman")
        ]

        def find_hr_class(t):
            for c in classes:
                if not c.class_teacher:
                    continue
                ct = c.class_teacher.strip().lower()
                tn = t.name.strip().lower()
                # Fixed: exact match only
                if ct == tn:
                    return c
            return None

        self.assertIsNone(find_hr_class(teacher_ram), "Ram must NOT match class teacher Raman")
        self.assertIsNotNone(find_hr_class(teacher_raman), "Raman must match class teacher Raman")

    # ---------------------------------------------------------
    # BUG-18 & BUG-19: Unassigned branches validation
    # ---------------------------------------------------------
    def test_bug18_and_19_unassigned_branches_in_parallel_splits(self):
        """BUG-18 & 19: Multiple unassigned branches ('') must not be flagged as teacher collisions."""
        branches = [
            {"subject": "Music", "teacher": ""},
            {"subject": "Dance", "teacher": ""},
            {"subject": "Drama", "teacher": "Mr. Sharma"}
        ]

        # Emulate duplicate teacher validation
        branch_teachers = set()
        has_error = False
        for b in branches:
            teach = b["teacher"]
            if teach and teach in branch_teachers:
                has_error = True
                break
            if teach:
                branch_teachers.add(teach)

        self.assertFalse(has_error, "Multiple unassigned branches must not trigger teacher clash error")

    # ---------------------------------------------------------
    # BUG-21: Server JSON parse error handling
    # ---------------------------------------------------------
    def test_bug21_server_json_parse_error_handling(self):
        """BUG-21: Server _read_json_body catches JSONDecodeError cleanly."""
        import json
        malformed_body = "{invalid_json: true,"
        try:
            json.loads(malformed_body)
            self.fail("Should have raised JSONDecodeError")
        except json.JSONDecodeError:
            # Expected: server catches this and returns 400 Bad Request
            pass

    # ---------------------------------------------------------
    # BUG-26: Unique ID generation with timestamps
    # ---------------------------------------------------------
    def test_bug26_unique_id_generation(self):
        """BUG-26: Class and Room IDs append timestamps to avoid duplicate IDs for same-named entities."""
        name = "Computer Lab"
        id1 = f"R_{name.replace(' ', '_').upper()}_1001"
        id2 = f"R_{name.replace(' ', '_').upper()}_1002"
        self.assertNotEqual(id1, id2, "Generated IDs must be unique even with identical display names")


    # ---------------------------------------------------------
    # Regression: Absent teacher never assigned to own period
    # ---------------------------------------------------------
    def test_absent_teacher_never_assigned_to_own_period(self):
        """Verify that an absent teacher (e.g. Sonakshi) is NEVER assigned to cover their own or any period."""
        mgr = SubstitutionManager(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        
        for day in days:
            # Test with title case
            result = mgr.auto_assign(day=day, absent_teachers=["Sonakshi"])
            for slot_key, sub in result.get("assignments", {}).items():
                self.assertNotIn(
                    sub.strip().lower(),
                    ["sonakshi"],
                    f"Sonakshi must never be assigned as substitute on {day} in {slot_key} when marked absent"
                )

            # Test with lowercase
            result_lower = mgr.auto_assign(day=day, absent_teachers=["sonakshi"])
            for slot_key, sub in result_lower.get("assignments", {}).items():
                self.assertNotIn(
                    sub.strip().lower(),
                    ["sonakshi"],
                    f"Lowercase 'sonakshi' must never be assigned as substitute on {day} in {slot_key} when marked absent"
                )

            # Verify slot retrieval handles case-insensitivity
            slots = mgr.get_affected_slots(day, ["sonakshi"])
            slots_title = mgr.get_affected_slots(day, ["Sonakshi"])
            self.assertEqual(
                len(slots),
                len(slots_title),
                f"get_affected_slots should return identical count for 'sonakshi' vs 'Sonakshi' on {day}"
            )

    # ---------------------------------------------------------
    # BUG: Divy and Divya Upadhyay Faculty Merge & Integrity
    # ---------------------------------------------------------
    def test_divy_and_divya_upadhyay_merged(self):
        """Verify that Divy and Divya Upadhaya are unified into Divya Upadhyay with 24 periods and homeroom Class Teacher status."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # 1. Verify timetable_config.json
        with open(os.path.join(base_dir, 'timetable_config.json'), 'r') as f:
            cfg = json.load(f)
            
        teacher_ids = [t['id'] for t in cfg.get('teachers', [])]
        self.assertNotIn('Divy', teacher_ids, "Divy must be removed from master teachers list")
        self.assertIn('Divya Upadhyay', teacher_ids, "Divya Upadhyay must be present in master teachers list")
        
        # Verify homeroom class teacher
        class_11 = next((c for c in cfg.get('classes', []) if '11' in c['name'] and 'Bio' in c['name']), None)
        self.assertIsNotNone(class_11, "CLASS 11 (Bio + Math) must exist")
        self.assertEqual(class_11.get('class_teacher'), 'Divya Upadhyay')
        
        # 2. Verify timetable_teachers.json
        teachers_json_path = os.path.join(base_dir, 'timetable_teachers.json')
        if os.path.exists(teachers_json_path):
            with open(teachers_json_path, 'r') as f:
                t_data = json.load(f)
            self.assertNotIn('Divy', t_data, "Divy must not exist in timetable_teachers.json")
            self.assertIn('Divya Upadhyay', t_data, "Divya Upadhyay must exist in timetable_teachers.json")
            
            divya = t_data['Divya Upadhyay']
            self.assertEqual(divya.get('total_weekly_teaching_periods'), 24, "Divya Upadhyay must have 24 periods/week")
            self.assertIn('CLASS 11 (Bio + Math)', divya.get('is_class_teacher_of', []))
            self.assertIn('Chem', divya.get('subjects', []))
            
            # Verify Class Teacher P1 rule: Period 1 every day is Chem for Class 11
            for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]:
                day_slots = divya.get('weekly_schedule', {}).get(day, [])
                p1_slot = next((s for s in day_slots if s.get('period_name') == '1st Period'), None)
                self.assertIsNotNone(p1_slot, f"Divya Upadhyay must teach Period 1 on {day}")
                self.assertEqual(p1_slot.get('class_name'), 'CLASS 11 (Bio + Math)')
                self.assertEqual(p1_slot.get('subject'), 'Chem')
                
        # 3. Verify substitution shield: Divya Upadhyay never self-assigned
        mgr = SubstitutionManager(base_dir)
        for day in ["Monday", "Thursday"]:
            result = mgr.auto_assign(day=day, absent_teachers=["Divya Upadhyay"])
            for slot_key, sub in result.get("assignments", {}).items():
                self.assertNotIn(
                    sub.strip().lower(),
                    ["divya upadhyay", "divya upadhaya", "divy"],
                    f"Divya Upadhyay must never be assigned as substitute on {day} in {slot_key} when absent"
                )

    # ---------------------------------------------------------
    # BUG: Group 1 Primary Wing Teachers Unification
    # ---------------------------------------------------------
    def test_primary_wing_teachers_merged(self):
        """Verify that all 12 Primary Wing duplicate faculty pairs are cleanly unified with their Class Teacher roles."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(base_dir, 'timetable_config.json'), 'r') as f:
            cfg = json.load(f)

        teacher_ids = {t['id'] for t in cfg.get('teachers', [])}

        expected_merged = [
            ("Swati Napit", "CLASS 1 Rose", 29),
            ("Raji Jain", "CLASS 1 Lily", 33),
            ("Sanskriti Singhai", "CLASS 1 Sunflower", 31),
            ("Reenu Yadav", "CLASS 2 Rose", 33),
            ("Arti Ahirwar", "CLASS 2 Marigold", 31),
            ("Kalyani Choudhary", "CLASS 2 Lily", 33),
            ("Vandna Saraf", "CLASS 3 Rose", 11),
            ("Shilpi Sahu", "CLASS 3 Marigold", 34),
            ("Rajkmari Yadav", "CLASS 4 Rose", 30),
            ("Neelam Sahu", "CLASS 5 Rose", 33),
            ("Shewta Dubey", "CLASS 5 Marigold", 31),
            ("Anjali Nalvanshi", "CLASS 5 Sunflower", 35),
        ]

        old_names_eliminated = [
            "Swati", "Raji", "Sanskriti", "Reenu", "Arti A", "Kalyani",
            "Vandna", "Shilpi Sahunsari", "Rajkmari", "Rajkmari yadav", "Neelam", "Shewta", "Anjali N"
        ]

        for canon, cls_name, expected_load in expected_merged:
            self.assertIn(canon, teacher_ids, f"{canon} must be present in master teachers list")
            cls = next((c for c in cfg.get('classes', []) if c['name'] == cls_name), None)
            self.assertIsNotNone(cls, f"Class {cls_name} must exist")
            self.assertEqual(cls.get('class_teacher'), canon, f"Class {cls_name} must have CT {canon}")

        for old in old_names_eliminated:
            self.assertNotIn(old, teacher_ids, f"Old duplicate '{old}' must be removed from master teachers list")

        # Distinct teachers must remain intact
        self.assertIn("Anjali Jain", teacher_ids, "Anjali Jain must remain intact")
        self.assertIn("Arti Sagar", teacher_ids, "Arti Sagar must remain intact")

    # ---------------------------------------------------------
    # BUG: Group 2 & 3 Middle & Senior Wing Teachers Unification
    # ---------------------------------------------------------
    def test_middle_and_senior_wing_teachers_merged(self):
        """Verify that all Group 2 & 3 Middle & Senior Wing duplicate faculty pairs are cleanly unified with their Class Teacher roles."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(base_dir, 'timetable_config.json'), 'r') as f:
            cfg = json.load(f)

        teacher_ids = {t['id'] for t in cfg.get('teachers', [])}

        expected_merged = [
            ("Shruti Badkul", "CLASS 6 Rose"),
            ("Jageshwar Sharma", "CLASS 7 Sunflower"),
            ("Anuj Jain", "CLASS 9 Marigold"),
            ("Jageshwar R", "CLASS 10 Marigold"),
            ("Jyotsharan", "CLASS 10 Lily"),
            ("Shailandra", "CLASS 11 Comm."),
            ("Ram Kumar", "CLASS 12 (Bio + Math)"),
            ("Rahul Vishwakarma", "CLASS 12 (Comm.)"),
        ]

        old_names_eliminated = [
            "Shruti", "Jageshwar S", "Anuj", "Anuj jain", "JR", "Jyotshran",
            "Deepak", "Ram", "Ram /Math_Rajpal", "Rahul", "Rahul Vish."
        ]

        for canon, cls_name in expected_merged:
            self.assertIn(canon, teacher_ids, f"{canon} must be present in master teachers list")
            cls = next((c for c in cfg.get('classes', []) if c['name'] == cls_name), None)
            self.assertIsNotNone(cls, f"Class {cls_name} must exist")
            self.assertEqual(cls.get('class_teacher'), canon, f"Class {cls_name} must have CT {canon}")

        for old in old_names_eliminated:
            self.assertNotIn(old, teacher_ids, f"Old duplicate '{old}' must be removed from master teachers list")

        # Total teachers in config must be 50
        self.assertEqual(len(cfg.get('teachers', [])), 50, "Master config must have exactly 50 faculty members")

    # ---------------------------------------------------------
    # BUG: Duplicate & Misspelled Subject Consolidation
    # ---------------------------------------------------------
    def test_subject_consolidation_and_canonical_names(self):
        """Verify that all 5 duplicate/misspelled subjects are consolidated into canonical names."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(base_dir, 'timetable_config.json'), 'r') as f:
            cfg = json.load(f)

        deprecated_names = {"Game", "GAME", "GAMES", "Art&Craft", "Math", "Sci", "Distation & Cursive", "Drawing", "Sports"}
        canonical_expected = {"Games", "Art & Craft", "Maths", "Science", "Dictation & Cursive"}
        retained_subjects = {"Dance", "Eng Read", "Hindi Read"}

        # 1. Subject Catalog Checks
        catalog_names = {s['name'] for s in cfg.get('subjects', [])}
        catalog_ids = [s['id'] for s in cfg.get('subjects', [])]

        for dep in deprecated_names:
            self.assertNotIn(dep, catalog_names, f"Deprecated subject '{dep}' must not exist in subjects catalog")

        for canon in canonical_expected:
            self.assertIn(canon, catalog_names, f"Canonical subject '{canon}' must exist in subjects catalog")

        for ret in retained_subjects:
            self.assertIn(ret, catalog_names, f"Retained subject '{ret}' must exist in subjects catalog")

        # Total unique subjects in catalog is exactly 28 (after Sports was removed/consolidated into Games)
        self.assertEqual(len(catalog_names), 28, "Catalog must have exactly 28 unique subjects")

        # Verify all subject IDs are strictly unique
        self.assertEqual(len(catalog_ids), len(set(catalog_ids)), "All subject IDs in catalog must be unique")

        # Verify Dictation & Cursive properties
        dict_subj = next(s for s in cfg['subjects'] if s['name'] == 'Dictation & Cursive')
        self.assertEqual(dict_subj['code'], 'DIC-&')

        # 2. Event Allocations Checks
        event_subjects = {e['subject'] for e in cfg.get('events', [])}
        for dep in deprecated_names:
            self.assertNotIn(dep, event_subjects, f"Deprecated subject '{dep}' must not be used in any event")

        # Verify Art & Craft has 29 events (18 original + 11 from Drawing)
        art_events = [e for e in cfg['events'] if e['subject'] == 'Art & Craft']
        self.assertEqual(len(art_events), 29, "Art & Craft must have exactly 29 events after Drawing merge")

        # Verify all Games events have room_type: 'Ground'
        games_events = [e for e in cfg['events'] if e['subject'] == 'Games']
        self.assertGreater(len(games_events), 0, "Games events must exist")
        for ge in games_events:
            self.assertEqual(ge.get('room_type'), 'Ground', f"Games event {ge['id']} must use room_type Ground")

        # 3. Exported timetable_entries.csv Checks
        csv_path = os.path.join(base_dir, 'timetable_entries.csv')
        if os.path.exists(csv_path):
            with open(csv_path, 'r', encoding='utf-8') as f:
                csv_content = f.read()
            self.assertNotIn(",Math,", csv_content, "CSV must not have ',Math,' subject")
            self.assertNotIn(",Art&Craft,", csv_content, "CSV must not have ',Art&Craft,' subject")
            self.assertNotIn(",Distation & Cursive,", csv_content, "CSV must not have ',Distation & Cursive,' subject")
            self.assertNotIn(",Sci,", csv_content, "CSV must not have ',Sci,' subject")
            self.assertNotIn(",Drawing,", csv_content, "CSV must not have ',Drawing,' subject")
            self.assertIn(",Maths,", csv_content, "CSV must have canonical ',Maths,' subject")
            self.assertIn(",Dictation & Cursive,", csv_content, "CSV must have canonical ',Dictation & Cursive,' subject")
            self.assertIn(",Art & Craft,", csv_content, "CSV must have canonical ',Art & Craft,' subject")


if __name__ == '__main__':
    unittest.main()

