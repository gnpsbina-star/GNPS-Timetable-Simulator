import unittest
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.models import SchoolConfig, Teacher, ClassSection, Room, Event, SlotAssignment, TimetableGrid

class TestElectivesModule(unittest.TestCase):
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
            enforce_class_teacher_p1=False
        )

    def test_event_joint_and_parallel_properties_and_serialization(self):
        """Module 4: Verify Event joint and parallel elective properties and JSON serialization."""
        ev_joint = Event(
            id="EV_JOINT_ECO",
            subject="Economics",
            teacher_ids=["Rahul"],
            section_ids=["CLASS_12_Comm", "CLASS_12_Arts"],
            weekly_quota=6,
            is_joint=True,
            joint_label="Class 12 Comm & Arts Economics"
        )
        self.assertTrue(ev_joint.is_joint)
        self.assertTrue(ev_joint.is_clubbed)
        self.assertEqual(ev_joint.joint_label, "Class 12 Comm & Arts Economics")

        d_joint = ev_joint.to_dict()
        self.assertTrue(d_joint.get("is_joint"))
        self.assertEqual(d_joint.get("joint_label"), "Class 12 Comm & Arts Economics")

        ev_reloaded = Event.from_dict(d_joint)
        self.assertTrue(ev_reloaded.is_joint)
        self.assertEqual(len(ev_reloaded.section_ids), 2)

        # Parallel split event
        ev_split = Event(
            id="EV_11_BIO",
            subject="Biology",
            teacher_ids=["Anuj"],
            section_ids=["CLASS_11_Sci"],
            weekly_quota=6,
            parallel_group_id="PG_11_SCI_ELECTIVE",
            elective_basket="Senior Science Stream Elective"
        )
        self.assertTrue(ev_split.is_parallel_split)
        self.assertEqual(ev_split.parallel_group_id, "PG_11_SCI_ELECTIVE")

        d_split = ev_split.to_dict()
        self.assertEqual(d_split.get("parallel_group_id"), "PG_11_SCI_ELECTIVE")
        self.assertEqual(d_split.get("elective_basket"), "Senior Science Stream Elective")

        ev_split_reloaded = Event.from_dict(d_split)
        self.assertTrue(ev_split_reloaded.is_parallel_split)

    def test_joint_class_collision_freedom(self):
        """Module 4: Verify that a single teacher teaching multiple joint sections has zero false clashes."""
        grid = TimetableGrid(self.config)
        ev_joint = Event(
            id="EV_JOINT_12_ECO",
            subject="Economics",
            teacher_ids=["Rahul"],
            section_ids=["CLASS_12_Comm", "CLASS_12_Arts"],
            weekly_quota=6,
            is_joint=True
        )

        assign = SlotAssignment(
            event_id=ev_joint.id,
            day="Monday",
            period_index=2,
            subject=ev_joint.subject,
            teacher_ids=ev_joint.teacher_ids,
            section_ids=ev_joint.section_ids,
            is_joint=True,
            joint_label="Class 12 Comm + Arts Economics"
        )
        grid.assign(assign)

        # Confirm 0 clashes detected in grid
        clashes = grid.detect_all_clashes()
        self.assertEqual(len(clashes), 0, "Joint class must not trigger teacher double-booking")

        # Confirm candidate check for another class with Rahul in Monday P2 -> MUST CLASH
        ev_other_teacher = Event(
            id="EV_OTHER_TEACHER",
            subject="Business Studies",
            teacher_ids=["Rahul"],
            section_ids=["CLASS_11_Comm"],
            weekly_quota=1
        )
        t_clashes = grid.check_clash(ev_other_teacher, "Monday", 2)
        self.assertTrue(len(t_clashes) > 0, "Teacher double booking must be detected")
        self.assertTrue(any("already teaching" in c for c in t_clashes))

        # Confirm candidate check for another class for CLASS_12_Comm in Monday P2 -> MUST CLASH
        ev_other_sec = Event(
            id="EV_OTHER_SEC",
            subject="Accounts",
            teacher_ids=["OtherTeacher"],
            section_ids=["CLASS_12_Comm"],
            weekly_quota=1
        )
        sec_clashes = grid.check_clash(ev_other_sec, "Monday", 2)
        self.assertTrue(len(sec_clashes) > 0, "Section double booking must be detected")
        self.assertTrue(any("already has" in c for c in sec_clashes))

    def test_parallel_elective_split_collision_freedom(self):
        """Module 4: Verify that parallel elective branches (e.g. Bio vs Math) run simultaneously without class clash."""
        grid = TimetableGrid(self.config)
        pg_id = "PG_11_SCI_ELECTIVE"

        ev_bio = Event(
            id="EV_11_BIO",
            subject="Biology",
            teacher_ids=["Anuj"],
            section_ids=["CLASS_11_Sci"],
            parallel_group_id=pg_id
        )
        ev_math = Event(
            id="EV_11_MATH",
            subject="Mathematics",
            teacher_ids=["Vandna"],
            section_ids=["CLASS_11_Sci"],
            parallel_group_id=pg_id
        )

        # 1. Assign ev_bio to Monday Period 3
        assign_bio = SlotAssignment(
            event_id=ev_bio.id,
            day="Monday",
            period_index=3,
            subject=ev_bio.subject,
            teacher_ids=ev_bio.teacher_ids,
            section_ids=ev_bio.section_ids,
            parallel_group_id=pg_id
        )
        grid.assign(assign_bio)

        # 2. Candidate check for ev_math in the exact same slot -> MUST BE 100% CLEAR (same parallel_group_id)
        clashes_math = grid.check_clash(ev_math, "Monday", 3)
        self.assertEqual(len(clashes_math), 0, "Parallel elective branch sharing parallel_group_id must not clash with co-branch")

        # 3. Assign ev_math to Monday Period 3
        assign_math = SlotAssignment(
            event_id=ev_math.id,
            day="Monday",
            period_index=3,
            subject=ev_math.subject,
            teacher_ids=ev_math.teacher_ids,
            section_ids=ev_math.section_ids,
            parallel_group_id=pg_id
        )
        grid.assign(assign_math)

        # 4. Verify detect_all_clashes sees this as a valid elective split with 0 clashes!
        all_clashes = grid.detect_all_clashes()
        self.assertEqual(len(all_clashes), 0, "Parallel elective split should produce 0 grid clashes")

        # 5. Candidate check for an unrelated 3rd event for CLASS_11_Sci (e.g. Physics) in Monday Period 3 -> MUST CLASH
        ev_physics = Event(
            id="EV_11_PHYS",
            subject="Physics",
            teacher_ids=["Deepak"],
            section_ids=["CLASS_11_Sci"]
        )
        phys_clashes = grid.check_clash(ev_physics, "Monday", 3)
        self.assertTrue(len(phys_clashes) > 0, "Unrelated lesson attempting to take split slot must clash")
        self.assertTrue(any("already has" in c for c in phys_clashes))

    def test_parallel_elective_teacher_mutual_exclusion(self):
        """Module 4: Verify that teachers assigned to parallel elective branches cannot teach other classes simultaneously."""
        grid = TimetableGrid(self.config)
        pg_id = "PG_11_SCI_ELECTIVE"

        ev_bio = Event(
            id="EV_11_BIO",
            subject="Biology",
            teacher_ids=["Anuj"],
            section_ids=["CLASS_11_Sci"],
            parallel_group_id=pg_id
        )
        assign_bio = SlotAssignment(
            event_id=ev_bio.id,
            day="Tuesday",
            period_index=4,
            subject="Biology",
            teacher_ids=["Anuj"],
            section_ids=["CLASS_11_Sci"],
            parallel_group_id=pg_id
        )
        grid.assign(assign_bio)

        # Anuj tries to teach Class 9 Science in the same slot -> MUST CLASH
        ev_c9 = Event(
            id="EV_9_SCI",
            subject="Science",
            teacher_ids=["Anuj"],
            section_ids=["CLASS_9_Rose"]
        )
        t_clashes = grid.check_clash(ev_c9, "Tuesday", 4)
        self.assertTrue(len(t_clashes) > 0)
        self.assertTrue(any("already teaching" in c for c in t_clashes))

    def test_solver_parallel_elective_co_location_and_room_shield(self):
        """Module 4: Verify CSPSolver schedules all parallel elective branches in identical slots with room shield."""
        from engine.csp_solver import CSPSolver

        teachers = {
            "T_BIO": Teacher(id="T_BIO", name="Anuj", max_weekly_periods=10, max_daily_periods=3),
            "T_MATH": Teacher(id="T_MATH", name="Vandna", max_weekly_periods=10, max_daily_periods=3),
            "T_IP": Teacher(id="T_IP", name="Jyotsharan", max_weekly_periods=10, max_daily_periods=3),
            "T_ENG": Teacher(id="T_ENG", name="Pradeep", max_weekly_periods=10, max_daily_periods=3)
        }

        classes = {
            "CLASS_11_Sci": ClassSection(id="CLASS_11_Sci", name="Class 11 Science", wing="Senior"),
            "CLASS_10_Rose": ClassSection(id="CLASS_10_Rose", name="Class 10 Rose", wing="Middle")
        }

        rooms = {
            "R_BIO": Room(id="R_BIO", name="Bio Lab", room_type="ScienceLab"),
            "R_COMP": Room(id="R_COMP", name="Computer Lab", room_type="ComputerLab"),
            "R_101": Room(id="R_101", name="Room 101", room_type="Classroom")
        }

        pg_id = "PG_11_SCI_ELECTIVE"
        events = [
            # 3-branch parallel elective split for Class 11 Science
            Event(
                id="EV_BIO",
                subject="Biology",
                teacher_ids=["T_BIO"],
                section_ids=["CLASS_11_Sci"],
                room_type="ScienceLab",
                weekly_quota=2,
                parallel_group_id=pg_id,
                elective_basket="Senior Science Stream"
            ),
            Event(
                id="EV_MATH",
                subject="Mathematics",
                teacher_ids=["T_MATH"],
                section_ids=["CLASS_11_Sci"],
                room_type="Classroom",
                weekly_quota=2,
                parallel_group_id=pg_id,
                elective_basket="Senior Science Stream"
            ),
            Event(
                id="EV_IP",
                subject="IP",
                teacher_ids=["T_IP"],
                section_ids=["CLASS_11_Sci"],
                room_type="ComputerLab",
                weekly_quota=2,
                parallel_group_id=pg_id,
                elective_basket="Senior Science Stream"
            ),
            # Regular English lessons
            Event(id="EV_11_ENG", subject="English", teacher_ids=["T_ENG"], section_ids=["CLASS_11_Sci"], weekly_quota=2),
            Event(id="EV_10_ENG", subject="English 10", teacher_ids=["T_ENG"], section_ids=["CLASS_10_Rose"], weekly_quota=2)
        ]

        solver = CSPSolver(
            config=self.config,
            teachers=teachers,
            classes=classes,
            rooms=rooms,
            events=events
        )
        res = solver.solve()
        self.assertTrue(res.success, f"CSPSolver failed with error: {res.message}")

        grid = res.grid
        self.assertIsNotNone(grid)

        # 1. Verify 100% collision freedom across the whole grid
        clashes = grid.detect_all_clashes(solver.rooms_by_type)
        self.assertEqual(len(clashes), 0, f"Expected 0 clashes but found: {clashes}")

        # 2. Verify all 3 branches of PG_11_SCI_ELECTIVE are scheduled at EXACTLY the same (day, period) slots
        bio_slots = {(day, p) for (sec, day, p), assigns in grid.section_grid_all.items()
                     if sec == "CLASS_11_Sci" and any(a.subject == "Biology" for a in assigns)}
        math_slots = {(day, p) for (sec, day, p), assigns in grid.section_grid_all.items()
                      if sec == "CLASS_11_Sci" and any(a.subject == "Mathematics" for a in assigns)}
        ip_slots = {(day, p) for (sec, day, p), assigns in grid.section_grid_all.items()
                    if sec == "CLASS_11_Sci" and any(a.subject == "IP" for a in assigns)}

        self.assertEqual(len(bio_slots), 2, "Biology must be scheduled exactly 2 periods")
        self.assertEqual(bio_slots, math_slots, "Biology and Mathematics must be scheduled in identical slots")
        self.assertEqual(bio_slots, ip_slots, "Biology and IP must be scheduled in identical slots")

        # 3. Verify each split period in Class 11 Science contains all 3 concurrent assignments
        for slot in bio_slots:
            day, p = slot
            assigns = grid.section_grid_all.get(("CLASS_11_Sci", day, p), [])
            self.assertEqual(len(assigns), 3, f"Slot {slot} must have 3 parallel assignments")
            assigned_subjects = {a.subject for a in assigns}
            self.assertEqual(assigned_subjects, {"Biology", "Mathematics", "IP"})
            # Verify elective basket and parallel group tags
            for a in assigns:
                self.assertEqual(a.parallel_group_id, pg_id)
                self.assertEqual(a.elective_basket, "Senior Science Stream")

        # 4. Verify facility bookings
        for day, p in bio_slots:
            bio_lab_assigns = grid.room_type_grid.get(("ScienceLab", day, p), [])
            self.assertEqual(len(bio_lab_assigns), 1)
            self.assertEqual(bio_lab_assigns[0].subject, "Biology")

            comp_lab_assigns = grid.room_type_grid.get(("ComputerLab", day, p), [])
            self.assertEqual(len(comp_lab_assigns), 1)
            self.assertEqual(comp_lab_assigns[0].subject, "IP")

    def test_solver_joint_class_scheduling(self):
        """Module 4: Verify CSPSolver schedules joint multi-section lessons with deduplicated teacher load."""
        from engine.csp_solver import CSPSolver

        teachers = {
            "T_RAHUL": Teacher(id="T_RAHUL", name="Rahul", max_weekly_periods=10, max_daily_periods=3),
            "T_AVDESH": Teacher(id="T_AVDESH", name="Avdesh", max_weekly_periods=10, max_daily_periods=3)
        }

        classes = {
            "CLASS_12_Comm": ClassSection(id="CLASS_12_Comm", name="Class 12 Commerce", wing="Senior"),
            "CLASS_12_Arts": ClassSection(id="CLASS_12_Arts", name="Class 12 Arts", wing="Senior"),
            "CLASS_11_Comm": ClassSection(id="CLASS_11_Comm", name="Class 11 Commerce", wing="Senior")
        }

        rooms = {
            "R_101": Room(id="R_101", name="Room 101", room_type="Classroom")
        }

        events = [
            # Joint class: Rahul teaches Economics to Class 12 Comm and Class 12 Arts simultaneously
            Event(
                id="EV_JOINT_12_ECO",
                subject="Economics",
                teacher_ids=["T_RAHUL"],
                section_ids=["CLASS_12_Comm", "CLASS_12_Arts"],
                weekly_quota=3,
                is_joint=True,
                joint_label="Class 12 Comm & Arts Economics"
            ),
            # Independent class for Class 11 Comm taught by Avdesh
            Event(
                id="EV_11_COMM_ACC",
                subject="Accounts",
                teacher_ids=["T_AVDESH"],
                section_ids=["CLASS_11_Comm"],
                weekly_quota=3
            )
        ]

        solver = CSPSolver(
            config=self.config,
            teachers=teachers,
            classes=classes,
            rooms=rooms,
            events=events
        )
        res = solver.solve()
        self.assertTrue(res.success, f"CSPSolver failed with error: {res.message}")

        grid = res.grid
        self.assertIsNotNone(grid)

        # 1. 0 clashes
        clashes = grid.detect_all_clashes()
        self.assertEqual(len(clashes), 0, f"Expected 0 clashes but found: {clashes}")

        # 2. Verify Rahul teaches 3 deduplicated contact periods
        workload = grid.get_teacher_workload("T_RAHUL")
        self.assertEqual(workload["total_weekly_periods"], 3,
                         "Joint class should count as 3 physical contact periods for Rahul")

        # 3. Verify both Class 12 Comm and Class 12 Arts have Economics at the exact same slots
        comm_slots = {(d, p) for (sec, d, p), a in grid.section_grid.items()
                      if sec == "CLASS_12_Comm" and a.subject == "Economics"}
        arts_slots = {(d, p) for (sec, d, p), a in grid.section_grid.items()
                      if sec == "CLASS_12_Arts" and a.subject == "Economics"}

        self.assertEqual(len(comm_slots), 3)
        self.assertEqual(comm_slots, arts_slots, "Joint sections must have lessons in the exact same slots")

        # 4. Check joint badges on slot assignments
        for d, p in comm_slots:
            comm_assign = grid.section_grid[("CLASS_12_Comm", d, p)]
            self.assertTrue(comm_assign.is_joint)
            self.assertEqual(comm_assign.joint_label, "Class 12 Comm & Arts Economics")

            arts_assign = grid.section_grid[("CLASS_12_Arts", d, p)]
            self.assertTrue(arts_assign.is_joint)
            self.assertEqual(arts_assign.joint_label, "Class 12 Comm & Arts Economics")

    def test_precheck_parallel_elective_teacher_conflict_detection(self):
        """Module 4: Verify precheck audit detects when a teacher is assigned to multiple branches of the same split."""
        from engine.precheck import audit_capacity

        teachers = {
            "T_ANUJ": Teacher(id="T_ANUJ", name="Anuj", max_weekly_periods=20),
            "T_VANDNA": Teacher(id="T_VANDNA", name="Vandna", max_weekly_periods=20)
        }
        classes = {
            "CLASS_11_Sci": ClassSection(id="CLASS_11_Sci", name="Class 11 Science", wing="Senior")
        }
        rooms = {
            "R1": Room(id="R1", name="Room 101", room_type="Classroom")
        }
        # Impossible configuration: Anuj is assigned to BOTH Biology and Chemistry in the same parallel split!
        events = [
            Event(
                id="EV_BIO",
                subject="Biology",
                teacher_ids=["T_ANUJ"],
                section_ids=["CLASS_11_Sci"],
                weekly_quota=4,
                parallel_group_id="PG_11_SPLIT",
                elective_basket="Senior Split"
            ),
            Event(
                id="EV_CHEM",
                subject="Chemistry",
                teacher_ids=["T_ANUJ"],
                section_ids=["CLASS_11_Sci"],
                weekly_quota=4,
                parallel_group_id="PG_11_SPLIT",
                elective_basket="Senior Split"
            )
        ]

        report = audit_capacity(self.config, teachers, classes, rooms, events)
        self.assertFalse(report.is_feasible)
        self.assertTrue(any("assigned to multiple simultaneous branches" in err for err in report.errors),
                        f"Expected teacher conflict error but got: {report.errors}")

    def test_precheck_parallel_elective_room_bottleneck_detection(self):
        """Module 4: Verify precheck audit catches when split branches demand more specialized rooms than exist."""
        from engine.precheck import audit_capacity

        teachers = {
            "T_ANUJ": Teacher(id="T_ANUJ", name="Anuj", max_weekly_periods=20),
            "T_JYOT": Teacher(id="T_JYOT", name="Jyotsharan", max_weekly_periods=20)
        }
        classes = {
            "CLASS_11_Sci": ClassSection(id="CLASS_11_Sci", name="Class 11 Science", wing="Senior")
        }
        # School has ONLY 1 Computer Lab
        rooms = {
            "R_COMP1": Room(id="R_COMP1", name="Computer Lab", room_type="ComputerLab", max_concurrent_classes=1)
        }
        # Both branches in parallel split demand ComputerLab simultaneously!
        events = [
            Event(
                id="EV_IP",
                subject="IP",
                teacher_ids=["T_JYOT"],
                section_ids=["CLASS_11_Sci"],
                room_type="ComputerLab",
                weekly_quota=4,
                parallel_group_id="PG_11_SPLIT"
            ),
            Event(
                id="EV_CS",
                subject="Computer Science",
                teacher_ids=["T_ANUJ"],
                section_ids=["CLASS_11_Sci"],
                room_type="ComputerLab",
                weekly_quota=4,
                parallel_group_id="PG_11_SPLIT"
            )
        ]

        report = audit_capacity(self.config, teachers, classes, rooms, events)
        self.assertFalse(report.is_feasible)
        self.assertTrue(any("Requires 2 simultaneous 'ComputerLab' facilities" in err for err in report.errors),
                        f"Expected room bottleneck error but got: {report.errors}")

    def test_precheck_parallel_elective_feasibility_pass(self):
        """Module 4: Verify precheck passes and populates elective audit stats for feasible parallel configurations."""
        from engine.precheck import audit_capacity

        teachers = {
            "T_ANUJ": Teacher(id="T_ANUJ", name="Anuj", max_weekly_periods=20),
            "T_VANDNA": Teacher(id="T_VANDNA", name="Vandna", max_weekly_periods=20)
        }
        classes = {
            "CLASS_11_Sci": ClassSection(id="CLASS_11_Sci", name="Class 11 Science", wing="Senior")
        }
        rooms = {
            "R_BIO": Room(id="R_BIO", name="Bio Lab", room_type="ScienceLab"),
            "R_101": Room(id="R_101", name="Room 101", room_type="Classroom")
        }
        events = [
            Event(
                id="EV_BIO",
                subject="Biology",
                teacher_ids=["T_ANUJ"],
                section_ids=["CLASS_11_Sci"],
                room_type="ScienceLab",
                weekly_quota=4,
                parallel_group_id="PG_11_SPLIT",
                elective_basket="Senior Split"
            ),
            Event(
                id="EV_MATH",
                subject="Mathematics",
                teacher_ids=["T_VANDNA"],
                section_ids=["CLASS_11_Sci"],
                room_type="Classroom",
                weekly_quota=4,
                parallel_group_id="PG_11_SPLIT",
                elective_basket="Senior Split"
            )
        ]

        report = audit_capacity(self.config, teachers, classes, rooms, events)
        # Check elective stats
        self.assertEqual(report.stats.get("elective_groups_count"), 1)
        elective_audit = report.stats.get("elective_audit", [])
        self.assertEqual(len(elective_audit), 1)
        self.assertEqual(elective_audit[0]["status"], "Feasible")
        self.assertEqual(elective_audit[0]["branches_count"], 2)

    def test_exporter_joint_and_split_integrity(self):
        """Module 4: Verify export_all correctly serializes joint and parallel split properties into JSON, CSV, and SQLite."""
        import tempfile
        import sqlite3
        from engine.exporter import export_all

        grid = TimetableGrid(self.config)
        teachers = {
            "T_RAHUL": Teacher(id="T_RAHUL", name="Rahul"),
            "T_BIO": Teacher(id="T_BIO", name="Anuj"),
            "T_MATH": Teacher(id="T_MATH", name="Vandna")
        }
        classes = {
            "CLASS_12_Comm": ClassSection(id="CLASS_12_Comm", name="Class 12 Commerce"),
            "CLASS_12_Arts": ClassSection(id="CLASS_12_Arts", name="Class 12 Arts"),
            "CLASS_11_Sci": ClassSection(id="CLASS_11_Sci", name="Class 11 Science")
        }

        # 1. Assign Joint class
        a_joint = SlotAssignment(
            event_id="EV_JOINT",
            day="Monday",
            period_index=1,
            subject="Economics",
            teacher_ids=["T_RAHUL"],
            section_ids=["CLASS_12_Comm", "CLASS_12_Arts"],
            is_joint=True,
            joint_label="Class 12 Comm & Arts Economics"
        )
        grid.assign(a_joint)

        # 2. Assign Parallel Split
        pg_id = "PG_11_SCI"
        a_bio = SlotAssignment(
            event_id="EV_BIO",
            day="Tuesday",
            period_index=2,
            subject="Biology",
            teacher_ids=["T_BIO"],
            section_ids=["CLASS_11_Sci"],
            parallel_group_id=pg_id,
            elective_basket="Science Split",
            room_type="ScienceLab"
        )
        a_math = SlotAssignment(
            event_id="EV_MATH",
            day="Tuesday",
            period_index=2,
            subject="Mathematics",
            teacher_ids=["T_MATH"],
            section_ids=["CLASS_11_Sci"],
            parallel_group_id=pg_id,
            elective_basket="Science Split",
            room_type="Classroom"
        )
        grid.assign(a_bio)
        grid.assign(a_math)

        with tempfile.TemporaryDirectory() as tmp_dir:
            exported = export_all(grid, teachers, classes, tmp_dir)
            self.assertIn("timetable.json", exported)
            self.assertIn("timetable_teachers.json", exported)
            self.assertIn("timetable_entries.csv", exported)
            self.assertIn("timetable.sqlite", exported)

            # Check timetable.json
            with open(exported["timetable.json"], "r", encoding="utf-8") as f:
                tt_data = json.load(f)

            # Find 12 Comm Monday P1
            c12_comm = next(c for c in tt_data["classes"] if c["class_name"] == "Class 12 Commerce")
            p1_mon = next(p for p in c12_comm["schedule"]["Monday"] if p["period_index"] == 1)
            self.assertTrue(p1_mon.get("is_joint"))
            self.assertEqual(p1_mon.get("joint_label"), "Class 12 Comm & Arts Economics")

            # Find 11 Sci Tuesday P2 (Parallel split)
            c11_sci = next(c for c in tt_data["classes"] if c["class_name"] == "Class 11 Science")
            p2_tue = next(p for p in c11_sci["schedule"]["Tuesday"] if p["period_index"] == 2)
            self.assertTrue(p2_tue.get("is_parallel_split"))
            self.assertEqual(len(p2_tue.get("parallel_split", [])), 2)
            split_subjs = {s["subject"] for s in p2_tue["parallel_split"]}
            self.assertEqual(split_subjs, {"Biology", "Mathematics"})

            # Check SQLite
            conn = sqlite3.connect(exported["timetable.sqlite"])
            cur = conn.cursor()
            cur.execute("SELECT is_joint, joint_label FROM schedule_entries WHERE class_name = 'Class 12 Commerce' AND period_index = 1")
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], 1)
            self.assertEqual(row[1], "Class 12 Comm & Arts Economics")
            conn.close()


if __name__ == "__main__":
    unittest.main()

