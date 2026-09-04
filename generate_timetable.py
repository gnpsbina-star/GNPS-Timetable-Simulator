#!/usr/bin/env python3
"""
CLI Command Center for School Timetable Generation, Audit, and Synchronization.
Usage:
    python3 generate_timetable.py --verify
    python3 generate_timetable.py --audit
    python3 generate_timetable.py --extract-config
    python3 generate_timetable.py --generate timetable_config.json
"""

import sys
import os
import argparse
import json

from engine.models import SchoolConfig, Teacher, ClassSection, Room, Event
from engine.generator import TimetableGenerator
from engine.precheck import audit_capacity

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def verify_current_timetable():
    print("🔍 Auditing deployed timetable for clashes...")
    json_path = os.path.join(BASE_DIR, "timetable.json")
    if not os.path.exists(json_path):
        print("❌ Error: timetable.json not found.")
        return False

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Check for clashes in deployed data
    teacher_slots = {}
    clashes = []

    for c in data.get("classes", []):
        c_name = c.get("class_name")
        for day, periods in c.get("schedule", {}).items():
            for p in periods:
                teach = p.get("teacher")
                subj = p.get("subject")
                p_idx = p.get("period_index")
                p_name = p.get("period_name")
                if teach and subj not in ["Lunch", "Prayer"]:
                    teachers = [t.strip() for t in teach.split("/") if t.strip()]
                    for t in teachers:
                        key = (t, day, p_idx)
                        if key not in teacher_slots:
                            teacher_slots[key] = []
                        teacher_slots[key].append({
                            "class": c_name,
                            "subject": subj,
                            "period": p_name
                        })

    for (t, day, p_idx), entries in teacher_slots.items():
        if len(entries) > 1:
            # Check if this is a legitimate clubbed class (same subject or related)
            subjects = {e["subject"] for e in entries}
            classes = [e["class"] for e in entries]
            if len(subjects) == 1:
                # Clubbed class
                pass
            else:
                clashes.append({
                    "teacher": t,
                    "day": day,
                    "period_index": p_idx,
                    "entries": entries
                })

    print(f"✅ Total Classes Audited: {len(data.get('classes', []))}")
    print(f"✅ Total Teachers Audited: {len(data.get('teachers', []))}")
    print(f"✅ Total Clashes: {len(clashes)}")
    if clashes:
        print("\n⚠️ Clashes detected:")
        for cl in clashes:
            print(f"  • {cl['teacher']} on {cl['day']} (Period {cl['period_index']}): {cl['entries']}")
        return False
    else:
        print("🎉 Timetable is 100% CLASH-FREE!")
        return True

def extract_config():
    """Extracts master configuration and event quotas from current timetable.json into an editable template."""
    json_path = os.path.join(BASE_DIR, "timetable.json")
    if not os.path.exists(json_path):
        print("❌ Error: timetable.json not found.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cfg_out = os.path.join(BASE_DIR, "timetable_config.json")
    
    # Extract unique teachers and calculate their average weekly load
    teacher_export_path = os.path.join(BASE_DIR, "timetable_teachers.json")
    teacher_loads = {}
    if os.path.exists(teacher_export_path):
        with open(teacher_export_path, "r", encoding="utf-8") as f:
            t_data = json.load(f)
            for t_name, info in t_data.items():
                teacher_loads[t_name] = info.get("total_weekly_teaching_periods", 30)

    teachers_list = []
    for t_name in data.get("teachers", []):
        is_spec = any(s in t_name.lower() for s in ["geetesh", "sports", "art", "music", "comp"])
        teachers_list.append({
            "id": t_name,
            "name": t_name,
            "max_weekly_periods": max(teacher_loads.get(t_name, 30), 34),
            "max_daily_periods": 6,
            "is_specialist": is_spec,
            "unavailable_slots": []
        })

    classes_list = []
    events_list = []
    ev_counter = 1

    first_class = data["classes"][0] if data.get("classes") else {}
    periods_def = first_class.get("period_definitions", [])

    for c in data.get("classes", []):
        c_name = c.get("class_name")
        c_id = c_name.replace(" ", "_")
        classes_list.append({
            "id": c_id,
            "name": c_name,
            "class_teacher": c.get("class_teacher", ""),
            "wing": "Senior" if any(x in c_name for x in ["9", "10", "11", "12"]) else ("Middle" if any(x in c_name for x in ["6", "7", "8"]) else "Primary")
        })

        # Calculate subject weekly quotas for this class
        subject_counts = {}
        for day, periods in c.get("schedule", {}).items():
            for p in periods:
                s = p.get("subject")
                t = p.get("teacher")
                if s and s not in ["Lunch", "Prayer", "CYCLE TEST", "CCA"]:
                    key = (s, t)
                    subject_counts[key] = subject_counts.get(key, 0) + 1

        for (s, t), count in subject_counts.items():
            events_list.append({
                "id": f"EV_{ev_counter}",
                "subject": s,
                "teacher_ids": [t] if t else [],
                "section_ids": [c_id],
                "weekly_quota": count,
                "room_type": "Classroom",
                "duration": 1
            })
            ev_counter += 1

    config_template = {
        "config": {
            "academic_year": data.get("academic_year", "2026-27"),
            "title": data.get("title", "School Time Table"),
            "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
            "periods_per_day": len(periods_def),
            "period_definitions": periods_def,
            "school_timings": data.get("school_timings", [])
        },
        "teachers": teachers_list,
        "classes": classes_list,
        "rooms": [
            {"id": "R_COMP", "name": "Computer Lab", "room_type": "ComputerLab", "capacity": 40},
            {"id": "R_SCI", "name": "Science Lab", "room_type": "ScienceLab", "capacity": 40},
            {"id": "R_GROUND", "name": "Playground", "room_type": "Ground", "capacity": 100}
        ],
        "events": events_list,
        "baskets": []
    }

    with open(cfg_out, "w", encoding="utf-8") as f:
        json.dump(config_template, f, indent=2, ensure_ascii=False)
    print(f"✨ Extracted clean editable template to: {cfg_out}")
    print(f"   • {len(teachers_list)} Teachers")
    print(f"   • {len(classes_list)} Classes")
    print(f"   • {len(events_list)} Unique Lesson Allocations")

def generate_from_config(config_path: str):
    print(f"🚀 Initializing Timetable Generation from: {config_path}")
    generator = TimetableGenerator.from_json(config_path)

    print("📊 Step 1: Performing Pre-solver Capacity & Bottleneck Audit...")
    audit = generator.pre_audit()
    print(f"   • Feasible: {audit.is_feasible}")
    for w in audit.warnings[:5]:
        print(f"   ⚠️ Warning: {w}")
    if len(audit.warnings) > 5:
        print(f"   ⚠️ ...and {len(audit.warnings)-5} more warnings.")

    if not audit.is_feasible:
        print("\n❌ FATAL AUDIT ERRORS:")
        for err in audit.errors:
            print(f"   ❌ {err}")
        return False

    print("\n⚙️ Step 2: Running Constraint Satisfaction Problem (CSP) Solver...")
    result = generator.generate(time_limit=45)
    print(f"   • Solver Status: {result.success}")
    print(f"   • {result.message}")

    if result.success and result.grid:
        print("\n💾 Step 3: Exporting to JSON, SQLite, CSV, and substitution matrix...")
        exported = generator.export(result.grid, BASE_DIR)
        for name, path in exported.items():
            print(f"   ✅ Exported: {name}")
        print("\n🎉 GENERATION COMPLETE! All portal views updated.")
        return True
    else:
        print(f"\n❌ Solver failed to find a feasible solution. Conflict details: {result.conflict_details}")
        return False

def main():
    parser = argparse.ArgumentParser(description="School Timetable Generator & Audit Center")
    parser.add_argument("--verify", action="store_true", help="Audit current timetable for collisions")
    parser.add_argument("--extract-config", action="store_true", help="Extract current timetable to editable JSON config")
    parser.add_argument("--generate", type=str, help="Generate new timetable from JSON config file")

    args = parser.parse_args()

    if args.verify:
        verify_current_timetable()
    elif args.extract_config:
        extract_config()
    elif args.generate:
        generate_from_config(args.generate)
    else:
        verify_current_timetable()

if __name__ == "__main__":
    main()
