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
    
    # Extract unique teachers and calculate their actual weekly and daily loads
    teacher_export_path = os.path.join(BASE_DIR, "timetable_teachers.json")
    teacher_loads = {}
    if os.path.exists(teacher_export_path):
        with open(teacher_export_path, "r", encoding="utf-8") as f:
            t_data = json.load(f)
            for t_name, info in t_data.items():
                teacher_loads[t_name] = info.get("total_weekly_teaching_periods", 30)

    # Compute maximum daily lessons for each teacher
    daily_counts = {}
    for c in data.get("classes", []):
        for day, periods in c.get("schedule", {}).items():
            for p in periods:
                t = p.get("teacher", "")
                s = p.get("subject", "")
                if t and s and s not in ["Morning Assembly", "Lunch", "Prayer", "Lunch _ Class Teacher", "CYCLE TEST", "CCA", "Recess", "Assembly"]:
                    for teach in [x.strip() for x in t.split("/") if x.strip()]:
                        daily_counts.setdefault((teach, day), 0)
                        daily_counts[(teach, day)] += 1

    max_daily_by_teacher = {}
    for (teach, day), cnt in daily_counts.items():
        max_daily_by_teacher[teach] = max(max_daily_by_teacher.get(teach, 0), cnt)

    teachers_list = []
    for t_name in data.get("teachers", []):
        is_spec = any(s in t_name.lower() for s in ["geetesh", "sports", "art", "music", "comp"])
        actual_max_daily = max_daily_by_teacher.get(t_name, 6)
        teachers_list.append({
            "id": t_name,
            "name": t_name,
            "max_weekly_periods": teacher_loads.get(t_name, 34),
            "max_daily_periods": max(actual_max_daily, 6),
            "is_specialist": is_spec,
            "unavailable_slots": []
        })

    classes_list = []
    events_list = []
    ev_counter = 1

    first_class = data["classes"][0] if data.get("classes") else {}
    periods_def = first_class.get("period_definitions", [])

    # Group slot assignments across all classes to accurately detect clubbed classes
    # (e.g. combined Class 12 Comm & Arts for Economics, or Class 11 & 12 for Games)
    clubbed_slots = {}
    for c in data.get("classes", []):
        c_name = c.get("class_name")
        c_id = c_name.replace(" ", "_")
        classes_list.append({
            "id": c_id,
            "name": c_name,
            "class_teacher": c.get("class_teacher", ""),
            "wing": "Senior" if any(x in c_name for x in ["9", "10", "11", "12"]) else ("Middle" if any(x in c_name for x in ["6", "7", "8"]) else "Primary")
        })

        for day, periods in c.get("schedule", {}).items():
            for p in periods:
                s = p.get("subject")
                t = p.get("teacher")
                p_idx = p.get("period_index")
                if s and t and s not in ["Lunch", "Prayer", "CYCLE TEST", "CCA", "Morning Assembly"]:
                    key = (t, s, day, p_idx)
                    clubbed_slots.setdefault(key, set()).add(c_id)

    # Group by (teacher, subject, section_ids_tuple) to create single events for clubbed classes
    event_groups = {}
    for (t, s, day, p_idx), sections in clubbed_slots.items():
        sec_key = tuple(sorted(list(sections)))
        group_key = (t, s, sec_key)
        event_groups.setdefault(group_key, []).append([day, p_idx])

    for (t, s, sec_tuple), slots in event_groups.items():
        r_type = "Activity Hall" if s == "Yoga" else ("Ground" if s in ["Games", "Game", "PE"] else "Classroom")
        is_joint = len(sec_tuple) > 1
        joint_label = None
        if is_joint:
            clean_secs = [s_id.replace("CLASS_", "Class ").replace("_", " ") for s_id in sec_tuple]
            joint_label = f"{' + '.join(clean_secs)} {s}"
        events_list.append({
            "id": f"EV_{ev_counter}",
            "subject": s,
            "teacher_ids": [t] if t else [],
            "section_ids": list(sec_tuple),
            "weekly_quota": len(slots),
            "room_type": r_type,
            "duration": 1,
            "locked_slots": slots,
            "is_joint": is_joint,
            "joint_label": joint_label
        })
        ev_counter += 1

    # Read existing config to preserve rich period definitions, subjects, and custom settings
    existing_cfg = {}
    if os.path.exists(cfg_out):
        try:
            with open(cfg_out, "r", encoding="utf-8") as f:
                existing_cfg = json.load(f)
        except Exception:
            pass

    rich_config = existing_cfg.get("config", {
        "academic_year": data.get("academic_year", "2026-27"),
        "title": data.get("title", "School Time Table"),
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        "periods_per_day": len(periods_def),
        "period_definitions": periods_def,
        "school_timings": data.get("school_timings", []),
        "enforce_class_teacher_p1": True
    })

    # Ensure periods_def has is_lunch, is_assembly, and Saturday early dispersal
    for p in rich_config.get("period_definitions", []):
        p_idx = p.get("period_index")
        if p_idx == 0:
            p["is_assembly"] = True
            p["is_lunch"] = False
        elif p_idx == 4 or "lunch" in p.get("name", "").lower():
            p["is_lunch"] = True
            p["is_assembly"] = False
        else:
            p["is_lunch"] = False
            p["is_assembly"] = False
        if p_idx in [6, 7, 8]:
            if "wing_schedule" in p and "saturday" in p["wing_schedule"]:
                p["wing_schedule"]["saturday"]["middle"] = "off"
                p["wing_schedule"]["saturday"]["primary"] = "off"

    # Normalize teacher weekly caps to cover assigned curricular load
    for t in teachers_list:
        t_key = t["name"].lower().strip()
        load = sum(
            e["weekly_quota"] * e.get("duration", 1)
            for e in events_list
            if any(tid.lower().strip() == t_key for tid in e["teacher_ids"])
        )
        if load > t["max_weekly_periods"]:
            t["max_weekly_periods"] = load

    config_template = {
        "config": rich_config,
        "teachers": teachers_list,
        "classes": classes_list,
        "rooms": [
            {"id": "R_COMP", "name": "Computer Lab", "room_type": "ComputerLab", "capacity": 40, "max_concurrent_classes": 1, "building": "Main Block"},
            {"id": "R_SCI", "name": "Science Lab", "room_type": "ScienceLab", "capacity": 40, "max_concurrent_classes": 1, "building": "Science Wing"},
            {"id": "R_GROUND", "name": "Playground", "room_type": "Ground", "capacity": 100, "max_concurrent_classes": 3, "building": "Sports Complex"},
            {"id": "R_ACT", "name": "Activity Hall", "room_type": "Activity Hall", "capacity": 60, "max_concurrent_classes": 2, "building": "Auditorium Wing"}
        ],
        "events": events_list,
        "baskets": existing_cfg.get("baskets", [])
    }
    if "subjects" in existing_cfg:
        config_template["subjects"] = existing_cfg["subjects"]

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
