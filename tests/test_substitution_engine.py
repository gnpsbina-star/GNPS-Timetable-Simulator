"""
Unit Tests for Autonomous Substitution Engine (Module 5).
Verifies multi-tier candidate ranking, daily proxy fatigue caps,
clash-free constraint satisfaction, and history persistence.
"""

import os
import tempfile
import unittest
from engine.substitution import SubstitutionManager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class TestSubstitutionManager(unittest.TestCase):
    def setUp(self):
        self.mgr = SubstitutionManager(BASE_DIR)
        self.assertTrue(self.mgr.is_loaded, "SubstitutionManager failed to load timetable and free teachers data.")

    def test_load_data(self):
        """Verify data files are loaded with teachers and roster."""
        self.assertGreater(len(self.mgr.teacher_data), 40)
        self.assertIn("roster", self.mgr.free_data)
        self.assertIn("Monday", self.mgr.free_data["roster"])

    def test_get_affected_slots(self):
        """Verify affected periods extraction ignores breaks like Lunch and Morning Assembly."""
        absent = ["Vandna Saraf"]
        slots = self.mgr.get_affected_slots("Monday", absent)
        self.assertGreater(len(slots), 0, "Vandna Saraf should have valid teaching slots on Monday.")

        # Ensure no break periods leaked into affected slots
        for s in slots:
            self.assertEqual(s["absent_teacher"], "Vandna Saraf")
            self.assertNotIn(s["subject"], ["Lunch", "Morning Assembly", "Prayer", "Recess"])
            self.assertTrue(s["period_name"])
            self.assertTrue(s["class_name"])

    def test_absent_candidates_excluded(self):
        """Verify that faculty marked absent are never recommended as substitutes."""
        absent = ["Vandna Saraf", "Pooja"]
        slots = self.mgr.get_affected_slots("Monday", absent)
        self.assertGreater(len(slots), 0)

        first_slot = slots[0]
        cands = self.mgr.rank_candidates_for_slot(first_slot, "Monday", absent, {})
        cand_names = [c["name"] for c in cands]

        self.assertNotIn("Vandna Saraf", cand_names, "Absent teacher Vandna Saraf must not be recommended as substitute.")
        self.assertNotIn("Pooja", cand_names, "Absent teacher Pooja must not be recommended as substitute.")

    def test_concurrent_slot_clash_prevention(self):
        """Verify that a candidate assigned in P1 cannot be recommended for another class in P1."""
        day = "Monday"
        absent = ["Vandna Saraf"]
        slots = self.mgr.get_affected_slots(day, absent)
        self.assertGreater(len(slots), 1)

        slot1 = slots[0]
        p_name = slot1["period_name"]

        # Find another slot in the same period or mock one
        mock_slot2 = {
            "key": f"{p_name}__MOCK_CLASS",
            "period_name": p_name,
            "period_index": slot1["period_index"],
            "class_name": "MOCK_CLASS",
            "subject": "General",
            "absent_teacher": "Vandna Saraf"
        }

        cands = self.mgr.rank_candidates_for_slot(slot1, day, absent, {})
        self.assertGreater(len(cands), 0)
        chosen_cand = cands[0]["name"]

        # Assign chosen_cand to slot1
        current_assigns = {slot1["key"]: chosen_cand}

        # Check candidates for mock_slot2 in the same period
        cands_slot2 = self.mgr.rank_candidates_for_slot(mock_slot2, day, absent, current_assigns)
        cand_names_slot2 = [c["name"] for c in cands_slot2]

        self.assertNotIn(chosen_cand, cand_names_slot2,
                         f"{chosen_cand} already assigned to {slot1['key']} and cannot take concurrent class.")

    def test_subject_specialist_scoring(self):
        """Verify that a subject specialist receives +50 bonus and outranks non-specialists."""
        day = "Monday"
        # Create a mock slot requiring 'Math'
        mock_slot = {
            "key": "2nd Period__CLASS 10 Rose",
            "period_name": "2nd Period",
            "period_index": 2,
            "class_name": "CLASS 10 Rose",
            "subject": "Math",
            "absent_teacher": "TestTeacher"
        }

        cands = self.mgr.rank_candidates_for_slot(mock_slot, day, ["TestTeacher"], {})
        self.assertGreater(len(cands), 0)

        # Find a candidate who teaches Math vs one who doesn't
        specialist = next((c for c in cands if any("math" in s.lower() for s in c["subjects"])), None)
        non_specialist = next((c for c in cands if not any("math" in s.lower() for s in c["subjects"])), None)

        if specialist and non_specialist:
            self.assertIn("Subject Match", specialist["reasons"])
            self.assertGreaterEqual(specialist["score"], non_specialist["score"])

    def test_class_teacher_scoring(self):
        """Verify that the homeroom Class Teacher of the affected section receives +40 bonus."""
        day = "Monday"
        # Find a teacher who is a class teacher of some section
        ct_teacher = None
        target_section = None
        for t_name, t_info in self.mgr.teacher_data.items():
            ct_list = t_info.get("is_class_teacher_of", [])
            if ct_list:
                ct_teacher = t_name
                target_section = ct_list[0]
                break

        self.assertIsNotNone(ct_teacher)
        mock_slot = {
            "key": f"1st Period__{target_section}",
            "period_name": "1st Period",
            "period_index": 1,
            "class_name": target_section,
            "subject": "English",
            "absent_teacher": "Dummy"
        }

        # Check if ct_teacher is free in 1st Period
        day_roster = self.mgr.free_data.get("roster", {}).get(day, {}).get("1st Period", {})
        free_names = [c["name"] for c in day_roster.get("free_teachers", [])]

        if ct_teacher in free_names:
            cands = self.mgr.rank_candidates_for_slot(mock_slot, day, ["Dummy"], {})
            ct_cand = next((c for c in cands if c["name"] == ct_teacher), None)
            self.assertIsNotNone(ct_cand)
            self.assertIn("Class Teacher", ct_cand["reasons"])
            self.assertTrue(ct_cand["is_class_teacher"])

    def test_daily_proxy_cap_enforcement(self):
        """Verify that candidates reaching max_proxies_per_day are excluded from further slots."""
        day = "Monday"
        absent = ["Vandna Saraf"]
        slots = self.mgr.get_affected_slots(day, absent)
        self.assertGreater(len(slots), 0)

        first_slot = slots[0]
        cands = self.mgr.rank_candidates_for_slot(first_slot, day, absent, {}, max_proxies_per_day=2)
        self.assertGreater(len(cands), 0)

        target_sub = cands[0]["name"]
        # Simulate target_sub having already completed 2 proxies in other periods
        mock_assignments = {
            "3rd Period__Class A": target_sub,
            "4th Period__Class B": target_sub
        }

        # Candidate now at cap (2 proxies)
        cands_at_cap = self.mgr.rank_candidates_for_slot(
            first_slot, day, absent, mock_assignments, max_proxies_per_day=2
        )
        cand_names_at_cap = [c["name"] for c in cands_at_cap]
        self.assertNotIn(target_sub, cand_names_at_cap,
                         f"{target_sub} has reached max daily proxy limit of 2 and must be excluded.")

    def test_global_auto_assign_clash_free(self):
        """Verify that auto_assign produces 100% collision-free assignments."""
        day = "Monday"
        absent = ["Vandna Saraf", "Pooja"]
        result = self.mgr.auto_assign(day, absent, max_proxies_per_day=2)

        self.assertIn("assignments", result)
        self.assertIn("total_slots", result)
        self.assertGreater(result["total_slots"], 0)

        # Audit collision freedom: No teacher assigned to 2 different classes in the same period
        period_teacher_map = {}
        for s_key, sub_name in result["assignments"].items():
            p_name = s_key.split("__")[0]
            if p_name not in period_teacher_map:
                period_teacher_map[p_name] = set()
            self.assertNotIn(sub_name, period_teacher_map[p_name],
                             f"Collision detected! {sub_name} assigned multiple times in {p_name}.")
            period_teacher_map[p_name].add(sub_name)

        # Audit proxy count limits
        for sub_name, count in result["proxy_counts"].items():
            self.assertLessEqual(count, 2, f"{sub_name} assigned {count} proxies, exceeding max cap of 2.")

    def test_history_persistence_and_retrieval(self):
        """Verify saving and loading substitution arrangements from history file."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_history = tf.name

        try:
            record = {
                "date": "2026-09-23",
                "day": "Wednesday",
                "timestamp": "2026-09-23T08:00:00.000Z",
                "absent_teachers": ["Vandna Saraf", "Pooja"],
                "assignments": {
                    "1st Period__CLASS 3 Rose": "Akash",
                    "2nd Period__CLASS 4 Lily": "Rajpal"
                }
            }

            saved = self.mgr.save_history(record, temp_history)
            self.assertTrue(saved)

            history = self.mgr.get_history(temp_history)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["date"], "2026-09-23")
            self.assertEqual(history[0]["assignments"]["1st Period__CLASS 3 Rose"], "Akash")
        finally:
            if os.path.exists(temp_history):
                os.remove(temp_history)

    def test_api_data_contracts(self):
        """Verify the data contracts expected by the REST API handlers."""
        # 1. Affected slots contract
        slots = self.mgr.get_affected_slots("Monday", ["Vandna Saraf"])
        self.assertIsInstance(slots, list)
        if slots:
            self.assertIn("key", slots[0])
            self.assertIn("period_name", slots[0])
            self.assertIn("class_name", slots[0])
            self.assertIn("subject", slots[0])

        # 2. Recommend contract
        if slots:
            cands = self.mgr.rank_candidates_for_slot(slots[0], "Monday", ["Vandna Saraf"], {})
            self.assertIsInstance(cands, list)
            if cands:
                self.assertIn("name", cands[0])
                self.assertIn("score", cands[0])
                self.assertIn("reasons", cands[0])

        # 3. Auto-assign contract
        res = self.mgr.auto_assign("Monday", ["Vandna Saraf"], max_proxies_per_day=2)
        self.assertIsInstance(res, dict)
        self.assertIn("success", res)
        self.assertIn("assignments", res)
        self.assertIn("proxy_counts", res)

    def test_class_teacher_duty_periods_inclusion(self):
        """Verify that absent Class Teachers generate Morning Assembly and Lunch duty coverage slots."""
        # Swati Napit is Class Teacher of CLASS 1 Rose
        slots = self.mgr.get_affected_slots("Monday", ["Swati Napit"])
        slot_names = [s["period_name"] for s in slots]
        slot_subjects = [s["subject"] for s in slots]

        self.assertIn("Morning Assembly", slot_names, "Morning Assembly must be generated for absent Class Teacher")
        self.assertIn("Lunch", slot_names, "Lunch must be generated for absent Class Teacher")
        self.assertIn("Duty: Morning Assembly", slot_subjects)
        self.assertIn("Duty: Lunch Break", slot_subjects)

        # Duty slots must specifically be for her homeroom section
        assembly_slot = next(s for s in slots if s["period_name"] == "Morning Assembly")
        self.assertEqual(assembly_slot["class_name"], "CLASS 1 Rose")
        self.assertTrue(assembly_slot["is_duty"])

    def test_management_faculty_excluded(self):
        """Verify that Sonakshi and Shailandra Kurmi are strictly excluded from substitutions."""
        # Test candidate ranking for regular academic slot
        mock_slot = {
            "key": "1st Period__CLASS 3 Rose",
            "period_name": "1st Period",
            "period_index": 1,
            "class_name": "CLASS 3 Rose",
            "subject": "Maths",
            "absent_teacher": "TestTeacher"
        }
        cands = self.mgr.rank_candidates_for_slot(mock_slot, "Monday", ["TestTeacher"], {})
        cand_names = [c["name"] for c in cands]

        self.assertNotIn("Sonakshi", cand_names, "Sonakshi looks after management and must never be recommended.")
        self.assertNotIn("Shailandra", cand_names, "Shailandra looks after management and must never be recommended.")

        # Test in auto_assign
        result = self.mgr.auto_assign("Monday", ["Swati Napit", "Anjali Jain"])
        assigned_subs = set(result["assignments"].values())
        self.assertNotIn("Sonakshi", assigned_subs, "Sonakshi must never be assigned in auto_assign.")
        self.assertNotIn("Shailandra", assigned_subs, "Shailandra must never be assigned in auto_assign.")

    def test_substitution_report_sorted_by_substitute_name(self):
        """Verify that generate_substitution_report produces rows sorted alphabetically by substitute teacher name."""
        absent = ["Vandna Saraf"]
        slots = self.mgr.get_affected_slots("Monday", absent)
        self.assertGreater(len(slots), 2)

        # Mock assignments with non-alphabetical substitute names
        mock_assignments = {
            slots[0]["key"]: "Zeenat",
            slots[1]["key"]: "Amit Saxena",
        }
        if len(slots) > 2:
            mock_assignments[slots[2]["key"]] = "Bharti"

        report = self.mgr.generate_substitution_report("Monday", absent, mock_assignments, "2026-09-24")
        self.assertEqual(len(report), len(mock_assignments))

        # Check date format converted to DD/MM/YYYY
        self.assertEqual(report[0]["date"], "24/09/2026")

        # Verify sorted alphabetically by substitute_teacher name
        subs_in_report = [r["substitute_teacher"] for r in report]
        expected_sorted = sorted(subs_in_report, key=lambda s: s.lower())
        self.assertEqual(subs_in_report, expected_sorted)

        # Verify all required columns exist in each row
        required_cols = {"date", "substitute_teacher", "period", "subject", "absent_teacher", "signature"}
        for r in report:
            self.assertTrue(required_cols.issubset(set(r.keys())))
            self.assertEqual(r["absent_teacher"], "Vandna Saraf")

    def test_blackout_slot_candidate_excluded(self):
        """Verify that faculty with marked Blackout slots are strictly excluded from candidates."""
        # Divya Upadhyay has unavailable_slots on Monday period 4 (Lunch) and period 5 (4th Period, index 5)
        # Create a slot for Monday 4th Period (index 5)
        mock_slot = {
            "key": "4th Period__CLASS 8 Rose",
            "period_name": "4th Period",
            "period_index": 5,
            "class_name": "CLASS 8 Rose",
            "subject": "General",
            "absent_teacher": "TestTeacher"
        }
        cands = self.mgr.rank_candidates_for_slot(mock_slot, "Monday", ["TestTeacher"], {})
        cand_names = [c["name"] for c in cands]

        self.assertNotIn("Divya Upadhyay", cand_names,
                         "Divya Upadhyay has Monday P5 blackout and must not be recommended.")

        # Test dynamic blackout addition
        self.mgr.blackout_slots["anjali jain"] = {("Monday", 8)}
        slot_p8 = {
            "key": "7th Period__CLASS 5 Rose",
            "period_name": "7th Period",
            "period_index": 8,
            "class_name": "CLASS 5 Rose",
            "subject": "General",
            "absent_teacher": "TestTeacher"
        }
        cands_p8 = self.mgr.rank_candidates_for_slot(slot_p8, "Monday", ["TestTeacher"], {})
        cand_names_p8 = [c["name"] for c in cands_p8]
        self.assertNotIn("Anjali Jain", cand_names_p8,
                         "Anjali Jain has marked Monday P8 blackout and must not be recommended.")

    def test_auto_substitution_never_assigns_blackout_teacher(self):
        """Verify that auto_assign never assigns a faculty member during their blackout slot."""
        # Force a blackout on a candidate for a specific period
        self.mgr.blackout_slots["vandna saraf"] = {("Tuesday", 1)}
        result = self.mgr.auto_assign("Tuesday", ["Anjali Jain", "Swati Napit"])
        assignments = result.get("assignments", {})

        for s_key, sub_name in assignments.items():
            if s_key.startswith("1st Period__") or "__1st Period__" in s_key:
                self.assertNotEqual(sub_name, "Vandna Saraf",
                                    "Vandna Saraf has Tuesday P1 blackout and must never be auto-assigned.")

    def test_sync_free_teachers_excludes_blackout(self):
        """Verify that sync_free_teachers excludes blackout teachers from free lists."""
        from engine.substitution import sync_free_teachers
        free_data = sync_free_teachers(BASE_DIR)
        
        # Check Divya Upadhyay on Monday 4th Period (period_index 5)
        monday_p4_free = free_data["slot_availability"]["Monday"].get("4th Period", [])
        self.assertNotIn("Divya Upadhyay", monday_p4_free,
                         "Divya Upadhyay must not be in Monday 4th Period free list due to blackout slot.")

    def test_class_teachers_not_free_during_assembly_and_lunch(self):
        """Verify that Class Teachers pay duty during Morning Assembly and Lunch, and are not considered free."""
        from engine.substitution import sync_free_teachers
        free_data = sync_free_teachers(BASE_DIR)

        # Swati Napit (CT of CLASS 1 Rose) and Anjali Jain (CT of CLASS 1 Marigold) must NOT be free
        for slot in ["Morning Assembly", "Lunch"]:
            free_in_slot = free_data["slot_availability"]["Monday"].get(slot, [])
            self.assertNotIn("Swati Napit", free_in_slot, f"Swati Napit is a Class Teacher and must pay {slot} duty (not free)")
            self.assertNotIn("Anjali Jain", free_in_slot, f"Anjali Jain is a Class Teacher and must pay {slot} duty (not free)")
            
            # Non-class teacher (specialist Pradeep) SHOULD be free
            self.assertIn("Pradeep", free_in_slot, f"Pradeep is a specialist with no homeroom and should be free for {slot}")

    def test_class_teachers_never_assigned_to_substitute_assembly_or_lunch(self):
        """Verify that Class Teachers are never assigned to cover Morning Assembly or Lunch duties for other classes."""
        # Swati Napit is absent, so her class needs Morning Assembly & Lunch duty coverage
        absent = ["Swati Napit"]
        slots = self.mgr.get_affected_slots("Monday", absent)
        duty_slots = [s for s in slots if s["is_duty"]]
        self.assertGreater(len(duty_slots), 0, "Must have duty slots for absent Class Teacher")

        for d_slot in duty_slots:
            cands = self.mgr.rank_candidates_for_slot(d_slot, "Monday", absent, {})
            cand_names = [c["name"] for c in cands]
            
            # Verify no candidate in cand_names is another Class Teacher
            for cand_name in cand_names:
                t_info = self.mgr.teacher_data.get(cand_name, {})
                ct_of = t_info.get("is_class_teacher_of", [])
                self.assertEqual(len(ct_of), 0,
                                 f"Candidate {cand_name} is Class Teacher of {ct_of} and must not substitute for {d_slot['period_name']} duty")

    def test_wing_compatibility_scoring(self):
        """Verify that wing alignment rewards same-wing and penalizes extreme cross-wing pairings."""
        # Class 4 Marigold is Primary; Prashant is Senior-only; Swati Napit is Primary
        mock_primary_slot = {
            "key": "2nd Period__CLASS 4 Marigold",
            "period_name": "2nd Period",
            "period_index": 2,
            "class_name": "CLASS 4 Marigold",
            "subject": "General",
            "absent_teacher": "TestTeacher"
        }
        score_senior, _ = self.mgr.get_wing_compatibility_score("CLASS 4 Marigold", "Prashant")
        self.assertEqual(score_senior, -50, "Senior teacher must get -50 penalty for Primary class")

        score_primary, reason = self.mgr.get_wing_compatibility_score("CLASS 4 Marigold", "Swati Napit")
        self.assertEqual(score_primary, 30, "Primary teacher must get +30 bonus for Primary class")
        self.assertEqual(reason, "Same Wing")

    def test_subject_family_matching(self):
        """Verify that related subject families (e.g. Science for EVS) receive Related Subject bonuses."""
        from engine.substitution import match_subject
        score, reason = match_subject("EVS", ["Science", "Maths"])
        self.assertEqual(score, 70)
        self.assertEqual(reason, "Related Subject")

        score, reason = match_subject("Physics", ["Physics"])
        self.assertEqual(score, 120)
        self.assertEqual(reason, "Subject Match")

    def test_duty_does_not_consume_teaching_proxy_cap(self):
        """Verify that an assigned homeroom duty does not count against the teaching proxy limit."""
        # A candidate with 1 morning assembly duty can still take a regular teaching period
        mock_slot = {
            "key": "1st Period__CLASS 3 Rose",
            "period_name": "1st Period",
            "period_index": 1,
            "class_name": "CLASS 3 Rose",
            "subject": "Maths",
            "absent_teacher": "Vandna Saraf",
            "is_duty": False
        }
        # Simulate Swati Napit having 1 duty assignment
        assignments = {"Morning Assembly__CLASS 1 Rose": "Swati Napit"}
        cands = self.mgr.rank_candidates_for_slot(mock_slot, "Monday", ["Vandna Saraf"], assignments, max_proxies_per_day=1)
        cand_names = [c["name"] for c in cands]
        self.assertIn("Swati Napit", cand_names, "Duty assignment must not consume teaching proxy limit of 1")

    def test_flexible_auto_expansion_solves_heavy_absence(self):
        """Verify that flexible 2-pass auto-assign successfully resolves heavy absences."""
        teachers = ["Anjali Jain", "Anjali Nalvanshi", "Anubha", "Anuj Jain", "Anuraj"]
        res = self.mgr.auto_assign("Monday", teachers, max_proxies_per_day=2)
        self.assertTrue(res["success"], f"Failed to solve with unassigned: {res.get('unassigned_slots')}")
        self.assertEqual(res["unassigned_count"], 0)
        self.assertEqual(res["total_slots"], res["assigned_count"])

if __name__ == '__main__':
    unittest.main()
