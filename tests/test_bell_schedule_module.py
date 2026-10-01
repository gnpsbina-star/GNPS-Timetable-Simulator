import unittest
import os
import sys
import json
import copy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.models import (
    SchoolConfig, Teacher, ClassSection, Room, Event,
    parse_time_to_minutes, minutes_to_time_string,
    calculate_end_time, calculate_period_duration, ripple_shift_periods
)
from engine.precheck import audit_capacity

class TestBellScheduleModule(unittest.TestCase):
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

    def test_parse_time_to_minutes_and_formatting(self):
        """Module 2: Verify 12-hour AM/PM time parsing to minutes and string conversion."""
        # AM parsing
        self.assertEqual(parse_time_to_minutes("08:00 AM"), 480)
        self.assertEqual(parse_time_to_minutes("08:30 AM"), 510)
        self.assertEqual(parse_time_to_minutes("11:50 AM"), 710)
        self.assertEqual(parse_time_to_minutes("12:00 PM"), 720) # Noon
        self.assertEqual(parse_time_to_minutes("12:30 PM"), 750)
        self.assertEqual(parse_time_to_minutes("01:10 PM"), 790) # Afternoon
        self.assertEqual(parse_time_to_minutes("01:50 PM"), 830)

        # Formatting back to string
        self.assertEqual(minutes_to_time_string(480), "08:00 AM")
        self.assertEqual(minutes_to_time_string(510), "08:30 AM")
        self.assertEqual(minutes_to_time_string(710), "11:50 AM")
        self.assertEqual(minutes_to_time_string(720), "12:00 PM")
        self.assertEqual(minutes_to_time_string(790), "01:10 PM")

    def test_auto_calculate_end_time_presets(self):
        """Module 2: Verify automatic calculation of period end time from start time and duration."""
        # Standard 40-minute periods
        self.assertEqual(calculate_end_time("08:00 AM", 40), "08:40 AM")
        self.assertEqual(calculate_end_time("11:50 AM", 40), "12:30 PM")
        self.assertEqual(calculate_end_time("12:30 PM", 40), "01:10 PM")
        self.assertEqual(calculate_end_time("01:10 PM", 40), "01:50 PM")

        # Standard 45-minute periods
        self.assertEqual(calculate_end_time("08:30 AM", 45), "09:15 AM")
        self.assertEqual(calculate_end_time("11:05 AM", 45), "11:50 AM")

        # 60-minute Senior Block
        self.assertEqual(calculate_end_time("08:00 AM", 60), "09:00 AM")

        # 20-minute Lunch Break
        self.assertEqual(calculate_end_time("10:30 AM", 20), "10:50 AM")

        # 30-minute Assembly / Prayer
        self.assertEqual(calculate_end_time("08:00 AM", 30), "08:30 AM")

    def test_period_duration_extraction(self):
        """Module 2: Verify duration extraction in minutes from range strings."""
        self.assertEqual(calculate_period_duration("08:00 AM to 08:40 AM"), 40)
        self.assertEqual(calculate_period_duration("08:30 to 9:15"), 45)
        self.assertEqual(calculate_period_duration("11:50 to 12:30"), 40)
        self.assertEqual(calculate_period_duration("12:30 to 1:10"), 40)
        self.assertEqual(calculate_period_duration("1:10 to 1:50"), 40)

    def test_sequential_ripple_shift(self):
        """Module 2: Verify ripple-shifting subsequent periods when an earlier period is lengthened."""
        mock_periods = [
            {"name": "Assembly", "time": "08:00 AM to 08:30 AM"}, # 30m
            {"name": "1st Period", "time": "08:30 AM to 09:15 AM"}, # 45m
            {"name": "2nd Period", "time": "09:15 AM to 09:55 AM"}, # 40m
            {"name": "3rd Period", "time": "09:55 AM to 10:35 AM"}, # 40m
        ]

        # Extend 1st Period from 45 min to 50 min ("08:30 AM to 09:20 AM")
        mock_periods[1]["time"] = "08:30 AM to 09:20 AM"
        
        # Ripple shift from index 2 onwards
        shifted = ripple_shift_periods(mock_periods, start_index=2)

        self.assertEqual(shifted[1]["time"], "08:30 AM to 09:20 AM") # 50m
        self.assertEqual(shifted[2]["time"], "09:20 AM to 10:00 AM") # 40m rippled
        self.assertEqual(shifted[3]["time"], "10:00 AM to 10:40 AM") # 40m rippled

    def test_staggered_lunch_and_breaks_structure(self):
        """Module 2: Verify lunch and assembly non-teaching break designations."""
        lunch_periods = [p for p in self.config.period_definitions if p.get("is_lunch")]
        assembly_periods = [p for p in self.config.period_definitions if p.get("is_assembly")]

        self.assertGreaterEqual(len(lunch_periods), 1, "Must have at least one defined lunch period")
        self.assertGreaterEqual(len(assembly_periods), 1, "Must have morning assembly period defined")

        for lp in lunch_periods:
            self.assertTrue(lp["is_lunch"])
            ws = lp.get("wing_schedule", {}).get("weekday", {})
            # All active wings should treat lunch as non-teaching 'lunch' slot
            for w in ["primary", "middle", "senior"]:
                self.assertEqual(ws.get(w), "lunch")

    def test_saturday_early_dispersal_configuration(self):
        """Module 2: Verify early Saturday dismissal for Primary & Middle wings (no Sat P6-P8)."""
        sat_off_middle = []
        for p in self.config.period_definitions:
            p_idx = p.get("period_index")
            sch = p.get("wing_schedule", {}).get("saturday", {}).get("middle")
            if sch == "off":
                sat_off_middle.append(p_idx)

        # Saturday periods 6, 7, 8 must be OFF for Middle wing early dispersal
        self.assertIn(6, sat_off_middle)
        self.assertIn(7, sat_off_middle)
        self.assertIn(8, sat_off_middle)

    def test_instructional_minutes_and_audit(self):
        """Module 2: Verify weekly instructional hours calculation and audit pass."""
        p_stats = self.config.get_wing_instructional_minutes("Primary")
        m_stats = self.config.get_wing_instructional_minutes("Middle")
        s_stats = self.config.get_wing_instructional_minutes("Senior")

        self.assertEqual(p_stats["active_slots"], 34)
        self.assertGreater(p_stats["total_weekly_minutes"], 1200)

        self.assertEqual(m_stats["active_slots"], 39)
        self.assertGreater(m_stats["total_weekly_minutes"], 1400)

        self.assertEqual(s_stats["active_slots"], 36)
        self.assertGreater(s_stats["total_weekly_minutes"], 1300)

        # Chronological validation
        errors = self.config.validate_bell_schedule()
        self.assertEqual(len(errors), 0, f"Expected 0 bell schedule errors, got: {errors}")

    def test_chronological_error_detection(self):
        """Module 2: Verify precheck flags errors for invalid end times and overlapping slots."""
        bad_config = copy.deepcopy(self.config)
        # Invert start and end time
        bad_config.period_definitions[1]["time"] = "09:15 to 08:30"
        errors = bad_config.validate_bell_schedule()
        self.assertTrue(any("End time must be after start time" in e for e in errors))

        # Test overlap detection in audit_capacity
        teachers = {t["id"]: Teacher(id=t["id"], name=t["name"]) for t in self.raw_data.get("teachers", [])[:2]}
        classes = {c["id"]: ClassSection(id=c["id"], name=c["name"], wing=c.get("wing", "Middle")) for c in self.raw_data.get("classes", [])[:2]}
        
        overlapping_config = copy.deepcopy(self.config)
        # Make period 1 end after period 2 starts (Period 1: 08:30 to 10:00, Period 2: 09:15 to 09:55)
        overlapping_config.period_definitions[1]["time"] = "08:30 AM to 10:00 AM"
        overlapping_config.period_definitions[2]["time"] = "09:15 AM to 09:55 AM"

        report = audit_capacity(overlapping_config, teachers, classes, {}, [])
        self.assertFalse(report.is_feasible)
        self.assertTrue(any("Overlapping periods detected" in err for err in report.errors))

if __name__ == "__main__":
    unittest.main()
