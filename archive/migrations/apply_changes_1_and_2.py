import os
import sys
import json
import sqlite3
import csv
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

print("=== Step 1: Backup files ===")
for fname in ["timetable.sqlite", "timetable.json", "timetable_teachers.json", "free_teachers.json", "timetable_entries.csv", "timetable_config.json"]:
    src = os.path.join(BASE_DIR, fname)
    if os.path.exists(src):
        shutil.copy2(src, src + ".bak_ch1_2")
print("Backups created.")

print("=== Step 2: Updating timetable.sqlite ===")
conn = sqlite3.connect(os.path.join(BASE_DIR, "timetable.sqlite"))
cur = conn.cursor()

# Change 1A: CLASS 10 Marigold Thu, Fri, Sat 5th Period -> Manish Mathur
cur.execute("""
    UPDATE schedule_entries
    SET subject = 'SST', teacher = 'Manish Mathur', raw_value = 'SST_Manish Mathur'
    WHERE class_name = 'CLASS 10 Marigold'
      AND period_name = '5th Period'
      AND day IN ('Thursday', 'Friday', 'Saturday')
""")
print(f"Updated CLASS 10 Marigold SST: {cur.rowcount} rows")

# Change 1B: CLASS 12 (Comm.) Thu, Fri, Sat 5th Period -> Rahul Vishwakarma
cur.execute("""
    UPDATE schedule_entries
    SET subject = 'Account', teacher = 'Rahul Vishwakarma', raw_value = 'Account_Rahul Vishwakarma'
    WHERE class_name = 'CLASS 12 (Comm.)'
      AND period_name = '5th Period'
      AND day IN ('Thursday', 'Friday', 'Saturday')
""")
print(f"Updated CLASS 12 (Comm.) Account: {cur.rowcount} rows")

# Change 2A: CLASS 11 (Bio + Math) -> Bio_Ram /Math_Rajpal (9 academic periods)
c11_p_conditions = """
    (day = 'Monday' AND period_index = 3) OR
    (day = 'Tuesday' AND period_index = 3) OR
    (day = 'Wednesday' AND period_index = 3) OR
    (day = 'Thursday' AND period_index IN (2, 3)) OR
    (day = 'Friday' AND period_index IN (2, 3)) OR
    (day = 'Saturday' AND period_index IN (2, 3))
"""
cur.execute(f"""
    UPDATE schedule_entries
    SET subject = 'Bio / Maths',
        teacher = 'Ram Kumar / Rajpal',
        raw_value = 'Bio_Ram /Math_Rajpal',
        parallel_group_id = 'ELECTIVE_11_BIO_MATH',
        elective_basket = 'Senior Science Elective Stream'
    WHERE class_name = 'CLASS 11 (Bio + Math)'
      AND ({c11_p_conditions})
""")
print(f"Updated CLASS 11 (Bio + Math): {cur.rowcount} rows")

# Change 2B: CLASS 12 (Bio + Math) -> Bio_Ram /Math_Rajpal (9 academic periods)
c12_p_conditions = """
    (day = 'Monday' AND period_index IN (1, 2)) OR
    (day = 'Tuesday' AND period_index IN (1, 2)) OR
    (day = 'Wednesday' AND period_index IN (1, 2)) OR
    (day = 'Thursday' AND period_index = 1) OR
    (day = 'Friday' AND period_index = 1) OR
    (day = 'Saturday' AND period_index = 1)
"""
cur.execute(f"""
    UPDATE schedule_entries
    SET subject = 'Bio / Maths',
        teacher = 'Ram Kumar / Rajpal',
        raw_value = 'Bio_Ram /Math_Rajpal',
        parallel_group_id = 'ELECTIVE_12_BIO_MATH',
        elective_basket = 'Senior Science Elective Stream'
    WHERE class_name = 'CLASS 12 (Bio + Math)'
      AND ({c12_p_conditions})
""")
print(f"Updated CLASS 12 (Bio + Math): {cur.rowcount} rows")

conn.commit()

# === Step 3: Re-export from SQLite into all JSON & CSV files ===
print("=== Step 3: Re-generating timetable.json, timetable_teachers.json, free_teachers.json, timetable_entries.csv ===")
with open(os.path.join(BASE_DIR, "timetable_config.json"), "r", encoding="utf-8") as f:
    cfg = json.load(f)

period_defs = cfg["config"]["period_definitions"]
school_timings = cfg["config"]["school_timings"]

cur.execute("SELECT DISTINCT class_name, class_teacher FROM schedule_entries ORDER BY id")
class_meta = cur.fetchall()
classes_dict = {}
for c_name, ct in class_meta:
    classes_dict[c_name] = {
        "class_name": c_name,
        "class_teacher": ct,
        "period_definitions": period_defs,
        "schedule": {d: [] for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]}
    }

cur.execute("""
    SELECT class_name, class_teacher, day, period_index, period_name, period_time, raw_value, subject, teacher, is_joint, joint_label, parallel_group_id, elective_basket
    FROM schedule_entries
    ORDER BY id
""")
all_entries = cur.fetchall()

flat_entries = []
all_teachers_set = set()
all_subjects_set = set()

for row in all_entries:
    (c_name, ct, day, p_idx, p_name, p_time, raw_val, subj, teach, is_joint, joint_label, parallel_group_id, elective_basket) = row
    
    t_ids = [t.strip() for t in teach.split("/") if t.strip()] if teach else []
    if subj and subj not in ["Lunch", "Prayer", "Morning Assembly"]:
        for t in t_ids:
            all_teachers_set.add(t)
        for s in subj.split("/"):
            if s.strip():
                all_subjects_set.add(s.strip())
        
    room_type = "Ground" if subj in ["Games", "Sports", "PE"] else ("Activity Hall" if subj == "Yoga" else "Classroom")

    period_item = {
        "period_index": p_idx,
        "period_name": p_name,
        "period_time": p_time,
        "raw_value": raw_val,
        "subject": subj,
        "teacher": teach,
        "teacher_ids": t_ids,
        "is_joint": bool(is_joint),
        "joint_label": joint_label,
        "parallel_group_id": parallel_group_id,
        "elective_basket": elective_basket,
        "room_type": room_type
    }
    classes_dict[c_name]["schedule"][day].append(period_item)

    flat_entries.append({
        "entry_id": len(flat_entries) + 1,
        "class_name": c_name,
        "class_teacher": ct,
        "day": day,
        "period_index": p_idx,
        "period_name": p_name,
        "period_time": p_time,
        "subject": subj,
        "teacher": teach,
        "room_type": room_type,
        "raw_value": raw_val
    })

conn.close()

classes_list = list(classes_dict.values())
cfg_teacher_names = {t["name"] for t in cfg.get("teachers", [])}
full_teacher_names = sorted(list(all_teachers_set.union(cfg_teacher_names)))

teacher_export = {}
for t_name in full_teacher_names:
    weekly_sched = {d: [] for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]}
    t_classes = set()
    t_subjects = set()
    unique_count = 0

    for c in classes_list:
        c_name = c["class_name"]
        for day, periods in c["schedule"].items():
            for p in periods:
                t_str = p.get("teacher", "")
                subj = p.get("subject", "")
                if not t_str or subj in ["Lunch", "Prayer", "Morning Assembly"]:
                    continue
                teachers = [x.strip() for x in t_str.split("/") if x.strip()]
                if t_name in teachers:
                    subjs = [x.strip() for x in subj.split("/") if x.strip()]
                    t_subj = subj
                    if len(subjs) == len(teachers):
                        t_subj = subjs[teachers.index(t_name)]
                    weekly_sched[day].append({
                        "class_name": c_name,
                        "period_index": p.get("period_index"),
                        "period_name": p.get("period_name"),
                        "period_time": p.get("period_time"),
                        "subject": t_subj,
                        "raw_value": f"{t_subj}_{t_name}",
                        "is_joint": p.get("is_joint", False),
                        "joint_label": p.get("joint_label"),
                        "parallel_group_id": p.get("parallel_group_id"),
                        "elective_basket": p.get("elective_basket"),
                        "room_type": p.get("room_type", "Classroom")
                    })
                    t_classes.add(c_name)
                    t_subjects.add(t_subj)
                    unique_count += 1

    for d in weekly_sched:
        weekly_sched[d].sort(key=lambda x: x.get("period_index", 0))

    is_ct = [c["class_name"] for c in classes_list if c.get("class_teacher") == t_name]

    teacher_export[t_name] = {
        "teacher_name": t_name,
        "is_class_teacher_of": is_ct,
        "total_weekly_teaching_periods": unique_count,
        "classes": sorted(list(t_classes)),
        "subjects": sorted(list(t_subjects)),
        "weekly_schedule": weekly_sched
    }

with open(os.path.join(BASE_DIR, "timetable_teachers.json"), "w", encoding="utf-8") as f:
    json.dump(teacher_export, f, indent=2, ensure_ascii=False)
print("Saved timetable_teachers.json")

tt_master = {
    "academic_year": "2026-27",
    "title": "School Time Table (w.e.f - 01/04/2026)",
    "school_timings": school_timings,
    "summary": {
        "total_classes": len(classes_list),
        "total_teachers": len(full_teacher_names),
        "total_subjects": len(all_subjects_set),
        "total_scheduled_periods": len(flat_entries)
    },
    "teachers": full_teacher_names,
    "subjects": sorted(list(all_subjects_set)),
    "classes": classes_list
}
with open(os.path.join(BASE_DIR, "timetable.json"), "w", encoding="utf-8") as f:
    json.dump(tt_master, f, indent=2, ensure_ascii=False)
print("Saved timetable.json")

days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
periods_meta = [
    {
        "index": p["period_index"],
        "id": f"P{p['period_index']}",
        "name": p["name"],
        "time": p["time"]
    }
    for p in period_defs
]

free_data = {
    "total_active_teachers": len(full_teacher_names),
    "days": days,
    "periods": periods_meta,
    "roster": {},
    "slot_availability": {}
}

for day in days:
    free_data["roster"][day] = {}
    free_data["slot_availability"][day] = {}
    for p_info in periods_meta:
        p_name = p_info["name"]
        p_idx = p_info["index"]

        occupied = {}
        for t_name, t_info in teacher_export.items():
            day_slots = t_info["weekly_schedule"][day]
            for slot in day_slots:
                if slot["period_index"] == p_idx:
                    occupied[t_name] = {
                        "class_name": slot["class_name"],
                        "subject": slot["subject"],
                        "raw": slot["raw_value"]
                    }
                    break

        free_candidates = []
        for t_name, t_info in teacher_export.items():
            if t_name not in occupied:
                free_candidates.append({
                    "name": t_name,
                    "is_class_teacher_of": t_info["is_class_teacher_of"],
                    "subjects": t_info["subjects"],
                    "classes": t_info["classes"],
                    "weekly_load": t_info["total_weekly_teaching_periods"]
                })

        free_candidates.sort(key=lambda x: x["name"])
        free_names = [c["name"] for c in free_candidates]

        free_data["slot_availability"][day][p_name] = free_names
        free_data["roster"][day][p_name] = {
            "period_info": p_info,
            "free_count": len(free_candidates),
            "busy_count": len(occupied),
            "busy_teachers": occupied,
            "free_teachers": free_candidates
        }

with open(os.path.join(BASE_DIR, "free_teachers.json"), "w", encoding="utf-8") as f:
    json.dump(free_data, f, indent=2, ensure_ascii=False)
print("Saved free_teachers.json")

with open(os.path.join(BASE_DIR, "timetable_entries.csv"), "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "entry_id", "class_name", "class_teacher", "day",
        "period_index", "period_name", "period_time", "subject", "teacher",
        "room_type", "raw_value"
    ])
    writer.writeheader()
    writer.writerows(flat_entries)
print("Saved timetable_entries.csv")

# === Step 4: Update timetable_config.json ===
print("=== Step 4: Updating timetable_config.json ===")
# 4A: Update EV_395 (CLASS 10 Marigold SST)
ev_395 = next((e for e in cfg["events"] if e["id"] == "EV_395"), None)
if ev_395:
    ev_395["weekly_quota"] = 3
    ev_395["locked_slots"] = [["Monday", 6], ["Tuesday", 6], ["Wednesday", 6]]
    ev_395["teacher_ids"] = ["Rahul Vishwakarma"]

# Add EV_395_B for Manish Mathur if not present
if not any(e["id"] == "EV_395_B" for e in cfg["events"]):
    cfg["events"].append({
        "id": "EV_395_B",
        "subject": "SST",
        "teacher_ids": ["Manish Mathur"],
        "section_ids": ["CLASS_10_Marigold"],
        "weekly_quota": 3,
        "room_type": "Classroom",
        "duration": 1,
        "locked_slots": [["Thursday", 6], ["Friday", 6], ["Saturday", 6]],
        "is_joint": False,
        "joint_label": None
    })

# 4B: Update EV_430 (CLASS 12 Comm Account)
ev_430 = next((e for e in cfg["events"] if e["id"] == "EV_430"), None)
if ev_430:
    ev_430["weekly_quota"] = 9
    ev_430["teacher_ids"] = ["Rahul Vishwakarma"]
    ev_430["locked_slots"] = [
        ["Monday", 5], ["Tuesday", 5], ["Wednesday", 5],
        ["Thursday", 5], ["Thursday", 6],
        ["Friday", 5], ["Friday", 6],
        ["Saturday", 5], ["Saturday", 6]
    ]

# Remove EV_434 (old Deepak Kushwaha account periods)
cfg["events"] = [e for e in cfg["events"] if e["id"] != "EV_434"]

# 4C: Update EV_408 (Class 11 Bio+Math)
ev_408 = next((e for e in cfg["events"] if e["id"] == "EV_408"), None)
if ev_408:
    ev_408["subject"] = "Bio / Maths"
    ev_408["teacher_ids"] = ["Ram Kumar", "Rajpal"]
    ev_408["parallel_group_id"] = "ELECTIVE_11_BIO_MATH"
    ev_408["elective_basket"] = "Senior Science Elective Stream"

# 4D: Update EV_421 (Class 12 Bio+Math)
ev_421 = next((e for e in cfg["events"] if e["id"] == "EV_421"), None)
if ev_421:
    ev_421["subject"] = "Bio / Maths"
    ev_421["teacher_ids"] = ["Ram Kumar", "Rajpal"]
    ev_421["parallel_group_id"] = "ELECTIVE_12_BIO_MATH"
    ev_421["elective_basket"] = "Senior Science Elective Stream"

# Update assigned_periods in cfg["teachers"]
for t_obj in cfg["teachers"]:
    t_name = t_obj["name"]
    if t_name in teacher_export:
        t_obj["assigned_periods"] = teacher_export[t_name]["total_weekly_teaching_periods"]

with open(os.path.join(BASE_DIR, "timetable_config.json"), "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
print("Saved timetable_config.json")

print("\n=== Summary of Key Workloads ===")
for t in ["Rajpal", "Ram Kumar", "Manish Mathur", "Rahul Vishwakarma", "Deepak Kushwaha"]:
    print(f"{t}: {teacher_export.get(t, {}).get('total_weekly_teaching_periods', 0)} p/w")

print("\nAll changes applied successfully!")
