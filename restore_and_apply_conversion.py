import sqlite3
import json
import os
import csv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

conn = sqlite3.connect(os.path.join(BASE_DIR, "timetable.sqlite"))
cur = conn.cursor()

# 1. Fetch all distinct classes
cur.execute("SELECT DISTINCT class_name, class_teacher FROM schedule_entries ORDER BY id")
class_rows = cur.fetchall()
classes_dict = {}
for c_name, ct in class_rows:
    classes_dict[c_name] = {
        "class_name": c_name,
        "class_teacher": ct,
        "schedule": {d: [] for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]}
    }

# 2. Fetch all schedule entries
cur.execute("""
    SELECT class_name, class_teacher, day, period_index, period_name, period_time, raw_value, subject, teacher, is_joint, joint_label, parallel_group_id, elective_basket
    FROM schedule_entries
    ORDER BY id
""")
all_entries = cur.fetchall()

for row in all_entries:
    (c_name, ct, day, p_idx, p_name, p_time, raw_val, subj, teach, is_joint, joint_label, parallel_group_id, elective_basket) = row
    classes_dict[c_name]["schedule"][day].append({
        "period_index": p_idx,
        "period_name": p_name,
        "period_time": p_time,
        "raw_value": raw_val,
        "subject": subj,
        "teacher": teach,
        "teacher_ids": [t.strip() for t in teach.split("/") if t.strip()] if teach else [],
        "is_joint": bool(is_joint),
        "joint_label": joint_label,
        "parallel_group_id": parallel_group_id,
        "elective_basket": elective_basket,
        "room_type": "Ground" if subj in ["Games", "Sports", "PE"] else ("Activity Hall" if subj == "Yoga" else "Classroom")
    })

# 3. Apply the 11 drawing-to-games conversions
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

print("Applying 11 drawing-to-games conversions...")
for c_name, day, p_name, old_subj, new_subj, new_teacher, room_type in conversions:
    target_class = classes_dict.get(c_name)
    if not target_class:
        print(f"Error: {c_name} not found")
        continue
    day_periods = target_class["schedule"][day]
    slot = next((p for p in day_periods if p["period_name"] == p_name), None)
    if not slot:
        print(f"Error: Slot {c_name} {day} {p_name} not found")
        continue
    print(f"Converting {c_name} {day} {p_name}: {slot['subject']} ({slot['teacher']}) -> {new_subj} ({new_teacher})")
    slot["subject"] = new_subj
    slot["teacher"] = new_teacher
    slot["teacher_ids"] = [new_teacher]
    slot["raw_value"] = f"{new_subj}_{new_teacher}"
    slot["room_type"] = room_type

    # Also update timetable.sqlite schedule_entries!
    cur.execute("""
        UPDATE schedule_entries
        SET subject = ?, teacher = ?, raw_value = ?
        WHERE class_name = ? AND day = ? AND period_name = ?
    """, (new_subj, new_teacher, f"{new_subj}_{new_teacher}", c_name, day, p_name))

conn.commit()
conn.close()
print("Updated timetable.sqlite successfully.")

# 4. Build classes list for timetable.json
classes_list = list(classes_dict.values())

# 5. Extract distinct teachers and build teacher_export
all_teachers = set()
for c in classes_list:
    for day, periods in c["schedule"].items():
        for p in periods:
            t_str = p.get("teacher", "")
            if t_str and p.get("subject") not in ["Lunch", "Prayer", "Morning Assembly"]:
                for t in [x.strip() for x in t_str.split("/") if x.strip()]:
                    all_teachers.add(t)

teacher_export = {}
for t_name in sorted(all_teachers):
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
                    weekly_sched[day].append({
                        "class_name": c_name,
                        "period_index": p.get("period_index"),
                        "period_name": p.get("period_name"),
                        "period_time": p.get("period_time"),
                        "subject": subj,
                        "raw_value": f"{subj}_{t_name}",
                        "is_joint": p.get("is_joint", False),
                        "joint_label": p.get("joint_label"),
                        "parallel_group_id": p.get("parallel_group_id"),
                        "elective_basket": p.get("elective_basket"),
                        "room_type": p.get("room_type", "Classroom")
                    })
                    t_classes.add(c_name)
                    t_subjects.add(subj)
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

# 6. Save timetable_teachers.json
with open(os.path.join(BASE_DIR, "timetable_teachers.json"), "w", encoding="utf-8") as f:
    json.dump(teacher_export, f, indent=2, ensure_ascii=False)
print("Saved timetable_teachers.json successfully. Total faculty:", len(teacher_export))

# 7. Save timetable.json
tt_output = {
    "academic_year": "2026-27",
    "title": "School Time Table (w.e.f - 01/04/2026)",
    "classes": classes_list,
    "teachers": [t_info for t_name, t_info in sorted(teacher_export.items())]
}
with open(os.path.join(BASE_DIR, "timetable.json"), "w", encoding="utf-8") as f:
    json.dump(tt_output, f, indent=2, ensure_ascii=False)
print("Saved timetable.json successfully.")

# 8. Rebuild free_teachers.json
days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
# Extract period definitions from first class
p_defs = classes_list[0]["schedule"]["Monday"]
periods_meta = [
    {
        "index": p["period_index"],
        "id": f"P{p['period_index']}",
        "name": p["period_name"],
        "time": p["period_time"]
    }
    for p in p_defs
]

free_data = {
    "total_active_teachers": len(teacher_export),
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
print("Saved free_teachers.json successfully.")

# 9. Save timetable_entries.csv
csv_path = os.path.join(BASE_DIR, "timetable_entries.csv")
flat_entries = []
entry_id = 1
for c in classes_list:
    c_name = c["class_name"]
    for day in days:
        for p in c["schedule"][day]:
            flat_entries.append({
                "entry_id": entry_id,
                "class_name": c_name,
                "day": day,
                "period_index": p["period_index"],
                "period_name": p["period_name"],
                "period_time": p["period_time"],
                "subject": p["subject"],
                "teacher": p["teacher"],
                "room_type": p.get("room_type", "Classroom"),
                "raw_value": p.get("raw_value")
            })
            entry_id += 1

with open(csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["entry_id", "class_name", "day", "period_index", "period_name", "period_time", "subject", "teacher", "room_type", "raw_value"])
    writer.writeheader()
    writer.writerows(flat_entries)
print("Saved timetable_entries.csv successfully.")

print("\n=== Updated Sports & Drawing Teachers Load Summary ===")
for t in ["Komal", "Geetesh", "Shikha Mishra", "Rajaram", "Shewta Dubey"]:
    print(f"{t}: {teacher_export[t]['total_weekly_teaching_periods']} p/w")
