"""
Unified Timetable Generator Facade.
Loads configurations, executes feasibility audit, invokes CSP / OR-Tools solver,
validates zero clashes, and exports results.
"""

from typing import Dict, List, Optional, Any
import os
import json
from .models import (
    SchoolConfig,
    Teacher,
    ClassSection,
    Room,
    Event,
    ElectiveBasket,
    TimetableGrid
)
from .precheck import audit_capacity, AuditReport
from .ortools_solver import ORToolsSolver
from .csp_solver import CSPSolverResult
from .exporter import export_all

class TimetableGenerator:
    def __init__(
        self,
        config: SchoolConfig,
        teachers: Dict[str, Teacher],
        classes: Dict[str, ClassSection],
        rooms: Dict[str, Room],
        events: List[Event],
        baskets: Optional[List[ElectiveBasket]] = None
    ):
        self.config = config
        self.teachers = teachers
        self.classes = classes
        self.rooms = rooms
        self.events = events
        self.baskets = baskets or []

    @classmethod
    def from_json(cls, config_path: str) -> "TimetableGenerator":
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimetableGenerator":
        cfg_data = data.get("config", {})
        config = SchoolConfig(
            academic_year=cfg_data.get("academic_year", "2026-27"),
            title=cfg_data.get("title", "School Time Table"),
            days=cfg_data.get("days", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]),
            periods_per_day=cfg_data.get("periods_per_day", 8),
            period_definitions=cfg_data.get("period_definitions", []),
            school_timings=cfg_data.get("school_timings", []),
            wing_bell_schedules=cfg_data.get("wing_bell_schedules", {}),
            fixed_locks=cfg_data.get("fixed_locks", []),
            enforce_class_teacher_p1=cfg_data.get("enforce_class_teacher_p1", True)
        )

        teachers = {}
        for t in data.get("teachers", []):
            teachers[t["id"]] = Teacher(
                id=t["id"],
                name=t["name"],
                max_weekly_periods=t.get("max_weekly_periods", 34),
                max_daily_periods=t.get("max_daily_periods", 6),
                is_specialist=t.get("is_specialist", False),
                unavailable_slots={tuple(s) for s in t.get("unavailable_slots", [])},
                subjects=t.get("subjects", [])
            )

        classes = {}
        for c in data.get("classes", []):
            classes[c["id"]] = ClassSection(
                id=c["id"],
                name=c["name"],
                wing=c.get("wing", "Middle"),
                class_teacher=c.get("class_teacher", ""),
                home_room=c.get("home_room", "")
            )

        rooms = {}
        for r in data.get("rooms", []):
            rooms[r["id"]] = Room.from_dict(r)

        events = []
        for e in data.get("events", []):
            events.append(Event.from_dict(e))

        baskets = []
        for b in data.get("baskets", []):
            b_events = [ev for ev in events if ev.basket_id == b["id"]]
            baskets.append(ElectiveBasket(
                id=b["id"],
                name=b["name"],
                section_ids=b.get("section_ids", []),
                events=b_events,
                weekly_quota=b.get("weekly_quota", 6)
            ))

        return cls(config, teachers, classes, rooms, events, baskets)

    def pre_audit(self) -> AuditReport:
        return audit_capacity(self.config, self.teachers, self.classes, self.rooms, self.events)

    def generate(self, time_limit: int = 30) -> CSPSolverResult:
        # 1. Run Pre-check
        audit = self.pre_audit()
        if not audit.is_feasible:
            return CSPSolverResult(
                False, None,
                f"Feasibility Audit Failed: {'; '.join(audit.errors)}"
            )

        # 2. Invoke Solver
        solver = ORToolsSolver(
            config=self.config,
            teachers=self.teachers,
            classes=self.classes,
            rooms=self.rooms,
            events=self.events,
            baskets=self.baskets,
            time_limit_seconds=time_limit
        )
        result = solver.solve()

        # 3. Post-verification
        if result.success and result.grid:
            clashes = result.grid.detect_all_clashes()
            if clashes:
                result.success = False
                result.message = f"Validation Error: Solver produced {len(clashes)} internal clashes."
                result.conflict_details = {"clashes": clashes}

        return result

    def export(self, grid: TimetableGrid, output_dir: str) -> Dict[str, str]:
        return export_all(grid, self.teachers, self.classes, output_dir, rooms=self.rooms)
