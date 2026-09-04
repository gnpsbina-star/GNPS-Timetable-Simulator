"""
Google OR-Tools CP-SAT Solver Integration.
Formulates the Timetable Creation Problem as a Constraint Satisfaction / Optimization problem.
When OR-Tools is not installed, seamlessly falls back to the pure-Python CSP Solver.
"""

from typing import List, Dict, Set, Tuple, Optional, Any
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
from .csp_solver import CSPSolverResult, CSPSolver

ORTOOLS_AVAILABLE = False
try:
    from ortools.sat.python import cp_model
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False

class ORToolsSolver:
    def __init__(
        self,
        config: SchoolConfig,
        teachers: Dict[str, Teacher],
        classes: Dict[str, ClassSection],
        rooms: Dict[str, Room],
        events: List[Event],
        baskets: Optional[List[ElectiveBasket]] = None,
        time_limit_seconds: int = 30
    ):
        self.config = config
        self.teachers = teachers
        self.classes = classes
        self.rooms = rooms
        self.events = events
        self.baskets = baskets or []
        self.time_limit = time_limit_seconds

    def solve(self) -> CSPSolverResult:
        if not ORTOOLS_AVAILABLE:
            # Fall back to high-performance pure-Python CSP solver
            fallback_solver = CSPSolver(
                config=self.config,
                teachers=self.teachers,
                classes=self.classes,
                rooms=self.rooms,
                events=self.events,
                baskets=self.baskets
            )
            res = fallback_solver.solve()
            res.message = f"[Pure-Python Engine] {res.message}"
            return res

        model = cp_model.CpModel()
        grid = TimetableGrid(self.config)

        # 1. Collect valid slots
        valid_slots = []
        for d_idx, day in enumerate(self.config.days):
            for p_def in self.config.period_definitions:
                p_idx = p_def.get("period_index", 0)
                if not p_def.get("is_lunch") and not p_def.get("is_assembly"):
                    valid_slots.append((day, p_idx))

        # 2. Decision Variables: X[e_id, slot_idx]
        x: Dict[Tuple[str, int, str, int], cp_model.IntVar] = {}
        for ev in self.events:
            for (day, p_idx) in valid_slots:
                var_name = f"x_{ev.id}_{day}_{p_idx}"
                x[(ev.id, day, p_idx)] = model.NewBoolVar(var_name)

        # 3. Hard Constraint: Weekly Quota per Event
        for ev in self.events:
            model.Add(
                sum(x[(ev.id, day, p_idx)] for (day, p_idx) in valid_slots) == ev.weekly_quota
            )

        # 4. Hard Constraint: No Section Clashes
        for sec_id in self.classes:
            sec_events = [ev for ev in self.events if sec_id in ev.section_ids]
            for (day, p_idx) in valid_slots:
                model.Add(
                    sum(x[(ev.id, day, p_idx)] for ev in sec_events) <= 1
                )

        # 5. Hard Constraint: No Teacher Clashes
        for t_id in self.teachers:
            t_events = [ev for ev in self.events if t_id in ev.teacher_ids]
            for (day, p_idx) in valid_slots:
                # Clubbed classes sharing same event ID are represented once in t_events
                model.Add(
                    sum(x[(ev.id, day, p_idx)] for ev in t_events) <= 1
                )

        # 6. Hard Constraint: Teacher Unavailability
        for t_id, teacher in self.teachers.items():
            t_events = [ev for ev in self.events if t_id in ev.teacher_ids]
            for (day, p_idx) in teacher.unavailable_slots:
                if (day, p_idx) in valid_slots:
                    for ev in t_events:
                        model.Add(x[(ev.id, day, p_idx)] == 0)

        # 7. Hard Constraint: Pinned Slots
        for ev in self.events:
            for (day, p_idx) in ev.locked_slots:
                if (ev.id, day, p_idx) in x:
                    model.Add(x[(ev.id, day, p_idx)] == 1)

        # 8. Solve
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.time_limit
        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            for ev in self.events:
                for (day, p_idx) in valid_slots:
                    if solver.Value(x[(ev.id, day, p_idx)]) == 1:
                        assign = SlotAssignment(
                            event_id=ev.id,
                            day=day,
                            period_index=p_idx,
                            subject=ev.subject,
                            teacher_ids=ev.teacher_ids,
                            section_ids=ev.section_ids,
                            room_type=ev.room_type,
                            is_locked=ev.is_locked
                        )
                        grid.assign(assign)

            return CSPSolverResult(
                True, grid,
                f"[OR-Tools CP-SAT] Solved to {'OPTIMAL' if status == cp_model.OPTIMAL else 'FEASIBLE'} in {solver.WallTime():.2f}s."
            )
        else:
            return CSPSolverResult(
                False, None,
                f"[OR-Tools CP-SAT] Infeasible. No solution exists satisfying all constraints."
            )
