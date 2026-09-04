"""
Timetable Exporter Module.
Exports generated TimetableGrid to JSON, SQLite, CSV, and HTML-embedded formats.
Maintains 100% backward compatibility with index.html, free_teachers.html, and update_online.sh.
"""

import os
import json
import sqlite3
import csv
from typing import Dict, Any, List, Set
from .models import TimetableGrid, SchoolConfig, Teacher, ClassSection

def export_all(
    grid: TimetableGrid,
    teachers: Dict[str, Teacher],
    classes: Dict[str, ClassSection],
    base_dir: str
) -> Dict[str, str]:
    exported_files = {}

    config = grid.config
    days = config.days
    periods = config.period_definitions

    # 1. Build Flat Entries & Classes List
    flat_entries = []
    classes_list = []
    all_teachers_set = set()
    all_subjects_set = set()

    entry_id = 1
    for c_id, c in classes.items():
        c_name = c.name
        class_teacher = c.class_teacher
        if class_teacher:
            all_teachers_set.add(class_teacher)

        days_schedule = {}
        for day in days:
            day_periods = []
            for p_def in periods:
                p_idx = p_def.get("period_index", 0)
                p_name = p_def.get("name", f"Period {p_idx}")
                p_time = p_def.get("time", "")

                assign = grid.section_grid.get((c_id, day, p_idx))
                subj = assign.subject if assign else ""
                teach = "/".join(assign.teacher_ids) if assign else ""
                raw_val = f"{subj}_{teach}" if (subj and teach) else subj

                if p_def.get("is_lunch", False):
                    subj = "Lunch"
                    teach = class_teacher
                    raw_val = f"Lunch _ {class_teacher}"

                if subj:
                    all_subjects_set.add(subj)
                if teach:
                    for t in assign.teacher_ids if assign else [teach]:
                        all_teachers_set.add(t)

                period_obj = {
                    "period_index": p_idx,
                    "period_name": p_name,
                    "period_time": p_time,
                    "raw_value": raw_val,
                    "subject": subj,
                    "teacher": teach
                }
                day_periods.append(period_obj)

                flat_entries.append({
                    "entry_id": entry_id,
                    "class_name": c_name,
                    "class_teacher": class_teacher,
                    "day": day,
                    "period_index": p_idx,
                    "period_name": p_name,
                    "period_time": p_time,
                    "raw_value": raw_val,
                    "subject": subj,
                    "teacher": teach
                })
                entry_id += 1

            days_schedule[day] = day_periods

        classes_list.append({
            "class_name": c_name,
            "class_teacher": class_teacher,
            "period_definitions": periods,
            "schedule": days_schedule
        })

    # 2. Export Master timetable.json
    master_data = {
        "academic_year": config.academic_year,
        "title": config.title,
        "school_timings": config.school_timings,
        "summary": {
            "total_classes": len(classes),
            "total_teachers": len(all_teachers_set),
            "total_subjects": len(all_subjects_set),
            "total_scheduled_periods": len(flat_entries)
        },
        "teachers": sorted(list(all_teachers_set)),
        "subjects": sorted(list(all_subjects_set)),
        "classes": classes_list
    }

    json_path = os.path.join(base_dir, "timetable.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(master_data, f, indent=2, ensure_ascii=False)
    exported_files["timetable.json"] = json_path

    # 3. Export Teacher-Centric timetable_teachers.json
    teacher_export = {}
    for t_id, t in teachers.items():
        t_name = t.name
        t_classes = set()
        t_subjects = set()
        weekly_sched = {}
        unique_periods = 0

        for day in days:
            day_list = []
            for p_def in periods:
                p_idx = p_def.get("period_index", 0)
                assigns = grid.teacher_grid.get((t_id, day, p_idx), [])
                if assigns:
                    a = assigns[0]
                    t_subjects.add(a.subject)
                    for sec in a.section_ids:
                        t_classes.add(classes[sec].name if sec in classes else sec)
                    day_list.append({
                        "class_name": ", ".join([classes[s].name if s in classes else s for s in a.section_ids]),
                        "period_index": p_idx,
                        "period_name": p_def.get("name", f"Period {p_idx}"),
                        "period_time": p_def.get("time", ""),
                        "subject": a.subject,
                        "raw_value": f"{a.subject}_{t_name}"
                    })
                    if a.subject not in ["Lunch", "Prayer"]:
                        unique_periods += 1

            weekly_sched[day] = day_list

        teacher_export[t_name] = {
            "teacher_name": t_name,
            "is_class_teacher_of": [c.name for c in classes.values() if c.class_teacher == t_name],
            "total_weekly_teaching_periods": unique_periods,
            "classes": sorted(list(t_classes)),
            "subjects": sorted(list(t_subjects)),
            "weekly_schedule": weekly_sched
        }

    teacher_json_path = os.path.join(base_dir, "timetable_teachers.json")
    with open(teacher_json_path, "w", encoding="utf-8") as f:
        json.dump(teacher_export, f, indent=2, ensure_ascii=False)
    exported_files["timetable_teachers.json"] = teacher_json_path

    # 4. Export Free Teachers Substitution Pool (free_teachers.json)
    free_data = {
        "total_active_teachers": len(teachers),
        "days": days,
        "periods": [p.get("name") for p in periods if not p.get("is_lunch")],
        "slot_availability": {}
    }

    for day in days:
        free_data["slot_availability"][day] = {}
        for p_def in periods:
            p_idx = p_def.get("period_index", 0)
            p_name = p_def.get("name", f"Period {p_idx}")
            if p_def.get("is_lunch"):
                continue

            occupied_teachers = {
                t_id for (t_id, d, p) in grid.teacher_grid
                if d == day and p == p_idx
            }
            free_list = [
                teachers[t_id].name for t_id in teachers
                if t_id not in occupied_teachers and teachers[t_id].is_available(day, p_idx)
            ]
            free_data["slot_availability"][day][p_name] = sorted(free_list)

    free_json_path = os.path.join(base_dir, "free_teachers.json")
    with open(free_json_path, "w", encoding="utf-8") as f:
        json.dump(free_data, f, indent=2, ensure_ascii=False)
    exported_files["free_teachers.json"] = free_json_path

    # 5. Export timetable_entries.csv
    csv_path = os.path.join(base_dir, "timetable_entries.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "entry_id", "class_name", "class_teacher", "day",
            "period_index", "period_name", "period_time", "raw_value", "subject", "teacher"
        ])
        writer.writeheader()
        writer.writerows(flat_entries)
    exported_files["timetable_entries.csv"] = csv_path

    # 6. Export SQLite Database
    db_path = os.path.join(base_dir, "timetable.sqlite")
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("CREATE TABLE school_timings (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, timings TEXT)")
    for st in config.school_timings:
        cur.execute("INSERT INTO school_timings (category, timings) VALUES (?, ?)", (st.get("category"), st.get("timings")))

    cur.execute("CREATE TABLE classes (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, class_teacher TEXT)")
    for c in classes.values():
        cur.execute("INSERT INTO classes (name, class_teacher) VALUES (?, ?)", (c.name, c.class_teacher))

    cur.execute("CREATE TABLE teachers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
    for t_name in sorted(list(all_teachers_set)):
        cur.execute("INSERT INTO teachers (name) VALUES (?)", (t_name,))

    cur.execute("CREATE TABLE subjects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
    for s_name in sorted(list(all_subjects_set)):
        cur.execute("INSERT INTO subjects (name) VALUES (?)", (s_name,))

    cur.execute("""CREATE TABLE schedule_entries (
        id INTEGER PRIMARY KEY,
        class_name TEXT,
        class_teacher TEXT,
        day TEXT,
        period_index INTEGER,
        period_name TEXT,
        period_time TEXT,
        raw_value TEXT,
        subject TEXT,
        teacher TEXT
    )""")
    for item in flat_entries:
        cur.execute("""INSERT INTO schedule_entries
            (id, class_name, class_teacher, day, period_index, period_name, period_time, raw_value, subject, teacher)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
            item["entry_id"], item["class_name"], item["class_teacher"],
            item["day"], item["period_index"], item["period_name"],
            item["period_time"], item["raw_value"], item["subject"], item["teacher"]
        ))

    cur.execute("CREATE INDEX idx_sched_class ON schedule_entries(class_name)")
    cur.execute("CREATE INDEX idx_sched_teacher ON schedule_entries(teacher)")
    cur.execute("CREATE INDEX idx_sched_day ON schedule_entries(day)")
    cur.execute("CREATE INDEX idx_sched_subject ON schedule_entries(subject)")
    conn.commit()
    conn.close()
    exported_files["timetable.sqlite"] = db_path

    return exported_files
