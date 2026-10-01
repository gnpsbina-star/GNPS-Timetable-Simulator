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

    def get_wing_slots(wing_name: str) -> int:
        if not config.period_definitions:
            return total_slots_per_week
        w = (wing_name or '').lower().replace(' ', '').replace('-', '')
        wing_key = 'middle'
        if 'play' in w: wing_key = 'playgroup'
        elif 'pre' in w or 'nur' in w or 'lkg' in w or 'ukg' in w: wing_key = 'pre_primary'
        elif 'prim' in w or any(str(i) in w for i in range(1, 6)): wing_key = 'primary'
        elif 'mid' in w or any(str(i) in w for i in range(6, 9)): wing_key = 'middle'
        elif 'sen' in w or any(str(i) in w for i in [9, 10, 11, 12]): wing_key = 'senior'

        cnt = 0
        for d in config.days:
            day_key = 'saturday' if d.lower() == 'saturday' else 'weekday'
            for p in config.period_definitions:
                if p.get('is_lunch') or p.get('is_assembly'):
                    continue
                sch = p.get('wing_schedule', {}).get(day_key, {}).get(wing_key, 'study')
                if sch == 'study':
                    cnt += 1
        return cnt if cnt > 0 else total_slots_per_week

    # Helper for checking if slot is active study for a section
    def is_slot_active_for_sec(sec_id: str, day: str, p_idx: int) -> bool:
        sec = classes.get(sec_id)
        if not sec:
            return True
        w = (sec.wing or '').lower().replace(' ', '').replace('-', '')
        wing_key = 'middle'
        if 'play' in w: wing_key = 'playgroup'
        elif 'pre' in w or 'nur' in w or 'lkg' in w or 'ukg' in w: wing_key = 'pre_primary'
        elif 'prim' in w or any(str(i) in w for i in range(1, 6)): wing_key = 'primary'
        elif 'mid' in w or any(str(i) in w for i in range(6, 9)): wing_key = 'middle'
        elif 'sen' in w or any(str(i) in w for i in [9, 10, 11, 12]): wing_key = 'senior'

        day_key = 'saturday' if day.lower() == 'saturday' else 'weekday'
        p_def = next((p for p in config.period_definitions if p.get('period_index') == p_idx), None)
        if not p_def or p_def.get('is_lunch') or p_def.get('is_assembly'):
            return False
        sch = p_def.get('wing_schedule', {}).get(day_key, {}).get(wing_key, 'study')
        return sch == 'study'

    # 1. Audit Class Period Quotas (accounting for parallel stream splits)
    class_demand: Dict[str, int] = {c_id: 0 for c_id in classes}
    sec_parallel_groups: Dict[Tuple[str, str], int] = {}
    for ev in events:
        pg_id = ev.parallel_group_id or ev.basket_id
        for sec in ev.section_ids:
            if sec not in class_demand:
                continue
            if pg_id:
                key = (sec, pg_id)
                sec_parallel_groups[key] = max(sec_parallel_groups.get(key, 0), ev.weekly_quota * ev.duration)
            else:
                class_demand[sec] += ev.weekly_quota * ev.duration

    for (sec, pg_id), pg_quota in sec_parallel_groups.items():
        if sec in class_demand:
            class_demand[sec] += pg_quota

    for c_id, total_demanded in class_demand.items():
        c_obj = classes.get(c_id)
        c_name = c_obj.name if c_obj else c_id
        target_capacity = get_wing_slots(c_obj.wing if c_obj else "")
        if total_demanded > target_capacity:
            report.add_error(
                f"Class '{c_name}' demands {total_demanded} periods/week, "
                f"which exceeds the wing schedule capacity of {target_capacity} slots (+{total_demanded - target_capacity})."
            )
        elif total_demanded < target_capacity:
            report.add_warning(
                f"Class '{c_name}' has only {total_demanded}/{target_capacity} periods assigned "
                f"({target_capacity - total_demanded} unscheduled/free slots)."
            )

    # 2. Audit Teacher Capacities & Bottlenecks
    teacher_assigned_load: Dict[str, int] = {t_id: 0 for t_id in teachers}
    for ev in events:
        for t_id in ev.teacher_ids:
            teacher_assigned_load[t_id] = teacher_assigned_load.get(t_id, 0) + (ev.weekly_quota * ev.duration)

    specialist_bottlenecks = []
    for t_id, load in teacher_assigned_load.items():
        t = teachers.get(t_id)
        if not t:
            report.add_warning(f"Teacher ID '{t_id}' referenced in events but not found in teachers list.")
            continue
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
    # 3. Audit Room / Lab Capacities & Utilization
    room_demand: Dict[str, int] = {}
    for ev in events:
        if ev.room_type and ev.room_type != "Classroom":
            room_demand[ev.room_type] = room_demand.get(ev.room_type, 0) + (ev.weekly_quota * ev.duration)

    rooms_by_type: Dict[str, List[Room]] = {}
    for r in rooms.values():
        rooms_by_type.setdefault(r.room_type, []).append(r)

    facility_utilization = {}
    # Audit demanded room types
    for r_type, demanded in room_demand.items():
        room_list = rooms_by_type.get(r_type, [])
        if not room_list:
            report.add_error(
                f"Facility '{r_type}' is required for {demanded} periods/week, but no such room is defined in physical infrastructure."
            )
            continue

        # Effective concurrent capacity
        total_concurrent_capacity = sum(r.max_concurrent_classes for r in room_list)
        max_room_slots = total_concurrent_capacity * total_slots_per_week
        utilization_pct = round((demanded / max_room_slots) * 100, 1) if max_room_slots > 0 else (float('inf') if demanded > 0 else 0.0)

        status = "Optimal"
        if utilization_pct > 100:
            status = "Deficit"
            report.add_error(
                f"Facility '{r_type}' requires {demanded} periods/week, but maximum physical capacity is "
                f"only {max_room_slots} slots across {len(room_list)} room(s) (Deficit: +{demanded - max_room_slots} periods)."
            )
        elif utilization_pct >= 90:
            status = "Bottleneck"
            report.add_warning(
                f"Facility Bottleneck: '{r_type}' is at {utilization_pct}% capacity ({demanded}/{max_room_slots} periods). High risk of room clash."
            )
        elif utilization_pct >= 75:
            status = "High"

        facility_utilization[r_type] = {
            "room_type": r_type,
            "rooms_count": len(room_list),
            "concurrent_capacity": total_concurrent_capacity,
            "demanded_periods": demanded,
            "max_slots": max_room_slots,
            "utilization_pct": utilization_pct,
            "status": status
        }

    # Also record defined rooms that have 0 current demand
    for r_type, room_list in rooms_by_type.items():
        if r_type not in facility_utilization:
            total_concurrent = sum(r.max_concurrent_classes for r in room_list)
            max_slots = total_concurrent * total_slots_per_week
            facility_utilization[r_type] = {
                "room_type": r_type,
                "rooms_count": len(room_list),
                "concurrent_capacity": total_concurrent,
                "demanded_periods": 0,
                "max_slots": max_slots,
                "utilization_pct": 0.0,
                "status": "Available"
            }

    # 4. Audit Bell Schedule & Chronological Consistency
    bell_errors = config.validate_bell_schedule()
    for b_err in bell_errors:
        report.add_error(b_err)

    # Check for overlapping periods
    from .models import parse_time_to_minutes
    for i in range(len(config.period_definitions) - 1):
        p1 = config.period_definitions[i]
        p2 = config.period_definitions[i + 1]
        t1 = p1.get("time", "")
        t2 = p2.get("time", "")
        if "to" in t1 and "to" in t2:
            e1 = parse_time_to_minutes(t1.split("to")[1].strip())
            s2 = parse_time_to_minutes(t2.split("to")[0].strip())
            if e1 is not None and s2 is not None and e1 > s2:
                report.add_error(
                    f"Overlapping periods detected: '{p1.get('name')}' ends at {t1.split('to')[1].strip()}, "
                    f"which is after '{p2.get('name')}' starts at {t2.split('to')[0].strip()}."
                )

    # 5. Audit Senior Elective Baskets, Parallel Stream Splits & Joint Classes
    parallel_groups: Dict[str, List[Event]] = {}
    joint_events: List[Event] = []

    for ev in events:
        pg_id = ev.parallel_group_id or ev.basket_id
        if pg_id:
            parallel_groups.setdefault(pg_id, []).append(ev)
        if ev.is_joint or len(ev.section_ids) > 1:
            joint_events.append(ev)

    elective_audit_details = []

    # 5a. Audit Parallel Groups
    for pg_id, grp_events in parallel_groups.items():
        basket_name = grp_events[0].elective_basket or pg_id
        all_sec_ids = list({s for e in grp_events for s in e.section_ids})
        all_teachers = [t for e in grp_events for t in e.teacher_ids]
        max_quota = max(e.weekly_quota for e in grp_events)

        # 1. Intra-group teacher conflict: check if a teacher is assigned to multiple branches
        teacher_counts: Dict[str, List[str]] = {}
        for e in grp_events:
            for tid in e.teacher_ids:
                teacher_counts.setdefault(tid, []).append(e.subject)
        for tid, subjs in teacher_counts.items():
            if len(subjs) > 1:
                t_obj = teachers.get(tid)
                t_name = t_obj.name if t_obj else tid
                report.add_error(
                    f"Parallel Elective Split '{basket_name}' conflict: Teacher '{t_name}' is assigned "
                    f"to multiple simultaneous branches ({', '.join(subjs)}). A teacher cannot teach two split classes at the same time."
                )

        # 2. Intra-group room conflict: check if branches demand more specialized rooms than exist
        room_demands: Dict[str, int] = {}
        for e in grp_events:
            if e.room_type and e.room_type != "Classroom":
                room_demands[e.room_type] = room_demands.get(e.room_type, 0) + 1
        for rt, req_cap in room_demands.items():
            max_c = sum(r.max_concurrent_classes for r in rooms_by_type.get(rt, []))
            if req_cap > max_c:
                report.add_error(
                    f"Parallel Elective Split '{basket_name}' room bottleneck: Requires {req_cap} simultaneous "
                    f"'{rt}' facilities, but only {max_c} are available in physical infrastructure."
                )

        # 3. Mutual overlapping teacher availability
        common_study_slots = []
        for d in config.days:
            for p_def in config.period_definitions:
                p_idx = p_def.get("period_index", 0)
                if p_def.get("is_lunch") or p_def.get("is_assembly"):
                    continue
                if all(is_slot_active_for_sec(s, d, p_idx) for s in all_sec_ids):
                    if all(teachers.get(tid, Teacher("", "")).is_available(d, p_idx) for tid in all_teachers):
                        common_study_slots.append((d, p_idx))

        if len(common_study_slots) < max_quota:
            report.add_error(
                f"Parallel Elective Split '{basket_name}' availability bottleneck: Requires {max_quota} periods, "
                f"but assigned faculty and sections share only {len(common_study_slots)} mutually free study slots per week "
                f"(Deficit: {max_quota - len(common_study_slots)} slots)."
            )

        elective_audit_details.append({
            "group_id": pg_id,
            "basket_name": basket_name,
            "branches_count": len(grp_events),
            "sections": all_sec_ids,
            "teachers": [teachers.get(tid, Teacher(tid, tid)).name for tid in all_teachers],
            "quota": max_quota,
            "shared_slots": len(common_study_slots),
            "status": "Feasible" if len(common_study_slots) >= max_quota else "Infeasible"
        })

    # 5b. Audit Joint Classes
    joint_audit_details = []
    for j_ev in joint_events:
        j_label = j_ev.joint_label or f"{j_ev.subject} ({' + '.join(j_ev.section_ids)})"
        shared_sec_slots = []
        for d in config.days:
            for p_def in config.period_definitions:
                p_idx = p_def.get("period_index", 0)
                if p_def.get("is_lunch") or p_def.get("is_assembly"):
                    continue
                if all(is_slot_active_for_sec(s, d, p_idx) for s in j_ev.section_ids):
                    if all(teachers.get(tid, Teacher("", "")).is_available(d, p_idx) for tid in j_ev.teacher_ids):
                        shared_sec_slots.append((d, p_idx))

        if len(shared_sec_slots) < j_ev.weekly_quota:
            report.add_error(
                f"Joint Session '{j_label}' schedule bottleneck: Demands {j_ev.weekly_quota} periods, "
                f"but participating sections and teacher share only {len(shared_sec_slots)} common active study slots per week."
            )

        joint_audit_details.append({
            "event_id": j_ev.id,
            "label": j_label,
            "subject": j_ev.subject,
            "sections": j_ev.section_ids,
            "teachers": [teachers.get(tid, Teacher(tid, tid)).name for tid in j_ev.teacher_ids],
            "quota": j_ev.weekly_quota,
            "shared_slots": len(shared_sec_slots),
            "status": "Feasible" if len(shared_sec_slots) >= j_ev.weekly_quota else "Infeasible"
        })

    # Calculate weekly instructional minutes for each wing
    instructional_hours = {}
    for w_name in ["Playgroup", "Pre-Primary", "Primary", "Middle", "Senior"]:
        instructional_hours[w_name] = config.get_wing_instructional_minutes(w_name)

    report.stats = {
        "total_classes": len(classes),
        "total_teachers": len(teachers),
        "total_events": len(events),
        "specialist_bottlenecks": specialist_bottlenecks,
        "instructional_hours": instructional_hours,
        "facility_utilization": facility_utilization,
        "elective_groups_count": len(parallel_groups),
        "joint_sessions_count": len(joint_events),
        "elective_audit": elective_audit_details,
        "joint_audit": joint_audit_details
    }

    return report
