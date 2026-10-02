import json
import os
import sqlite3
import csv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 1. Load timetable.json
with open(os.path.join(BASE_DIR, "timetable.json"), "r", encoding="utf-8") as f:
    tt = json.load(f)

classes_list = tt.get("classes", [])

# Define conversions by (class_name, day, period_name, expected_old_subj, new_subj, new_teacher, room_type)
conversions = [
    ("CLASS 6 Rose", "Tuesday", "2nd Period", "Drawing", "Games", "Geetesh", "Ground"),
    ("CLASS 6 Marigold", "Tuesday", "5th Period", "Drawing", "Sports", "Shikha Mishra", "Ground"),
    ("CLASS 6 Lily", "Monday", "4th Period", "Drawing", "Games", "Komal", "Ground"),
    # Class 6 Sunflower: Friday P3 was Drawing, P5 was Hindi. We swap: P3 -> Hindi (Shewta Dubey), P5 -> Games (Geetesh)
    ("CLASS 6 Sunflower", "Friday", "3rd Period", "Drawing", "Hindi", "Shewta Dubey", "Classroom"),
    ("CLASS 6 Sunflower", "Friday", "5th Period", "Hindi", "Games", "Geetesh", "Ground"),
    ("CLASS 7 Rose", "Thursday", "2nd Period", "Drawing", "Games", "Geetesh", "Ground"),
    ("CLASS 7 Marigold", "Saturday", "1st Period", "Drawing", "Games", "Geetesh", "Ground"),
    ("CLASS 7 Lily", "Thursday", "6th Period", "Drawing", "Games", "Geetesh", "Ground"),
    ("CLASS 7 Sunflower", "Wednesday", "5th Period", "Drawing", "Games", "Komal", "Ground"),
    ("CLASS 8 Rose", "Saturday", "4th Period", "Drawing", "Games", "Komal", "Ground"),
    ("CLASS 8 Marigold", "Thursday", "1st Period", "Drawing", "Games", "Komal", "Ground"),
    ("CLASS 8 Lily", "Monday", "5th Period", "Drawing", "Games", "Komal", "Ground"),
]

print("Applying conversions to timetable.json classes...")
for c_name, day, p_name, old_subj, new_subj, new_teacher, room_type in conversions:
    target_class = next((c for c in classes_list if c.get("class_name") == c_name), None)
    if not target_class:
        print(f"ERROR: Class {c_name} not found!")
        continue
    day_periods = target_class.get("schedule", {}).get(day, [])
    slot = next((p for p in day_periods if p.get("period_name") == p_name), None)
    if not slot:
        print(f"ERROR: Slot for {c_name} on {day} {p_name} not found!")
        continue
    curr_subj = slot.get('subject')
    curr_teach = slot.get('teacher')
    print(f"Updating {c_name} {day} {p_name}: {curr_subj} ({curr_teach}) -> {new_subj} ({new_teacher})")
    slot["subject"] = new_subj
    slot["teacher"] = new_teacher
    slot["teacher_ids"] = [new_teacher]
    slot["raw_value"] = f"{new_subj}_{new_teacher}"
    slot["room_type"] = room_type

# Save updated timetable.json
with open(os.path.join(BASE_DIR, "timetable.json"), "w", encoding="utf-8") as f:
    json.dump(tt, f, indent=2, ensure_ascii=False)
print("Saved updated timetable.json successfully.")

# 2. Rebuild timetable_teachers.json
with open(os.path.join(BASE_DIR, "timetable_teachers.json"), "r", encoding="utf-8") as f:
    teachers_export = json.load(f)

# Recompute schedules for all teachers from classes_list
teacher_schedules = {t: {d: [] for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]} for t in teachers_export.keys()}
teacher_classes = {t: set() for t in teachers_export.keys()}
teacher_subjects = {t: set() for t in teachers_export.keys()}

for c in classes_list:
    c_name = c.get("class_name")
    for day, periods in c.get("schedule", {}).items():
        for p in periods:
            teach_str = p.get("teacher", "")
            subj = p.get("subject", "")
            if not teach_str or subj in ["Lunch", "Prayer", "Morning Assembly"]:
                continue
            for t in [x.strip() for x in teach_str.split("/") if x.strip()]:
                if t in teacher_schedules:
                    teacher_schedules[t][day].append({
                        "class_name": c_name,
                        "period_index": p.get("period_index"),
                        "period_name": p.get("period_name"),
                        "period_time": p.get("period_time"),
                        "subject": subj,
                        "raw_value": f"{subj}_{t}",
                        "is_joint": p.get("is_joint", False),
                        "joint_label": p.get("joint_label"),
                        "parallel_group_id": p.get("parallel_group_id"),
                        "elective_basket": p.get("elective_basket"),
                        "room_type": p.get("room_type", "Classroom")
                    })
                    teacher_classes[t].add(c_name)
                    teacher_subjects[t].add(subj)

for t_name, t_info in teachers_export.items():
    sched = teacher_schedules[t_name]
    for d in sched:
        sched[d].sort(key=lambda x: x.get("period_index", 0))
    t_info["weekly_schedule"] = sched
    t_info["classes"] = sorted(list(teacher_classes[t_name]))
    t_info["subjects"] = sorted(list(teacher_subjects[t_name]))
    unique_count = sum(len(sched[d]) for d in sched)
    t_info["total_weekly_teaching_periods"] = unique_count

with open(os.path.join(BASE_DIR, "timetable_teachers.json"), "w", encoding="utf-8") as f:
    json.dump(teachers_export, f, indent=2, ensure_ascii=False)
print("Saved updated timetable_teachers.json successfully.")

# Also update tt['teachers'] in timetable.json if present
if "teachers" in tt:
    tt_teachers = []
    for t_name, t_info in sorted(teachers_export.items()):
        tt_teachers.append(t_info)
    tt["teachers"] = tt_teachers
    with open(os.path.join(BASE_DIR, "timetable.json"), "w", encoding="utf-8") as f:
        json.dump(tt, f, indent=2, ensure_ascii=False)

# 3. Rebuild free_teachers.json
with open(os.path.join(BASE_DIR, "free_teachers.json"), "r", encoding="utf-8") as f:
    free_data = json.load(f)

days = free_data.get("days", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"])
periods_def = free_data.get("periods", [])

for day in days:
    for p_info in periods_def:
        p_name = p_info.get("name")
        p_idx = p_info.get("index")
        
        occupied = {}
        for t_name, t_info in teachers_export.items():
            day_slots = t_info.get("weekly_schedule", {}).get(day, [])
            for slot in day_slots:
                if slot.get("period_index") == p_idx:
                    occupied[t_name] = {
                        "class_name": slot.get("class_name"),
                        "subject": slot.get("subject"),
                        "raw": slot.get("raw_value")
                    }
                    break
        
        free_candidates = []
        for t_name, t_info in teachers_export.items():
            if t_name not in occupied:
                free_candidates.append({
                    "name": t_name,
                    "is_class_teacher_of": t_info.get("is_class_teacher_of", []),
                    "subjects": t_info.get("subjects", []),
                    "classes": t_info.get("classes", []),
                    "weekly_load": t_info.get("total_weekly_teaching_periods", 0)
                })
        
        free_candidates.sort(key=lambda x: x["name"])
        free_names = [c["name"] for c in free_candidates]
        
        if day in free_data.get("slot_availability", {}):
            free_data["slot_availability"][day][p_name] = free_names
        if day in free_data.get("roster", {}) and p_name in free_data["roster"][day]:
            free_data["roster"][day][p_name]["free_count"] = len(free_candidates)
            free_data["roster"][day][p_name]["busy_count"] = len(occupied)
            free_data["roster"][day][p_name]["busy_teachers"] = occupied
            free_data["roster"][day][p_name]["free_teachers"] = free_candidates

with open(os.path.join(BASE_DIR, "free_teachers.json"), "w", encoding="utf-8") as f:
    json.dump(free_data, f, indent=2, ensure_ascii=False)
print("Saved updated free_teachers.json successfully.")

# 4. Rebuild timetable_entries.csv and timetable.db
csv_path = os.path.join(BASE_DIR, "timetable_entries.csv")
flat_entries = []
entry_id = 1
for c in classes_list:
    c_name = c.get("class_name")
    for day in days:
        for p in c.get("schedule", {}).get(day, []):
            flat_entries.append({
                "entry_id": entry_id,
                "class_name": c_name,
                "day": day,
                "period_index": p.get("period_index"),
                "period_name": p.get("period_name"),
                "period_time": p.get("period_time"),
                "subject": p.get("subject"),
                "teacher": p.get("teacher"),
                "room_type": p.get("room_type", "Classroom"),
                "raw_value": p.get("raw_value")
            })
            entry_id += 1

with open(csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["entry_id", "class_name", "day", "period_index", "period_name", "period_time", "subject", "teacher", "room_type", "raw_value"])
    writer.writeheader()
    writer.writerows(flat_entries)
print("Saved updated timetable_entries.csv successfully.")

db_path = os.path.join(BASE_DIR, "timetable.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("DROP TABLE IF EXISTS timetable_entries")
cur.execute("""
    CREATE TABLE timetable_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_name TEXT,
        day TEXT,
        period_index INTEGER,
        period_name TEXT,
        period_time TEXT,
        subject TEXT,
        teacher TEXT,
        room_type TEXT,
        raw_value TEXT
    )
""")
for e in flat_entries:
    cur.execute("""
        INSERT INTO timetable_entries (class_name, day, period_index, period_name, period_time, subject, teacher, room_type, raw_value)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (e["class_name"], e["day"], e["period_index"], e["period_name"], e["period_time"], e["subject"], e["teacher"], e["room_type"], e["raw_value"]))
conn.commit()
conn.close()
print("Saved updated timetable.db successfully.")

# 5. Update timetable_config.json
cfg_path = os.path.join(BASE_DIR, "timetable_config.json")
with open(cfg_path, "r", encoding="utf-8") as f:
    cfg = json.load(f)

if "teachers" in cfg:
    for t_obj in cfg["teachers"]:
        t_n = t_obj.get("name")
        if t_n in teachers_export:
            t_obj["assigned_periods"] = teachers_export[t_n]["total_weekly_teaching_periods"]

with open(cfg_path, "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
print("Saved updated timetable_config.json successfully.")

print("\n--- Final Workload Summary ---")
for t in ["Komal", "Geetesh", "Shikha Mishra", "Rajaram", "Shewta Dubey"]:
    print(f"{t}: {teachers_export[t]['total_weekly_teaching_periods']} p/w")
