"""
High-Performance Pure-Python Constraint Satisfaction Problem (CSP) Solver.
Uses Backtracking Search with MRV (Minimum Remaining Values), Degree Heuristic,
Forward Checking, and Soft Constraint Optimization.
Guarantees zero-dependency execution across any standard Python 3.9+ runtime.
"""

from typing import List, Dict, Set, Tuple, Optional, Any
import copy
import random
import sys
from .models import (

    SchoolConfig,
    Teacher,
    ClassSection,
    Room,
    Event,
    ElectiveBasket,
    SlotAssignment,
    TimetableGrid
)

class CSPSolverResult:
    def __init__(self, success: bool, grid: Optional[TimetableGrid] = None, message: str = ""):
        self.success = success
        self.grid = grid
        self.message = message
        self.steps_count: int = 0
        self.conflict_details: Optional[Dict[str, Any]] = None

class CSPSolver:
    def __init__(
        self,
        config: SchoolConfig,
        teachers: Dict[str, Teacher],
        classes: Dict[str, ClassSection],
        rooms: Dict[str, Room],
        events: List[Event],
        baskets: Optional[List[ElectiveBasket]] = None,
        max_steps: int = 100000
    ):
        self.config = config
        self.teachers = teachers
        self.classes = classes
        self.rooms = rooms
        self.events = events
        self.baskets = baskets or []
        self.max_steps = max_steps
        self.steps = 0
        self.unit_neighbors: Dict[str, List[str]] = {}

        # Precompute valid schedule slots (excluding lunch & assembly)
        self.all_slots: List[Tuple[str, int]] = []
        self.lunch_slots: Set[Tuple[str, int]] = set()
        self.assembly_slots: Set[Tuple[str, int]] = set()

        for d in self.config.days:
            for i, p_def in enumerate(self.config.period_definitions):
                p_idx = p_def.get("period_index", i)
                if p_def.get("is_lunch", False):
                    self.lunch_slots.add((d, p_idx))
                elif p_def.get("is_assembly", False):
                    self.assembly_slots.add((d, p_idx))
                else:
                    self.all_slots.append((d, p_idx))

        # Room capacities and groupings
        self.rooms_by_type: Dict[str, List[Room]] = {}
        self.room_capacities: Dict[str, int] = {}
        for r in rooms.values():
            self.room_capacities[r.room_type] = self.room_capacities.get(r.room_type, 0) + 1
            self.rooms_by_type.setdefault(r.room_type, []).append(r)

    def _get_wing_key(self, wing_name: str) -> str:
        w = (wing_name or '').lower().replace(' ', '').replace('-', '')
        if 'play' in w: return 'playgroup'
        elif 'pre' in w or 'nur' in w or 'lkg' in w or 'ukg' in w: return 'pre_primary'
        elif 'prim' in w or any(str(i) in w for i in range(1, 6)): return 'primary'
        elif 'mid' in w or any(str(i) in w for i in range(6, 9)): return 'middle'
        elif 'sen' in w or any(str(i) in w for i in [9, 10, 11, 12]): return 'senior'
        return 'middle'

    def _is_slot_active_for_section(self, sec_id: str, day: str, p_idx: int) -> bool:
        sec = self.classes.get(sec_id)
        if not sec:
            return True
        wing_key = self._get_wing_key(sec.wing)
        day_key = 'saturday' if day.lower() == 'saturday' else 'weekday'
        p_def = next((p for i, p in enumerate(self.config.period_definitions) if p.get('period_index', i) == p_idx), None)
        if not p_def:
            return True
        if p_def.get('is_lunch') or p_def.get('is_assembly'):
            return False
        wing_schedule = p_def.get('wing_schedule', {}).get(day_key, {})
        return wing_schedule.get(wing_key, 'study') == 'study'

    def solve(self) -> CSPSolverResult:
        grid = TimetableGrid(self.config)
        self.steps = 0


        # 1. Expand events into atomic scheduling units
        all_events: List[Event] = list(self.events)

        # Incorporate baskets if provided
        if self.baskets:
            for basket in self.baskets:
                for b_ev in basket.events:
                    if not b_ev.parallel_group_id:
                        b_ev.parallel_group_id = basket.id
                    if not b_ev.elective_basket:
                        b_ev.elective_basket = basket.name
                    if b_ev.weekly_quota <= 1 and basket.weekly_quota and basket.weekly_quota > 1:
                        b_ev.weekly_quota = basket.weekly_quota
                    if not any(e.id == b_ev.id for e in all_events):
                        all_events.append(b_ev)

        # Separate parallel elective events vs standalone events
        events_by_group: Dict[str, List[Event]] = {}
        standalone_events: List[Event] = []

        for ev in all_events:
            # Bridge legacy basket_id if set
            if ev.basket_id and not ev.parallel_group_id:
                ev.parallel_group_id = ev.basket_id

            if ev.parallel_group_id:
                events_by_group.setdefault(ev.parallel_group_id, []).append(ev)
            else:
                standalone_events.append(ev)

        units = []

        # 1a. Expand parallel groups into atomic synchronized units
        for grp_id, grp_events in events_by_group.items():
            quota = min(e.weekly_quota for e in grp_events) if grp_events else 0
            duration = max(e.duration for e in grp_events) if grp_events else 1
            for i in range(quota):
                pinned = None
                for e in grp_events:
                    if i < len(e.locked_slots):
                        pinned = e.locked_slots[i]
                        break
                units.append({
                    "unit_id": f"PG_{grp_id}_{i}",
                    "events": grp_events,
                    "event": grp_events[0],
                    "occ_index": i,
                    "duration": duration,
                    "pinned": pinned,
                    "is_parallel": True,
                    "parallel_group_id": grp_id
                })

        # 1b. Expand standalone events
        for ev in standalone_events:
            pinned_slots = list(ev.locked_slots)
            for i in range(ev.weekly_quota):
                pinned = pinned_slots[i] if i < len(pinned_slots) else None
                units.append({
                    "unit_id": f"{ev.id}_{i}",
                    "events": [ev],
                    "event": ev,
                    "occ_index": i,
                    "duration": ev.duration,
                    "pinned": pinned,
                    "is_parallel": False,
                    "parallel_group_id": None
                })

        self.units_by_id = {u["unit_id"]: u for u in units}

        # 2. Build constraint adjacency graph for fast O(1) neighbor lookups
        units_by_sec: Dict[str, Set[str]] = {}
        units_by_teacher: Dict[str, Set[str]] = {}
        units_by_room: Dict[str, Set[str]] = {}
        for u in units:
            uid = u["unit_id"]
            for ev in u["events"]:
                for sec in ev.section_ids:
                    units_by_sec.setdefault(sec, set()).add(uid)
                for tid in ev.teacher_ids:
                    units_by_teacher.setdefault(tid, set()).add(uid)
                if ev.room_type and ev.room_type != "Classroom":
                    units_by_room.setdefault(ev.room_type, set()).add(uid)

        self.unit_neighbors = {}
        for u in units:
            uid = u["unit_id"]
            neighs = set()
            for ev in u["events"]:
                for sec in ev.section_ids:
                    neighs.update(units_by_sec.get(sec, set()))
                for tid in ev.teacher_ids:
                    neighs.update(units_by_teacher.get(tid, set()))
                if ev.room_type and ev.room_type != "Classroom":
                    neighs.update(units_by_room.get(ev.room_type, set()))
            neighs.discard(uid)
            self.unit_neighbors[uid] = list(neighs)

        # 3. Build initial domain for each unit (strictly respecting wing active study periods)
        domains: Dict[str, List[Tuple[str, int]]] = {}
        for u in units:
            if u["pinned"]:
                domains[u["unit_id"]] = [u["pinned"]]
                continue

            valid_slots = []
            for (day, p_idx) in self.all_slots:
                # Wing active schedule check: slot must be a 'study' period for all participating sections
                is_active = True
                for ev in u["events"]:
                    for sec_id in ev.section_ids:
                        if not self._is_slot_active_for_section(sec_id, day, p_idx):
                            is_active = False
                            break
                        if u["duration"] == 2 and not self._is_slot_active_for_section(sec_id, day, p_idx + 1):
                            is_active = False
                            break
                    if not is_active:
                        break
                if not is_active:
                    continue

                # Double period check: next period cannot be lunch, assembly, or beyond period limit
                if u["duration"] == 2:
                    next_slot = (day, p_idx + 1)
                    if next_slot in self.lunch_slots or next_slot in self.assembly_slots or (p_idx + 1) >= self.config.periods_per_day:
                        continue

                # Teacher availability check
                t_avail = True
                for ev in u["events"]:
                    for t_id in ev.teacher_ids:
                        t = self.teachers.get(t_id)
                        if t and not t.is_available(day, p_idx):
                            t_avail = False
                            break
                        if u["duration"] == 2 and t and not t.is_available(day, p_idx + 1):
                            t_avail = False
                            break
                    if not t_avail:
                        break
                if not t_avail:
                    continue

                # Specialized room intra-group check: group cannot demand more rooms of same type than exist
                room_cap_ok = True
                room_req_counts: Dict[str, int] = {}
                for ev in u["events"]:
                    if ev.room_type and ev.room_type != "Classroom":
                        room_req_counts[ev.room_type] = room_req_counts.get(ev.room_type, 0) + 1
                for rt, req_count in room_req_counts.items():
                    max_cap = 1
                    if self.rooms_by_type and rt in self.rooms_by_type:
                        max_cap = sum(r.max_concurrent_classes for r in self.rooms_by_type[rt])
                    elif rt == "Ground":
                        max_cap = 2
                    if req_count > max_cap:
                        room_cap_ok = False
                        break
                if not room_cap_ok:
                    continue

                valid_slots.append((day, p_idx))

            domains[u["unit_id"]] = valid_slots

        # 4. Run Backtracking Search with MRV
        req_limit = max(sys.getrecursionlimit(), len(units) * 2 + 5000)
        sys.setrecursionlimit(req_limit)

        success, conflict_info = self._backtrack(units, domains, grid, {})

        if success:
            res = CSPSolverResult(True, grid, "Successfully generated 100% clash-free timetable.")
            res.steps_count = self.steps
            return res
        else:
            res = CSPSolverResult(False, None, "Generation Infeasible with current constraints.")
            res.steps_count = self.steps
            res.conflict_details = conflict_info
            return res

    def _find_basket_slots(self, basket: ElectiveBasket, grid: TimetableGrid) -> List[Tuple[str, int]]:
        """Finds parallel slots for senior secondary elective baskets."""
        chosen_slots = []
        days_pool = list(self.config.days)
        random.shuffle(days_pool)

        for day in days_pool:
            if len(chosen_slots) >= basket.weekly_quota:
                break
            for p_idx in range(1, self.config.periods_per_day - 1):
                if (day, p_idx) in self.lunch_slots or (day, p_idx) in self.assembly_slots:
                    continue

                # Check if all events in basket can run at (day, p_idx)
                all_clear = True
                for ev in basket.events:
                    clashes = grid.check_clash(ev, day, p_idx, self.rooms_by_type)
                    if clashes:
                        all_clear = False
                        break

                if all_clear:
                    # Assign all events in basket simultaneously
                    for ev in basket.events:
                        assign = SlotAssignment(
                            event_id=ev.id,
                            day=day,
                            period_index=p_idx,
                            subject=ev.subject,
                            teacher_ids=ev.teacher_ids,
                            section_ids=ev.section_ids,
                            room_type=ev.room_type,
                            is_locked=True
                        )
                        grid.assign(assign)
                    chosen_slots.append((day, p_idx))
                    break

        return chosen_slots if len(chosen_slots) == basket.weekly_quota else []

    def _select_unassigned_variable(
        self,
        units: List[Dict[str, Any]],
        domains: Dict[str, List[Tuple[str, int]]],
        assigned: Dict[str, Tuple[str, int]]
    ) -> Optional[Dict[str, Any]]:
        """MRV (Minimum Remaining Values) + Degree Heuristic Variable Ordering."""
        best_u = None
        min_domain_len = float("inf")
        max_degree = -1

        for u in units:
            u_id = u["unit_id"]
            if u_id in assigned:
                continue

            d_len = len(domains[u_id])

            # Degree: prioritize parallel split groups, specialist teachers, clubbed classes, double periods, and class teacher events
            degree = 0
            if u.get("is_parallel"):
                degree += 15  # Strongly prioritize parallel elective stream splits

            for ev in u["events"]:
                degree += len(ev.section_ids) * 2 + len(ev.teacher_ids) * 2
                for t_id in ev.teacher_ids:
                    if self.teachers.get(t_id, Teacher("", "")).is_specialist:
                        degree += 3

            if u["duration"] == 2:
                degree += 5

            # Prioritize Class Teacher scheduling to secure Period 1
            if getattr(self.config, 'enforce_class_teacher_p1', True):
                for ev in u["events"]:
                    for sec_id in ev.section_ids:
                        sec = self.classes.get(sec_id)
                        if sec and sec.class_teacher:
                            ct_lower = sec.class_teacher.strip().lower()
                            if ct_lower:  # Guard: empty string after strip matches everything
                                for t_id in ev.teacher_ids:
                                    t_obj = self.teachers.get(t_id)
                                    t_name_lower = t_obj.name.strip().lower() if t_obj else ""
                                    if (t_id.strip().lower() in ct_lower or ct_lower in t_id.strip().lower()
                                        or (t_name_lower and (t_name_lower in ct_lower or ct_lower in t_name_lower))):
                                        degree += 12
                                        break

            if d_len < min_domain_len or (d_len == min_domain_len and degree > max_degree):
                min_domain_len = d_len
                max_degree = degree
                best_u = u

        return best_u

    def _order_domain_values(
        self,
        u: Dict[str, Any],
        domains: Dict[str, List[Tuple[str, int]]],
        grid: TimetableGrid
    ) -> List[Tuple[str, int]]:
        """
        Soft Constraint Value Ordering:
        1. Prefers spreading subjects evenly across different days.
        2. Enforces Class Teacher takes Period 1 when enforce_class_teacher_p1 is True.
        """
        candidate_slots = list(domains[u["unit_id"]])

        # Check if event is taught by the Class Teacher for this section
        is_class_teacher_event = False
        sec_has_class_teacher = False
        if getattr(self.config, 'enforce_class_teacher_p1', True):
            for ev in u["events"]:
                for sec_id in ev.section_ids:
                    sec = self.classes.get(sec_id)
                    if sec and sec.class_teacher:
                        sec_has_class_teacher = True
                        ct_lower = sec.class_teacher.strip().lower()
                        if ct_lower:  # Guard: empty string after strip matches everything
                            for t_id in ev.teacher_ids:
                                t_obj = self.teachers.get(t_id)
                                t_name_lower = t_obj.name.strip().lower() if t_obj else ""
                                if (t_id.strip().lower() in ct_lower or ct_lower in t_id.strip().lower()
                                    or (t_name_lower and (t_name_lower in ct_lower or ct_lower in t_name_lower))):
                                    is_class_teacher_event = True
                                    break

        # Count existing days where subjects in this unit are already assigned
        assigned_days = set()
        for ev in u["events"]:
            for sec in ev.section_ids:
                for d in self.config.days:
                    for p_idx in range(self.config.periods_per_day):
                        existing = grid.section_grid.get((sec, d, p_idx))
                        if existing and existing.subject == ev.subject:
                            assigned_days.add(d)

        # Score slots: lower score = better
        def slot_score(slot):
            day, p_idx = slot

            score = 0
            if day in assigned_days:
                score += 5  # Penalize placing same subject on same day twice

            # Class Teacher Period 1 Rule: Strongly favor Period 1 for the Class Teacher
            if is_class_teacher_event:
                if p_idx == 1:
                    score -= 50  # Heavy bonus for Period 1
                else:
                    score += 5   # Mild penalty for non-Period-1
            elif sec_has_class_teacher and p_idx == 1:
                # Mild penalty for other teachers taking Period 1 to keep it open for Class Teacher
                score += 15

            if p_idx > 5:
                score += 1  # Slightly prefer earlier periods
            return score

        candidate_slots.sort(key=slot_score)
        return candidate_slots

    def _backtrack(
        self,
        units: List[Dict[str, Any]],
        domains: Dict[str, List[Tuple[str, int]]],
        grid: TimetableGrid,
        assigned: Dict[str, Tuple[str, int]]
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        if len(assigned) == len(units):
            return True, None

        self.steps += 1
        if self.steps > self.max_steps:
            return False, {"reason": "STEP_BUDGET_EXCEEDED", "steps": self.steps}

        u = self._select_unassigned_variable(units, domains, assigned)
        if not u:
            return True, None

        u_id = u["unit_id"]
        ev_lead: Event = u["event"]
        slots_to_try = self._order_domain_values(u, domains, grid)

        if not slots_to_try:
            return False, {
                "reason": "EMPTY_DOMAIN",
                "unit_id": u_id,
                "event_id": ev_lead.id,
                "subject": ev_lead.subject,
                "sections": [s for e in u["events"] for s in e.section_ids],
                "teachers": [t for e in u["events"] for t in e.teacher_ids]
            }

        for (day, p_idx) in slots_to_try:
            # 1. Daily teacher max periods check across all teachers in unit
            overload = False
            for ev in u["events"]:
                for t_id in ev.teacher_ids:
                    t = self.teachers.get(t_id)
                    if t:
                        day_load = sum(
                            1 for p in range(self.config.periods_per_day)
                            if (t_id, day, p) in grid.teacher_grid
                        )
                        if day_load + u["duration"] > t.max_daily_periods:
                            overload = True
                            break
                if overload:
                    break
            if overload:
                continue

            # 2. Hard clash check and sequential assignment for all events in unit
            temp_assigned: List[SlotAssignment] = []
            clashed = False

            for ev in u["events"]:
                clashes = grid.check_clash(ev, day, p_idx, self.rooms_by_type)
                if u["duration"] == 2:
                    clashes.extend(grid.check_clash(ev, day, p_idx + 1, self.rooms_by_type))
                if clashes:
                    clashed = True
                    break

                assign1 = SlotAssignment(
                    event_id=ev.id,
                    day=day,
                    period_index=p_idx,
                    subject=ev.subject,
                    teacher_ids=ev.teacher_ids,
                    section_ids=ev.section_ids,
                    room_type=ev.room_type,
                    is_locked=u["pinned"] is not None,
                    is_joint=ev.is_joint,
                    joint_label=ev.joint_label,
                    parallel_group_id=ev.parallel_group_id,
                    elective_basket=ev.elective_basket
                )
                grid.assign(assign1)
                temp_assigned.append(assign1)

                if u["duration"] == 2:
                    assign2 = SlotAssignment(
                        event_id=ev.id,
                        day=day,
                        period_index=p_idx + 1,
                        subject=ev.subject,
                        teacher_ids=ev.teacher_ids,
                        section_ids=ev.section_ids,
                        room_type=ev.room_type,
                        is_locked=u["pinned"] is not None,
                        is_joint=ev.is_joint,
                        joint_label=ev.joint_label,
                        parallel_group_id=ev.parallel_group_id,
                        elective_basket=ev.elective_basket
                    )
                    grid.assign(assign2)
                    temp_assigned.append(assign2)

            if clashed:
                for a in reversed(temp_assigned):
                    grid.remove(a)
                continue

            assigned[u_id] = (day, p_idx)

            # 3. Forward Checking: prune domain of neighboring units
            pruned: Dict[str, List[Tuple[str, int]]] = {}
            domain_wipeout = False

            for other_id in self.unit_neighbors.get(u_id, []):
                if other_id in assigned:
                    continue

                other_unit = self.units_by_id[other_id]

                shares_entity = False
                for other_ev in other_unit["events"]:
                    for this_ev in u["events"]:
                        if (set(this_ev.section_ids).intersection(other_ev.section_ids) or
                            set(this_ev.teacher_ids).intersection(other_ev.teacher_ids)):
                            shares_entity = True
                            break
                    if shares_entity:
                        break

                room_full = False
                if not shares_entity:
                    for other_ev in other_unit["events"]:
                        if other_ev.room_type and other_ev.room_type != "Classroom":
                            max_cap = 1
                            if self.rooms_by_type and other_ev.room_type in self.rooms_by_type:
                                max_cap = sum(r.max_concurrent_classes for r in self.rooms_by_type[other_ev.room_type])
                            elif other_ev.room_type == "Ground":
                                max_cap = 2
                            existing = grid.room_type_grid.get((other_ev.room_type, day, p_idx), [])
                            unique_bookings = {a.event_id for a in existing}
                            if len(unique_bookings) >= max_cap:
                                room_full = True
                                break

                if (shares_entity or room_full) and (day, p_idx) in domains[other_id]:
                    if other_id not in pruned:
                        pruned[other_id] = []
                    domains[other_id].remove((day, p_idx))
                    pruned[other_id].append((day, p_idx))

                    if u["duration"] == 2 and (day, p_idx + 1) in domains[other_id]:
                        domains[other_id].remove((day, p_idx + 1))
                        pruned[other_id].append((day, p_idx + 1))

                    if not domains[other_id]:
                        domain_wipeout = True
                        break

            if not domain_wipeout:
                success, conflict_info = self._backtrack(units, domains, grid, assigned)
                if success:
                    return True, None

            # 4. Undo Assignment and restore pruned domains
            del assigned[u_id]
            for a in reversed(temp_assigned):
                grid.remove(a)

            for other_id, restored_slots in pruned.items():
                domains[other_id].extend(restored_slots)

        return False, {
            "reason": "BACKTRACK_EXHAUSTED",
            "unit_id": u_id,
            "event_id": ev_lead.id,
            "subject": ev_lead.subject,
            "sections": [s for e in u["events"] for s in e.section_ids],
            "teachers": [t for e in u["events"] for t in e.teacher_ids]
        }
