"""
High-Performance Pure-Python Constraint Satisfaction Problem (CSP) Solver.
Uses Backtracking Search with MRV (Minimum Remaining Values), Degree Heuristic,
Forward Checking, and Soft Constraint Optimization.
Guarantees zero-dependency execution across any standard Python 3.9+ runtime.
"""

from typing import List, Dict, Set, Tuple, Optional, Any
import copy
import random
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
        max_steps: int = 25000
    ):
        self.config = config
        self.teachers = teachers
        self.classes = classes
        self.rooms = rooms
        self.events = events
        self.baskets = baskets or []
        self.max_steps = max_steps
        self.steps = 0

        # Precompute valid schedule slots (excluding lunch & assembly)
        self.all_slots: List[Tuple[str, int]] = []
        self.lunch_slots: Set[Tuple[str, int]] = set()
        self.assembly_slots: Set[Tuple[str, int]] = set()

        for d in self.config.days:
            for p_def in self.config.period_definitions:
                p_idx = p_def.get("period_index", 0)
                if p_def.get("is_lunch", False):
                    self.lunch_slots.add((d, p_idx))
                elif p_def.get("is_assembly", False):
                    self.assembly_slots.add((d, p_idx))
                else:
                    self.all_slots.append((d, p_idx))

        # Room capacities
        self.room_capacities: Dict[str, int] = {}
        for r in rooms.values():
            self.room_capacities[r.room_type] = self.room_capacities.get(r.room_type, 0) + 1

    def solve(self) -> CSPSolverResult:
        grid = TimetableGrid(self.config)
        self.steps = 0

        # 1. Expand events into atomic scheduling units
        # An event with quota Q produces Q distinct unit slots to place.
        units = []
        unit_id = 1
        for ev in self.events:
            # If part of an elective basket, basket handles sync
            if ev.basket_id:
                continue

            # Check for pinned slots
            pinned_slots = list(ev.locked_slots)
            for i in range(ev.weekly_quota):
                pinned = pinned_slots[i] if i < len(pinned_slots) else None
                units.append({
                    "unit_id": f"{ev.id}_{i}",
                    "event": ev,
                    "occ_index": i,
                    "duration": ev.duration,
                    "pinned": pinned
                })

        # 2. Build initial domain for each unit
        domains: Dict[str, List[Tuple[str, int]]] = {}
        for u in units:
            ev: Event = u["event"]
            if u["pinned"]:
                domains[u["unit_id"]] = [u["pinned"]]
                continue

            valid_slots = []
            for (day, p_idx) in self.all_slots:
                # Double period check: next period cannot be lunch or beyond period limit
                if u["duration"] == 2:
                    next_slot = (day, p_idx + 1)
                    if next_slot in self.lunch_slots or (p_idx + 1) >= self.config.periods_per_day:
                        continue

                # Teacher availability check
                t_avail = True
                for t_id in ev.teacher_ids:
                    t = self.teachers.get(t_id)
                    if t and not t.is_available(day, p_idx):
                        t_avail = False
                        break
                    if u["duration"] == 2 and t and not t.is_available(day, p_idx + 1):
                        t_avail = False
                        break
                if not t_avail:
                    continue

                valid_slots.append((day, p_idx))

            domains[u["unit_id"]] = valid_slots

        # 3. Schedule Elective Baskets First (Highest Degree Constraint)
        for basket in self.baskets:
            basket_slots = self._find_basket_slots(basket, grid)
            if not basket_slots:
                return CSPSolverResult(
                    False, None,
                    f"Infeasible: Could not find {basket.weekly_quota} conflict-free parallel slots for Elective Basket '{basket.name}'."
                )

        # 4. Run Backtracking Search with MRV
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
                    clashes = grid.check_clash(ev, day, p_idx)
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
            ev: Event = u["event"]

            # Degree: prioritize specialist teachers, clubbed classes, and double periods
            degree = len(ev.section_ids) * 2 + len(ev.teacher_ids) * 2
            if u["duration"] == 2:
                degree += 5
            for t_id in ev.teacher_ids:
                if self.teachers.get(t_id, Teacher("", "")).is_specialist:
                    degree += 3

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
        Prefers spreading subjects evenly across different days.
        """
        ev: Event = u["event"]
        candidate_slots = list(domains[u["unit_id"]])

        # Count existing days where this subject is already assigned to this section
        assigned_days = set()
        for sec in ev.section_ids:
            for d in self.config.days:
                for p_idx in range(self.config.periods_per_day):
                    existing = grid.section_grid.get((sec, d, p_idx))
                    if existing and existing.subject == ev.subject:
                        assigned_days.add(d)

        # Score slots: lower score = better (prefer days not yet containing this subject)
        def slot_score(slot: Tuple[str, int]) -> int:
            day, p_idx = slot
            score = 0
            if day in assigned_days:
                score += 5  # Penalize placing same subject on same day twice
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
        ev: Event = u["event"]
        slots_to_try = self._order_domain_values(u, domains, grid)

        if not slots_to_try:
            return False, {
                "reason": "EMPTY_DOMAIN",
                "event_id": ev.id,
                "subject": ev.subject,
                "sections": ev.section_ids,
                "teachers": ev.teacher_ids
            }

        for (day, p_idx) in slots_to_try:
            # 1. Hard clash check
            clashes = grid.check_clash(ev, day, p_idx)
            if u["duration"] == 2:
                clashes.extend(grid.check_clash(ev, day, p_idx + 1))
            if clashes:
                continue

            # 2. Daily teacher max periods check
            overload = False
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
                continue

            # 3. Assign
            assign1 = SlotAssignment(
                event_id=ev.id,
                day=day,
                period_index=p_idx,
                subject=ev.subject,
                teacher_ids=ev.teacher_ids,
                section_ids=ev.section_ids,
                room_type=ev.room_type,
                is_locked=u["pinned"] is not None
            )
            grid.assign(assign1)
            assign2 = None
            if u["duration"] == 2:
                assign2 = SlotAssignment(
                    event_id=ev.id,
                    day=day,
                    period_index=p_idx + 1,
                    subject=ev.subject,
                    teacher_ids=ev.teacher_ids,
                    section_ids=ev.section_ids,
                    room_type=ev.room_type,
                    is_locked=u["pinned"] is not None
                )
                grid.assign(assign2)

            assigned[u_id] = (day, p_idx)

            # 4. Forward Checking: prune domain of other units
            pruned: Dict[str, List[Tuple[str, int]]] = {}
            domain_wipeout = False

            for other_u in units:
                other_id = other_u["unit_id"]
                if other_id in assigned:
                    continue

                other_ev: Event = other_u["event"]
                # If sharing teacher or section, (day, p_idx) is no longer valid
                shares_entity = (
                    set(ev.section_ids).intersection(other_ev.section_ids) or
                    set(ev.teacher_ids).intersection(other_ev.teacher_ids)
                )

                if shares_entity and (day, p_idx) in domains[other_id]:
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

            # 5. Undo Assignment and restore pruned domains
            del assigned[u_id]
            grid.remove(assign1)
            if assign2:
                grid.remove(assign2)

            for other_id, restored_slots in pruned.items():
                domains[other_id].extend(restored_slots)

        return False, {
            "reason": "BACKTRACK_EXHAUSTED",
            "event_id": ev.id,
            "subject": ev.subject,
            "sections": ev.section_ids,
            "teachers": ev.teacher_ids
        }
