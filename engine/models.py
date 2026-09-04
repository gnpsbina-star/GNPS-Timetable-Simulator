"""
Data models for school timetable generation, validation, and serialization.
Supports standard lessons, clubbed classes, CBSE elective baskets, and double periods.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple, Optional, Any
import json

@dataclass
class DayPeriod:
    day: str
    period_index: int
    period_name: str
    period_time: str = ""
    is_lunch: bool = False
    is_assembly: bool = False

    @property
    def key(self) -> Tuple[str, int]:
        return (self.day, self.period_index)

@dataclass
class Teacher:
    id: str
    name: str
    max_weekly_periods: int = 34
    max_daily_periods: int = 6
    unavailable_slots: Set[Tuple[str, int]] = field(default_factory=set)
    is_specialist: bool = False
    subjects: List[str] = field(default_factory=list)

    def is_available(self, day: str, period_index: int) -> bool:
        return (day, period_index) not in self.unavailable_slots

@dataclass
class ClassSection:
    id: str
    name: str
    wing: str = "Middle"  # Primary, Middle, Senior
    class_teacher: str = ""
    home_room: str = ""

@dataclass
class Room:
    id: str
    name: str
    room_type: str = "Classroom"  # Classroom, ComputerLab, ScienceLab, Ground, Hall
    capacity: int = 40

@dataclass
class Event:
    """
    An Event is the schedulable unit in the CSP model.
    It can be a standard single-class lesson, a clubbed class (multiple sections, 1 teacher),
    a co-taught lesson (1 section, multiple teachers), or part of an elective basket.
    """
    id: str
    subject: str
    teacher_ids: List[str]
    section_ids: List[str]
    weekly_quota: int = 1
    room_type: str = "Classroom"
    duration: int = 1  # 1 for single period, 2 for double period lab
    basket_id: Optional[str] = None
    is_locked: bool = False
    locked_slots: List[Tuple[str, int]] = field(default_factory=list)

    @property
    def is_clubbed(self) -> bool:
        return len(self.section_ids) > 1

    @property
    def is_co_taught(self) -> bool:
        return len(self.teacher_ids) > 1

@dataclass
class ElectiveBasket:
    """
    CBSE Senior Secondary Elective Basket (Classes 11 & 12).
    Multiple subjects run in parallel across sections in the exact same time slots.
    """
    id: str
    name: str
    section_ids: List[str]
    events: List[Event] = field(default_factory=list)
    weekly_quota: int = 6

@dataclass
class SlotAssignment:
    event_id: str
    day: str
    period_index: int
    subject: str
    teacher_ids: List[str]
    section_ids: List[str]
    room_id: str = ""
    room_type: str = "Classroom"
    is_locked: bool = False
    raw_value: str = ""

@dataclass
class SchoolConfig:
    academic_year: str = "2026-27"
    title: str = "School Time Table"
    days: List[str] = field(default_factory=lambda: [
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"
    ])
    periods_per_day: int = 8
    period_definitions: List[Dict[str, Any]] = field(default_factory=list)
    school_timings: List[Dict[str, str]] = field(default_factory=list)
    fixed_locks: List[Dict[str, Any]] = field(default_factory=list)

class TimetableGrid:
    """
    In-memory representation of a complete or partial timetable grid.
    Provides fast O(1) clash detection, workload analytics, and serialization.
    """
    def __init__(self, config: SchoolConfig):
        self.config = config
        # Map: (section_id, day, period_index) -> SlotAssignment
        self.section_grid: Dict[Tuple[str, str, int], SlotAssignment] = {}
        # Map: (teacher_id, day, period_index) -> List[SlotAssignment]
        self.teacher_grid: Dict[Tuple[str, str, int], List[SlotAssignment]] = {}
        # Map: (room_id, day, period_index) -> List[SlotAssignment]
        self.room_grid: Dict[Tuple[str, str, int], List[SlotAssignment]] = {}

    def assign(self, assignment: SlotAssignment) -> None:
        day = assignment.day
        p_idx = assignment.period_index

        for sec in assignment.section_ids:
            self.section_grid[(sec, day, p_idx)] = assignment

        for t_id in assignment.teacher_ids:
            key = (t_id, day, p_idx)
            if key not in self.teacher_grid:
                self.teacher_grid[key] = []
            self.teacher_grid[key].append(assignment)

        if assignment.room_id:
            r_key = (assignment.room_id, day, p_idx)
            if r_key not in self.room_grid:
                self.room_grid[r_key] = []
            self.room_grid[r_key].append(assignment)

    def remove(self, assignment: SlotAssignment) -> None:
        day = assignment.day
        p_idx = assignment.period_index

        for sec in assignment.section_ids:
            self.section_grid.pop((sec, day, p_idx), None)

        for t_id in assignment.teacher_ids:
            key = (t_id, day, p_idx)
            if key in self.teacher_grid:
                self.teacher_grid[key] = [a for a in self.teacher_grid[key] if a.event_id != assignment.event_id]
                if not self.teacher_grid[key]:
                    del self.teacher_grid[key]

        if assignment.room_id:
            r_key = (assignment.room_id, day, p_idx)
            if r_key in self.room_grid:
                self.room_grid[r_key] = [a for a in self.room_grid[r_key] if a.event_id != assignment.event_id]
                if not self.room_grid[r_key]:
                    del self.room_grid[r_key]

    def check_clash(self, event: Event, day: str, period_index: int) -> List[str]:
        """
        Fast O(1) collision checker for candidate assignment.
        Returns a list of violation messages, or empty list if 100% valid.
        """
        violations = []

        # 1. Section clash (unless elective basket running in parallel)
        for sec in event.section_ids:
            existing = self.section_grid.get((sec, day, period_index))
            if existing:
                # If they share the exact same event (clubbing), it's valid
                if existing.event_id != event.id:
                    violations.append(
                        f"Section '{sec}' already has '{existing.subject}' in {day} Period {period_index}"
                    )

        # 2. Teacher clash (unless authorized clubbed session sharing the same event)
        for t_id in event.teacher_ids:
            existing_list = self.teacher_grid.get((t_id, day, period_index), [])
            for existing in existing_list:
                if existing.event_id != event.id:
                    violations.append(
                        f"Teacher '{t_id}' is already teaching '{existing.subject}' for {existing.section_ids} in {day} Period {period_index}"
                    )

        return violations

    def detect_all_clashes(self) -> List[Dict[str, Any]]:
        """Scans entire grid and reports any teacher, section, or room clash."""
        clashes = []

        # Check teacher double bookings (that are not same event)
        for (t_id, day, p_idx), assignments in self.teacher_grid.items():
            unique_events = {a.event_id for a in assignments}
            if len(unique_events) > 1:
                clashes.append({
                    "type": "TEACHER_CLASH",
                    "teacher": t_id,
                    "day": day,
                    "period_index": p_idx,
                    "conflicts": [
                        {"event_id": a.event_id, "subject": a.subject, "sections": a.section_ids}
                        for a in assignments
                    ]
                })

        # Check room double bookings
        for (r_id, day, p_idx), assignments in self.room_grid.items():
            unique_events = {a.event_id for a in assignments}
            if len(unique_events) > 1:
                clashes.append({
                    "type": "ROOM_CLASH",
                    "room": r_id,
                    "day": day,
                    "period_index": p_idx,
                    "conflicts": [
                        {"event_id": a.event_id, "subject": a.subject, "sections": a.section_ids}
                        for a in assignments
                    ]
                })

        return clashes

    def get_teacher_workload(self, teacher_id: str) -> Dict[str, Any]:
        """Calculates deduplicated contact periods per week and daily distribution."""
        daily_counts: Dict[str, int] = {}
        unique_slots = set()

        for day in self.config.days:
            daily_counts[day] = 0
            for p_idx in range(self.config.periods_per_day):
                assigns = self.teacher_grid.get((teacher_id, day, p_idx), [])
                if assigns:
                    # Deduplicate clubbed classes (counts as 1 physical contact slot)
                    daily_counts[day] += 1
                    unique_slots.add((day, p_idx))

        return {
            "teacher_id": teacher_id,
            "total_weekly_periods": len(unique_slots),
            "daily_distribution": daily_counts
        }
