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

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Teacher":
        unavail = set()
        for slot in data.get("unavailable_slots", []):
            if isinstance(slot, (list, tuple)) and len(slot) == 2:
                unavail.add((slot[0], slot[1]))
            elif isinstance(slot, dict):
                unavail.add((slot.get("day", ""), slot.get("period_index", 0)))
        return cls(
            id=data.get("id", data.get("name", "")),
            name=data.get("name", ""),
            max_weekly_periods=data.get("max_weekly_periods", 34),
            max_daily_periods=data.get("max_daily_periods", 6),
            unavailable_slots=unavail,
            is_specialist=data.get("is_specialist", False),
            subjects=data.get("subjects", [])
        )

    def is_available(self, day: str, period_index: int) -> bool:
        return (day, period_index) not in self.unavailable_slots

@dataclass
class ClassSection:
    id: str
    name: str
    wing: str = "Middle"  # Primary, Middle, Senior
    class_teacher: str = ""
    home_room: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClassSection":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            wing=data.get("wing", "Middle"),
            class_teacher=data.get("class_teacher", ""),
            home_room=data.get("home_room", "")
        )

@dataclass
class Room:
    id: str
    name: str
    room_type: str = "Classroom"  # Classroom, ComputerLab, ScienceLab, Ground, ArtStudio, Hall
    capacity: int = 40
    max_concurrent_classes: int = 1
    building: str = "Main Block"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Room":
        r_type = data.get("room_type", "Classroom")
        # Configurable concurrent class defaults per room type
        CONCURRENT_DEFAULTS = {"Ground": 2, "Hall": 3}
        default_concurrent = CONCURRENT_DEFAULTS.get(r_type, 1)
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            room_type=r_type,
            capacity=data.get("capacity", 40),
            max_concurrent_classes=data.get("max_concurrent_classes", default_concurrent),
            building=data.get("building", "Main Block")
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "room_type": self.room_type,
            "capacity": self.capacity,
            "max_concurrent_classes": self.max_concurrent_classes,
            "building": self.building
        }

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
    is_joint: bool = False
    joint_label: Optional[str] = None
    parallel_group_id: Optional[str] = None  # Links events that must be co-scheduled in the same slot
    elective_basket: Optional[str] = None   # e.g. "Senior Science Elective Stream"

    @property
    def is_clubbed(self) -> bool:
        return len(self.section_ids) > 1

    @property
    def is_co_taught(self) -> bool:
        return len(self.teacher_ids) > 1

    @property
    def is_parallel_split(self) -> bool:
        return bool(self.parallel_group_id)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        locked_raw = data.get("locked_slots", [])
        locked_slots = [tuple(s) for s in locked_raw] if locked_raw else []
        sec_ids = data.get("section_ids", [])
        is_joint = data.get("is_joint", len(sec_ids) > 1)
        return cls(
            id=data.get("id", ""),
            subject=data.get("subject", ""),
            teacher_ids=data.get("teacher_ids", []),
            section_ids=sec_ids,
            weekly_quota=data.get("weekly_quota", 1),
            room_type=data.get("room_type", "Classroom"),
            duration=data.get("duration", 1),
            basket_id=data.get("basket_id"),
            is_locked=data.get("is_locked", False),
            locked_slots=locked_slots,
            is_joint=is_joint,
            joint_label=data.get("joint_label"),
            parallel_group_id=data.get("parallel_group_id"),
            elective_basket=data.get("elective_basket")
        )

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "id": self.id,
            "subject": self.subject,
            "teacher_ids": self.teacher_ids,
            "section_ids": self.section_ids,
            "weekly_quota": self.weekly_quota,
            "room_type": self.room_type,
            "duration": self.duration,
            "is_locked": self.is_locked,
            "locked_slots": [list(s) for s in self.locked_slots]
        }
        if self.basket_id:
            d["basket_id"] = self.basket_id
        if self.is_joint:
            d["is_joint"] = True
        if self.joint_label:
            d["joint_label"] = self.joint_label
        if self.parallel_group_id:
            d["parallel_group_id"] = self.parallel_group_id
        if self.elective_basket:
            d["elective_basket"] = self.elective_basket
        return d

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
    is_joint: bool = False
    joint_label: Optional[str] = None
    parallel_group_id: Optional[str] = None
    elective_basket: Optional[str] = None

@dataclass
class Subject:
    id: str
    name: str
    code: str
    category: str = "theory"  # theory, practical, activity, language
    room_type: str = "Classroom"
    default_quota: int = 5
    is_double_period: bool = False
    duration_type: str = "single"  # single, double

# =====================================================================
# TIME CALCULATION & BELL SCHEDULE UTILITIES (MODULE 2)
# =====================================================================
import re

def parse_time_to_minutes(time_str: str) -> Optional[int]:
    """Parses standard 12-hour AM/PM time (e.g. '08:00 AM', '1:10 PM', '8:30') to minutes from midnight."""
    if not time_str:
        return None
    time_str = time_str.strip()
    match = re.match(r"^(\d{1,2}):(\d{2})\s*(AM|PM)?$", time_str, re.IGNORECASE)
    if not match:
        return None
    hours = int(match.group(1))
    mins = int(match.group(2))
    meridiem = match.group(3).upper() if match.group(3) else None

    if meridiem == "PM" and hours < 12:
        hours += 12
    elif meridiem == "AM" and hours == 12:
        hours = 0
    elif not meridiem:
        if 1 <= hours <= 6:
            hours += 12

    return hours * 60 + mins

def minutes_to_time_string(total_minutes: int) -> str:
    """Converts minutes from midnight to formatted 'HH:MM AM/PM' string."""
    total_minutes = (total_minutes + 24 * 60) % (24 * 60)
    hours = total_minutes // 60
    mins = total_minutes % 60
    meridiem = "PM" if hours >= 12 else "AM"
    display_hour = hours % 12
    if display_hour == 0:
        display_hour = 12
    return f"{display_hour:02d}:{mins:02d} {meridiem}"

def calculate_end_time(start_time_str: str, duration_minutes: int) -> str:
    """Auto-calculates period end time given start time string and duration in minutes."""
    start_mins = parse_time_to_minutes(start_time_str)
    if start_mins is None:
        return ""
    return minutes_to_time_string(start_mins + duration_minutes)

def calculate_period_duration(time_range_str: str) -> Optional[int]:
    """Calculates duration in minutes from a time range string like '08:00 AM to 08:40 AM'."""
    if not time_range_str or "to" not in time_range_str:
        return None
    parts = time_range_str.split("to")
    start_mins = parse_time_to_minutes(parts[0].strip())
    end_mins = parse_time_to_minutes(parts[1].strip())
    if start_mins is None or end_mins is None:
        return None
    diff = end_mins - start_mins
    if diff < 0:
        diff += 24 * 60
    return diff

def ripple_shift_periods(periods: List[Dict[str, Any]], start_index: int = 0) -> List[Dict[str, Any]]:
    """
    Sequentially chains periods so each subsequent period starts exactly
    when the previous period ends, maintaining each period's duration.
    """
    for i in range(max(1, start_index), len(periods)):
        prev_p = periods[i - 1]
        curr_p = periods[i]
        
        prev_time = prev_p.get("time", "")
        if "to" not in prev_time:
            continue
        prev_end_str = prev_time.split("to")[1].strip()
        
        curr_time = curr_p.get("time", "")
        curr_dur = calculate_period_duration(curr_time) or 40
        
        new_start = prev_end_str
        new_end = calculate_end_time(new_start, curr_dur)
        curr_p["time"] = f"{new_start} to {new_end}"
        curr_p["raw_header"] = f"{curr_p.get('name', f'Period {i}')} {curr_p['time']}"
        
    return periods

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
    wing_bell_schedules: Dict[str, Any] = field(default_factory=dict)
    fixed_locks: List[Dict[str, Any]] = field(default_factory=list)
    enforce_class_teacher_p1: bool = True

    def get_period_duration_minutes(self, period_index: int) -> int:
        for p in self.period_definitions:
            if p.get("period_index") == period_index:
                dur = calculate_period_duration(p.get("time", ""))
                return dur if dur else 40
        return 40

    def get_wing_instructional_minutes(self, wing_name: str) -> Dict[str, Any]:
        w = (wing_name or "").lower().replace(" ", "").replace("-", "")
        wing_key = "middle"
        if "play" in w: wing_key = "playgroup"
        elif "pre" in w or "nur" in w or "lkg" in w or "ukg" in w: wing_key = "pre_primary"
        elif "prim" in w or any(str(i) in w for i in range(1, 6)): wing_key = "primary"
        elif "mid" in w or any(str(i) in w for i in range(6, 9)): wing_key = "middle"
        elif "sen" in w or any(str(i) in w for i in [9, 10, 11, 12]): wing_key = "senior"

        daily_breakdown = {}
        total_minutes = 0
        active_slots = 0

        for d in self.days:
            day_key = "saturday" if d.lower() == "saturday" else "weekday"
            day_mins = 0
            for p in self.period_definitions:
                if p.get("is_lunch") or p.get("is_assembly"):
                    continue
                sch = p.get("wing_schedule", {}).get(day_key, {}).get(wing_key, "study")
                if sch == "study":
                    dur = calculate_period_duration(p.get("time", "")) or 40
                    day_mins += dur
                    active_slots += 1
            daily_breakdown[d] = day_mins
            total_minutes += day_mins

        return {
            "wing": wing_name,
            "wing_key": wing_key,
            "active_slots": active_slots,
            "total_weekly_minutes": total_minutes,
            "total_weekly_hours": round(total_minutes / 60.0, 2),
            "daily_breakdown": daily_breakdown
        }

    def validate_bell_schedule(self) -> List[str]:
        errors = []
        for i, p in enumerate(self.period_definitions):
            p_name = p.get("name", f"Period #{i}")
            p_time = p.get("time", "")
            if not p_time or "to" not in p_time:
                continue
            parts = p_time.split("to")
            s_mins = parse_time_to_minutes(parts[0].strip())
            e_mins = parse_time_to_minutes(parts[1].strip())
            if s_mins is None or e_mins is None:
                errors.append(f"{p_name}: Invalid time format '{p_time}'")
            elif e_mins <= s_mins:
                errors.append(f"{p_name}: End time must be after start time ({p_time})")
        return errors

class TimetableGrid:
    """
    In-memory representation of a complete or partial timetable grid.
    Provides fast O(1) clash detection, workload analytics, and serialization.
    """
    def __init__(self, config: SchoolConfig):
        self.config = config
        # Primary Map: (section_id, day, period_index) -> SlotAssignment (for fast backward compatibility)
        self.section_grid: Dict[Tuple[str, str, int], SlotAssignment] = {}
        # Multi-Assignment Map: (section_id, day, period_index) -> List[SlotAssignment] (for parallel splits)
        self.section_grid_all: Dict[Tuple[str, str, int], List[SlotAssignment]] = {}
        # Map: (teacher_id, day, period_index) -> List[SlotAssignment]
        self.teacher_grid: Dict[Tuple[str, str, int], List[SlotAssignment]] = {}
        # Map: (room_id, day, period_index) -> List[SlotAssignment]
        self.room_grid: Dict[Tuple[str, str, int], List[SlotAssignment]] = {}
        # Map: (room_type, day, period_index) -> List[SlotAssignment]
        self.room_type_grid: Dict[Tuple[str, str, int], List[SlotAssignment]] = {}

    def assign(self, assignment: SlotAssignment) -> None:
        day = assignment.day
        p_idx = assignment.period_index

        for sec in assignment.section_ids:
            sec_key = (sec, day, p_idx)
            self.section_grid[sec_key] = assignment
            if sec_key not in self.section_grid_all:
                self.section_grid_all[sec_key] = []
            self.section_grid_all[sec_key].append(assignment)

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

        if assignment.room_type and assignment.room_type != "Classroom":
            rt_key = (assignment.room_type, day, p_idx)
            if rt_key not in self.room_type_grid:
                self.room_type_grid[rt_key] = []
            self.room_type_grid[rt_key].append(assignment)

    def remove(self, assignment: SlotAssignment) -> None:
        day = assignment.day
        p_idx = assignment.period_index

        for sec in assignment.section_ids:
            sec_key = (sec, day, p_idx)
            if sec_key in self.section_grid_all:
                self.section_grid_all[sec_key] = [
                    a for a in self.section_grid_all[sec_key] if a.event_id != assignment.event_id
                ]
                if self.section_grid_all[sec_key]:
                    self.section_grid[sec_key] = self.section_grid_all[sec_key][-1]
                else:
                    del self.section_grid_all[sec_key]
                    self.section_grid.pop(sec_key, None)
            else:
                self.section_grid.pop(sec_key, None)

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

        if assignment.room_type and assignment.room_type != "Classroom":
            rt_key = (assignment.room_type, day, p_idx)
            if rt_key in self.room_type_grid:
                self.room_type_grid[rt_key] = [a for a in self.room_type_grid[rt_key] if a.event_id != assignment.event_id]
                if not self.room_type_grid[rt_key]:
                    del self.room_type_grid[rt_key]

    def check_clash(
        self,
        event: Event,
        day: str,
        period_index: int,
        rooms_by_type: Optional[Dict[str, List[Room]]] = None
    ) -> List[str]:
        """
        Fast O(1) collision checker for candidate assignment.
        Returns a list of violation messages, or empty list if 100% valid.
        """
        violations = []

        # 1. Section clash (unless elective basket running in parallel)
        for sec in event.section_ids:
            existing_list = self.section_grid_all.get((sec, day, period_index), [])
            for existing in existing_list:
                # If they share the exact same event (clubbing), it's valid
                if existing.event_id == event.id:
                    continue
                # If both events belong to the same parallel elective group, they run simultaneously
                if event.parallel_group_id and existing.parallel_group_id == event.parallel_group_id:
                    continue
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

        # 3. Room / Facility capacity clash (for specialized facilities like ScienceLab, ComputerLab, Ground)
        if event.room_type and event.room_type != "Classroom":
            existing_room_bookings = self.room_type_grid.get((event.room_type, day, period_index), [])
            unique_bookings = {a.event_id for a in existing_room_bookings if a.event_id != event.id}

            # Determine maximum concurrent capacity
            max_concurrent = 1
            if rooms_by_type and event.room_type in rooms_by_type:
                max_concurrent = sum(r.max_concurrent_classes for r in rooms_by_type[event.room_type])
            elif event.room_type == "Ground":
                max_concurrent = 2

            if len(unique_bookings) >= max_concurrent:
                violations.append(
                    f"Facility '{event.room_type}' is at maximum concurrent capacity ({max_concurrent} classes) in {day} Period {period_index}"
                )

        return violations

    def detect_all_clashes(self, rooms_by_type: Optional[Dict[str, List[Room]]] = None) -> List[Dict[str, Any]]:
        """Scans entire grid and reports any teacher, section, or room clash."""
        clashes = []

        # Check section double bookings (that are not part of same parallel group)
        for (sec, day, p_idx), assignments in self.section_grid_all.items():
            unique_events = {a.event_id for a in assignments}
            if len(unique_events) > 1:
                pg_ids = {a.parallel_group_id for a in assignments if a.parallel_group_id}
                if len(pg_ids) == 1 and len(assignments) == len([a for a in assignments if a.parallel_group_id]):
                    pass  # Valid parallel elective split
                else:
                    clashes.append({
                        "type": "SECTION_CLASH",
                        "section": sec,
                        "day": day,
                        "period_index": p_idx,
                        "conflicts": [
                            {"event_id": a.event_id, "subject": a.subject, "teacher_ids": a.teacher_ids}
                            for a in assignments
                        ]
                    })

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

        # Check specialized room capacity over-bookings
        for (r_type, day, p_idx), assignments in self.room_type_grid.items():
            unique_events = {a.event_id for a in assignments}
            max_concurrent = 1
            if rooms_by_type and r_type in rooms_by_type:
                max_concurrent = sum(r.max_concurrent_classes for r in rooms_by_type[r_type])
            elif r_type == "Ground":
                max_concurrent = 2

            if len(unique_events) > max_concurrent:
                clashes.append({
                    "type": "ROOM_CAPACITY_CLASH",
                    "room_type": r_type,
                    "day": day,
                    "period_index": p_idx,
                    "max_allowed": max_concurrent,
                    "actual_bookings": len(unique_events),
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
