import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.models import SchoolConfig, Teacher, ClassSection, Room, Event, ElectiveBasket
from engine.generator import TimetableGenerator

def run_tests():
    print("Testing Timetable Creation Engine...")

    # Configure small test school
    config = SchoolConfig(
        academic_year="2026-27",
        days=["Monday", "Tuesday", "Wednesday"],
        periods_per_day=4,
        period_definitions=[
            {"period_index": 0, "name": "Assembly", "is_assembly": True},
            {"period_index": 1, "name": "1st Period", "is_lunch": False},
            {"period_index": 2, "name": "2nd Period", "is_lunch": False},
            {"period_index": 3, "name": "3rd Period", "is_lunch": False},
        ]
    )

    teachers = {
        "T1": Teacher(id="T1", name="Vandna", max_weekly_periods=10, max_daily_periods=3),
        "T2": Teacher(id="T2", name="Avdesh", max_weekly_periods=10, max_daily_periods=3),
        "T3": Teacher(id="T3", name="Geetesh", max_weekly_periods=10, max_daily_periods=3, is_specialist=True)
    }

    classes = {
        "C1": ClassSection(id="C1", name="Class 10 Rose", class_teacher="Vandna"),
        "C2": ClassSection(id="C2", name="Class 10 Lily", class_teacher="Avdesh"),
        "C3": ClassSection(id="C3", name="Class 11 Comm", class_teacher="Geetesh")
    }

    rooms = {
        "R1": Room(id="R1", name="Room 101", room_type="Classroom"),
        "R2": Room(id="R2", name="Ground", room_type="Ground")
    }

    events = [
        # Normal single class lessons
        Event(id="E1", subject="Maths", teacher_ids=["T1"], section_ids=["C1"], weekly_quota=2),
        Event(id="E2", subject="Science", teacher_ids=["T2"], section_ids=["C1"], weekly_quota=2),
        Event(id="E3", subject="English", teacher_ids=["T1"], section_ids=["C2"], weekly_quota=2),
        # Clubbed event: T3 teaches Games to C1 and C2 simultaneously
        Event(id="E_CLUB", subject="Games", teacher_ids=["T3"], section_ids=["C1", "C2"], weekly_quota=1, room_type="Ground"),
        # Double period lab for C3
        Event(id="E_LAB", subject="CS Lab", teacher_ids=["T2"], section_ids=["C3"], weekly_quota=1, duration=2)
    ]

    generator = TimetableGenerator(config, teachers, classes, rooms, events)
    audit = generator.pre_audit()
    print("Pre-audit feasibility:", audit.is_feasible)
    assert audit.is_feasible, f"Pre-audit failed: {audit.errors}"

    result = generator.generate()
    print("Solver Result:", result.success, "-", result.message)
    assert result.success, f"Solver failed: {result.message}"

    grid = result.grid
    clashes = grid.detect_all_clashes()
    print(f"Total Clashes Detected: {len(clashes)}")
    assert len(clashes) == 0, f"Clashes found: {clashes}"

    # Verify Clubbed event
    t3_workload = grid.get_teacher_workload("T3")
    print(f"T3 (Geetesh) Physical Periods: {t3_workload['total_weekly_periods']} (expected 1 for clubbed games)")
    assert t3_workload["total_weekly_periods"] == 1, "Clubbed class failed deduplicated contact hours check"

    # Test Infeasibility detection
    print("\nTesting Infeasibility Detection on Impossible Load...")
    bad_events = events + [
        Event(id="E_IMP", subject="Overload", teacher_ids=["T1"], section_ids=["C1"], weekly_quota=100)
    ]
    bad_gen = TimetableGenerator(config, teachers, classes, rooms, bad_events)
    bad_audit = bad_gen.pre_audit()
    print("Bad audit correctly failed:", not bad_audit.is_feasible)
    assert not bad_audit.is_feasible, "Failed to catch impossible arithmetic load in precheck"

    print("\nALL ENGINE TESTS PASSED SUCCESSFULLY! ✅")

if __name__ == "__main__":
    run_tests()
