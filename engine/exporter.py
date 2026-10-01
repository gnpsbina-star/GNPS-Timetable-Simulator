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
from .models import TimetableGrid, SchoolConfig, Teacher, ClassSection, Room

def export_all(
    grid: TimetableGrid,
    teachers: Dict[str, Teacher],
    classes: Dict[str, ClassSection],
    base_dir: str,
    rooms: Dict[str, Room] = None
) -> Dict[str, str]:
    exported_files = {}

    config = grid.config
    days = config.days
    periods = config.period_definitions

    # 1. Build Flat Entries & Classes List
    flat_entries = []
    classes_list = []
    all_teachers_set = set(t.name for t in teachers.values())
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

                assigns = grid.section_grid_all.get((c_id, day, p_idx), [])
                if not assigns:
                    assign = grid.section_grid.get((c_id, day, p_idx))
                    if assign:
                        assigns = [assign]

                is_split = len(assigns) > 1
                is_joint = bool(assigns and assigns[0].is_joint)
                joint_label = assigns[0].joint_label if (assigns and assigns[0].joint_label) else None
                parallel_group_id = assigns[0].parallel_group_id if assigns else None
                elective_basket = assigns[0].elective_basket if assigns else None
                room_type = assigns[0].room_type if (assigns and not is_split) else ("Multiple" if is_split else "Classroom")

                parallel_split = []
                if is_split:
                    subj = " / ".join(a.subject for a in assigns)
                    teach = " / ".join("/".join(a.teacher_ids) for a in assigns)
                    raw_val = f"PARALLEL: {subj}"
                    for a in assigns:
                        if a.subject:
                            all_subjects_set.add(a.subject)
                        for t in a.teacher_ids:
                            all_teachers_set.add(t)
                        parallel_split.append({
                            "event_id": a.event_id,
                            "subject": a.subject,
                            "teacher_ids": a.teacher_ids,
                            "teacher": "/".join(a.teacher_ids),
                            "room_type": a.room_type,
                            "room_id": a.room_id or a.room_type  # Fallback: use room_type if physical room_id not assigned
                        })
                elif assigns:
                    a = assigns[0]
                    subj = a.subject
                    teach = "/".join(a.teacher_ids)
                    raw_val = f"{subj}_{teach}" if (subj and teach) else subj
                    if subj:
                        all_subjects_set.add(subj)
                    for t in a.teacher_ids:
                        all_teachers_set.add(t)
                else:
                    subj = ""
                    teach = ""
                    raw_val = ""

                if p_def.get("is_lunch", False):
                    subj = "Lunch"
                    teach = class_teacher
                    raw_val = f"Lunch _ {class_teacher}"
                    is_joint = False
                    joint_label = None
                elif p_def.get("is_assembly", False):
                    subj = "Morning Assembly"
                    teach = ""
                    raw_val = "Morning Assembly"
                    is_joint = False
                    joint_label = None

                period_obj = {
                    "period_index": p_idx,
                    "period_name": p_name,
                    "period_time": p_time,
                    "raw_value": raw_val,
                    "subject": subj,
                    "teacher": teach,
                    "is_joint": is_joint,
                    "joint_label": joint_label,
                    "parallel_group_id": parallel_group_id,
                    "elective_basket": elective_basket,
                    "room_type": room_type,
                    "is_parallel_split": is_split,
                    "parallel_split": parallel_split
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
                    "teacher": teach,
                    "is_joint": is_joint,
                    "joint_label": joint_label,
                    "parallel_group_id": parallel_group_id,
                    "elective_basket": elective_basket
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
                        "raw_value": f"{a.subject}_{t_name}",
                        "is_joint": a.is_joint,
                        "joint_label": a.joint_label,
                        "parallel_group_id": a.parallel_group_id,
                        "elective_basket": a.elective_basket,
                        "room_type": a.room_type
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
        "periods": [
            {
                "index": p.get("period_index", 0),
                "id": f"P{p.get('period_index', 0)}",
                "name": p.get("name", f"Period {p.get('period_index', 0)}"),
                "time": p.get("time", "")
            }
            for p in periods
        ],
        "roster": {},
        "slot_availability": {}
    }

    for day in days:
        free_data["roster"][day] = {}
        free_data["slot_availability"][day] = {}
        for p_def in periods:
            p_idx = p_def.get("period_index", 0)
            p_name = p_def.get("name", f"Period {p_idx}")
            if p_def.get("is_lunch"):
                continue

            occupied_teachers = {}
            for (t_id, d, p), assigns in grid.teacher_grid.items():
                if d == day and p == p_idx:
                    t_name = teachers[t_id].name if t_id in teachers else t_id
                    a = assigns[0]
                    c_name = ", ".join([classes[s].name if s in classes else s for s in a.section_ids])
                    occupied_teachers[t_name] = {
                        "class_name": c_name,
                        "subject": a.subject,
                        "raw": f"{a.subject}_{t_name}"
                    }

            free_candidates = []
            for t_id, t in teachers.items():
                t_name = t.name
                if (t_id, day, p_idx) not in grid.teacher_grid:
                    if t.is_available(day, p_idx):
                        t_info = teacher_export.get(t_name, {})
                        free_candidates.append({
                            "name": t_name,
                            "is_class_teacher_of": t_info.get("is_class_teacher_of", []),
                            "subjects": t_info.get("subjects", []),
                            "classes": t_info.get("classes", []),
                            "weekly_load": t_info.get("total_weekly_teaching_periods", 0)
                        })

            free_candidates.sort(key=lambda x: x["name"])
            free_names = [c["name"] for c in free_candidates]

            free_data["slot_availability"][day][p_name] = free_names
            free_data["roster"][day][p_name] = {
                "period_info": {
                    "index": p_idx,
                    "id": f"P{p_idx}",
                    "name": p_name,
                    "time": p_def.get("time", "")
                },
                "free_count": len(free_candidates),
                "busy_count": len(occupied_teachers),
                "busy_teachers": occupied_teachers,
                "free_teachers": free_candidates
            }

    free_json_path = os.path.join(base_dir, "free_teachers.json")
    with open(free_json_path, "w", encoding="utf-8") as f:
        json.dump(free_data, f, indent=2, ensure_ascii=False)
    exported_files["free_teachers.json"] = free_json_path

    # 5. Export Room-Centric timetable_rooms.json
    room_export = {}
    if rooms:
        for r_id, r in rooms.items():
            r_sched = {}
            total_bookings = 0
            for day in days:
                day_periods = []
                for p_def in periods:
                    p_idx = p_def.get("period_index", 0)
                    assigns = grid.room_type_grid.get((r.room_type, day, p_idx), [])
                    booking_info = []
                    for a in assigns:
                        class_names = [classes[s].name if s in classes else s for s in a.section_ids]
                        teacher_names = [teachers[t].name if t in teachers else t for t in a.teacher_ids]
                        booking_info.append({
                            "subject": a.subject,
                            "classes": class_names,
                            "teachers": teacher_names,
                            "raw_value": f"{a.subject} ({', '.join(class_names)})"
                        })
                    if booking_info:
                        total_bookings += len(booking_info)
                    day_periods.append({
                        "period_index": p_idx,
                        "period_name": p_def.get("name", f"Period {p_idx}"),
                        "period_time": p_def.get("time", ""),
                        "bookings": booking_info,
                        "is_occupied": len(booking_info) > 0,
                        "occupancy_count": len(booking_info),
                        "max_capacity": r.max_concurrent_classes
                    })
                r_sched[day] = day_periods

            room_obj = {
                "id": r.id,
                "name": r.name,
                "room_type": r.room_type,
                "building": r.building,
                "capacity": r.capacity,
                "max_concurrent_classes": r.max_concurrent_classes,
                "total_bookings_per_week": total_bookings,
                "schedule": r_sched
            }
            room_export[r.id] = room_obj
            if r.name not in room_export:
                room_export[r.name] = room_obj

        rooms_json_path = os.path.join(base_dir, "timetable_rooms.json")
        with open(rooms_json_path, "w", encoding="utf-8") as f:
            json.dump(room_export, f, indent=2, ensure_ascii=False)
        exported_files["timetable_rooms.json"] = rooms_json_path

    # 6. Export timetable_entries.csv
    csv_path = os.path.join(base_dir, "timetable_entries.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "entry_id", "class_name", "class_teacher", "day",
            "period_index", "period_name", "period_time", "raw_value", "subject", "teacher",
            "is_joint", "joint_label", "parallel_group_id", "elective_basket"
        ], extrasaction='ignore')
        writer.writeheader()
        writer.writerows(flat_entries)
    exported_files["timetable_entries.csv"] = csv_path

    # 7. Export SQLite Database
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

    if rooms:
        cur.execute("CREATE TABLE rooms (id TEXT PRIMARY KEY, name TEXT, room_type TEXT, capacity INTEGER, max_concurrent INTEGER, building TEXT)")
        for r in rooms.values():
            cur.execute("INSERT INTO rooms (id, name, room_type, capacity, max_concurrent, building) VALUES (?, ?, ?, ?, ?, ?)",
                        (r.id, r.name, r.room_type, r.capacity, r.max_concurrent_classes, r.building))

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
        teacher TEXT,
        is_joint INTEGER DEFAULT 0,
        joint_label TEXT,
        parallel_group_id TEXT,
        elective_basket TEXT
    )""")
    for item in flat_entries:
        cur.execute("""INSERT INTO schedule_entries
            (id, class_name, class_teacher, day, period_index, period_name, period_time, raw_value, subject, teacher,
             is_joint, joint_label, parallel_group_id, elective_basket)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
            item["entry_id"], item["class_name"], item["class_teacher"],
            item["day"], item["period_index"], item["period_name"],
            item["period_time"], item["raw_value"], item["subject"], item["teacher"],
            1 if item.get("is_joint") else 0,
            item.get("joint_label"),
            item.get("parallel_group_id"),
            item.get("elective_basket")
        ))

    cur.execute("CREATE INDEX idx_sched_class ON schedule_entries(class_name)")
    cur.execute("CREATE INDEX idx_sched_teacher ON schedule_entries(teacher)")
    cur.execute("CREATE INDEX idx_sched_day ON schedule_entries(day)")
    cur.execute("CREATE INDEX idx_sched_subject ON schedule_entries(subject)")
    conn.commit()
    conn.close()
    exported_files["timetable.sqlite"] = db_path

    return exported_files
