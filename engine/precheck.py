"""
Pre-solver Feasibility & Capacity Bottleneck Audit.
Performs arithmetic sanity checks before running the combinatorial solver.
Catches over-allocations, specialist teacher bottlenecks, and lab deficits.
"""

from typing import List, Dict, Any, Tuple
from .models import SchoolConfig, Teacher, ClassSection, Room, Event

class AuditReport:
    def __init__(self):
        self.is_feasible: bool = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.stats: Dict[str, Any] = {}

    def add_error(self, msg: str):
        self.is_feasible = False
        self.errors.append(msg)

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_feasible": self.is_feasible,
            "errors": self.errors,
            "warnings": self.warnings,
            "stats": self.stats
        }

def audit_capacity(
    config: SchoolConfig,
    teachers: Dict[str, Teacher],
    classes: Dict[str, ClassSection],
    rooms: Dict[str, Room],
    events: List[Event]
) -> AuditReport:
    report = AuditReport()

    total_days = len(config.days)
    periods_per_day = config.periods_per_day
    total_slots_per_week = total_days * periods_per_day

    # 1. Audit Class Period Quotas
    class_demand: Dict[str, int] = {c_id: 0 for c_id in classes}
    for ev in events:
        for sec in ev.section_ids:
            if sec in class_demand:
                class_demand[sec] += ev.weekly_quota * ev.duration

    for c_id, total_demanded in class_demand.items():
        c_name = classes[c_id].name if c_id in classes else c_id
        if total_demanded > total_slots_per_week:
            report.add_error(
                f"Class '{c_name}' demands {total_demanded} periods/week, "
                f"which exceeds the maximum schedule capacity of {total_slots_per_week} slots."
            )
        elif total_demanded < total_slots_per_week:
            report.add_warning(
                f"Class '{c_name}' has only {total_demanded}/{total_slots_per_week} periods assigned "
                f"({total_slots_per_week - total_demanded} unscheduled/free slots)."
            )

    # 2. Audit Teacher Capacities & Bottlenecks
    teacher_assigned_load: Dict[str, int] = {t_id: 0 for t_id in teachers}
    for ev in events:
        for t_id in ev.teacher_ids:
            if t_id in teacher_assigned_load:
                teacher_assigned_load[t_id] += ev.weekly_quota * ev.duration

    specialist_bottlenecks = []
    for t_id, load in teacher_assigned_load.items():
        t = teachers[t_id]
        available_slots = total_slots_per_week - len(t.unavailable_slots)

        if load > available_slots:
            report.add_error(
                f"Teacher '{t.name}' assigned {load} periods/week, but is only available for "
                f"{available_slots} slots (deficit of {load - available_slots} periods)."
            )
        elif load > t.max_weekly_periods:
            report.add_error(
                f"Teacher '{t.name}' assigned {load} periods, exceeding their maximum cap of {t.max_weekly_periods} periods/week."
            )
        elif available_slots > 0:
            utilization = load / available_slots
            if utilization >= 0.90:
                report.add_warning(
                    f"Specialist Bottleneck: Teacher '{t.name}' is at {utilization*100:.1f}% capacity "
                    f"({load}/{available_slots} periods). High risk of scheduling conflicts."
                )
                specialist_bottlenecks.append({
                    "teacher": t.name,
                    "load": load,
                    "capacity": available_slots,
                    "utilization": round(utilization * 100, 1)
                })

    # 3. Audit Room / Lab Capacities
    room_demand: Dict[str, int] = {}
    for ev in events:
        if ev.room_type and ev.room_type != "Classroom":
            room_demand[ev.room_type] = room_demand.get(ev.room_type, 0) + (ev.weekly_quota * ev.duration)

    rooms_by_type: Dict[str, int] = {}
    for r in rooms.values():
        rooms_by_type[r.room_type] = rooms_by_type.get(r.room_type, 0) + 1

    for r_type, demanded in room_demand.items():
        available_rooms = rooms_by_type.get(r_type, 0)
        max_room_slots = available_rooms * total_slots_per_week
        if available_rooms == 0:
            report.add_error(
                f"Facility '{r_type}' is required for {demanded} periods/week, but no such room is defined."
            )
        elif demanded > max_room_slots:
            report.add_error(
                f"Facility '{r_type}' requires {demanded} periods/week, but maximum facility capacity is "
                f"only {max_room_slots} slots across {available_rooms} room(s)."
            )

    report.stats = {
        "total_classes": len(classes),
        "total_teachers": len(teachers),
        "total_events": len(events),
        "specialist_bottlenecks": specialist_bottlenecks
    }

    return report
