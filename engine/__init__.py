"""
School Timetable Creation Engine
Supports Constraint Satisfaction Problem (CSP) solving, CBSE elective baskets,
class clubbing, specialist bottleneck audits, and full-fidelity export.
"""

from .models import (
    SchoolConfig,
    Teacher,
    ClassSection,
    Room,
    Event,
    TimetableGrid,
    DayPeriod
)
from .precheck import audit_capacity
from .generator import TimetableGenerator

__all__ = [
    'SchoolConfig',
    'Teacher',
    'ClassSection',
    'Room',
    'Event',
    'TimetableGrid',
    'DayPeriod',
    'audit_capacity',
    'TimetableGenerator'
]
