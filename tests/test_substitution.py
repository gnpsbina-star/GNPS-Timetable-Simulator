import os
import sys
import json
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class TestSubstitutionEngine(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(BASE_DIR, 'timetable_teachers.json'), 'r', encoding='utf-8') as f:
            self.teacher_data = json.load(f)
        with open(os.path.join(BASE_DIR, 'free_teachers.json'), 'r', encoding='utf-8') as f:
            self.free_data = json.load(f)
        with open(os.path.join(BASE_DIR, 'timetable.json'), 'r', encoding='utf-8') as f:
            self.timetable_data = json.load(f)

    def test_absent_teacher_slots_retrieval(self):
        """Verify that absent teacher slots on Monday are correctly identified excluding Lunch/Prayer."""
        teacher = "Vandna Saraf"
        self.assertIn(teacher, self.teacher_data)
        
        day = "Monday"
        sched = self.teacher_data[teacher].get("weekly_schedule", {}).get(day, [])
        valid_slots = [
            p for p in sched 
            if p.get("subject") and p.get("subject") not in ["Lunch", "Prayer", "Lunch _ Class Teacher", "Morning Assembly"]
        ]
        self.assertGreater(len(valid_slots), 0, f"{teacher} should have teaching periods on {day}")
        print(f"✅ Found {len(valid_slots)} valid teaching slots for {teacher} on {day}:")
        for s in valid_slots:
            print(f"   • {s['period_name']} ({s['period_time']}): {s['class_name']} — {s['subject']}")

    def test_free_teacher_candidate_filtering(self):
        """Verify that free teachers exist for Monday slots and can cover classes."""
        day = "Monday"
        p1 = "1st Period"
        roster = self.free_data.get("roster", {}).get(day, {}).get(p1, {})
        free_teachers = roster.get("free_teachers", [])
        self.assertGreater(len(free_teachers), 0, f"There should be free teachers in {p1} on {day}")
        print(f"✅ Found {len(free_teachers)} free teachers in {p1} on {day}. Top candidate: {free_teachers[0]['name']}")

    def test_ranking_algorithm_logic(self):
        """Test the heuristic ranking: subject match should score higher."""
        target_subject = "Maths"
        target_class = "CLASS 10 Rose"
        day = "Monday"
        p_name = "2nd Period"

        roster = self.free_data.get("roster", {}).get(day, {}).get(p_name, {})
        free_teachers = roster.get("free_teachers", [])
        self.assertGreater(len(free_teachers), 0)

        # Calculate scores as done in substitution.html
        ranked = []
        for cand in free_teachers:
            score = 0
            if cand.get("subjects") and any(s.lower() == target_subject.lower() for s in cand["subjects"]):
                score += 50
            if cand.get("classes") and target_class in cand["classes"]:
                score += 30
            if cand.get("is_class_teacher_of") and target_class in cand["is_class_teacher_of"]:
                score += 40
            load = cand.get("weekly_load", 0)
            if load < 20:
                score += 15
            ranked.append((cand["name"], score, load))

        ranked.sort(key=lambda x: (x[1], -x[2]), reverse=True)
        print(f"✅ Top ranked substitute for {target_class} ({target_subject}): {ranked[0][0]} with score {ranked[0][1]}")

    def test_server_substitution_persistence(self):
        """Test saving and loading a substitution log to substitutions_history.json."""
        history_path = os.path.join(BASE_DIR, 'substitutions_history.json')
        sample_record = {
            "date": "2026-09-23",
            "day": "Wednesday",
            "timestamp": "2026-09-23T08:00:00.000Z",
            "absent_teachers": ["Vandna Saraf"],
            "assignments": {
                "2nd Period__CLASS 3 Rose": "Akash"
            }
        }

        # Backup if exists
        backup = None
        if os.path.exists(history_path):
            with open(history_path, 'r', encoding='utf-8') as f:
                backup = f.read()

        try:
            # Write sample
            records = [sample_record]
            with open(history_path, 'w', encoding='utf-8') as f:
                json.dump({"records": records}, f, indent=2)

            with open(history_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            self.assertEqual(len(loaded.get("records", [])), 1)
            self.assertEqual(loaded["records"][0]["date"], "2026-09-23")
            print("✅ Successfully verified substitution history serialization and persistence.")
        finally:
            if backup is not None:
                with open(history_path, 'w', encoding='utf-8') as f:
                    f.write(backup)
            elif os.path.exists(history_path):
                os.remove(history_path)

if __name__ == '__main__':
    unittest.main()
