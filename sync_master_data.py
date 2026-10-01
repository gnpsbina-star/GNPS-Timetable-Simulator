import os
import json
import sqlite3
import csv
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

print("=== 1. Reading Master Configuration and Timings ===")
with open(os.path.join(BASE_DIR, "timetable_config.json"), "r", encoding="utf-8") as f:
    cfg = json.load(f)

period_defs = cfg["config"]["period_definitions"]
school_timings = cfg["config"]["school_timings"]

print("=== 2. Reading Master Schedule from timetable.sqlite ===")
conn = sqlite3.connect(os.path.join(BASE_DIR, "timetable.sqlite"))
cur = conn.cursor()

# Synchronize period_time in timetable.sqlite with master period_definitions
p_time_map = {p["period_index"]: p["time"] for p in period_defs}
for p_idx, new_time in p_time_map.items():
    cur.execute("UPDATE schedule_entries SET period_time = ? WHERE period_index = ?", (new_time, p_idx))
conn.commit()
print("Synchronized period_time in timetable.sqlite with master period_definitions.")

# Get distinct classes
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
    p_time = p_time_map.get(p_idx, p_time)

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
print(f"Total classes: {len(classes_list)}")
print(f"Total faculty with teaching periods: {len(all_teachers_set)}")

# 3. Build Teacher Export (all 50 teachers)
# Ensure all 50 faculty from config are represented
cfg_teacher_names = {t["name"] for t in cfg.get("teachers", [])}
full_teacher_names = sorted(list(all_teachers_set.union(cfg_teacher_names)))
print(f"Total faculty members in catalog: {len(full_teacher_names)}")

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

# 4. Save timetable.json
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
    "teachers": full_teacher_names,  # Strings list matching index.html contract
    "subjects": sorted(list(all_subjects_set)),
    "classes": classes_list
}
with open(os.path.join(BASE_DIR, "timetable.json"), "w", encoding="utf-8") as f:
    json.dump(tt_master, f, indent=2, ensure_ascii=False)
print("Saved timetable.json")

# 5. Build free_teachers.json
from engine.substitution import sync_free_teachers
sync_free_teachers(BASE_DIR, config_data=cfg)
print("Saved free_teachers.json")

# 6. Save timetable_entries.csv
with open(os.path.join(BASE_DIR, "timetable_entries.csv"), "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "entry_id", "class_name", "class_teacher", "day",
        "period_index", "period_name", "period_time", "subject", "teacher",
        "room_type", "raw_value"
    ])
    writer.writeheader()
    writer.writerows(flat_entries)
print("Saved timetable_entries.csv")

# 6b. Update timetable_rooms.json period_time
rooms_path = os.path.join(BASE_DIR, "timetable_rooms.json")
if os.path.exists(rooms_path):
    with open(rooms_path, "r", encoding="utf-8") as f:
        rooms_data = json.load(f)
    for r_id, r_info in rooms_data.items():
        for d, periods_list in r_info.get("schedule", {}).items():
            for p_slot in periods_list:
                p_idx = p_slot.get("period_index")
                if p_idx in p_time_map:
                    p_slot["period_time"] = p_time_map[p_idx]
    with open(rooms_path, "w", encoding="utf-8") as f:
        json.dump(rooms_data, f, indent=2, ensure_ascii=False)
    print("Saved updated timetable_rooms.json with synchronized bell schedule.")

# 7. Update timetable_config.json events & assigned workloads
# Adjust events for the 11 classes to 1 Art & Craft + 1 Games/Sports
event_updates = [
    # (event_id_to_reduce, class_id, remaining_art_slots, new_event_id, new_subj, new_teacher, new_slots)
    ("EV_231", "CLASS_6_Rose", [["Saturday", 2]], "EV_6_ROSE_GAMES", "Games", "Geetesh", [["Tuesday", 2]]),
    ("EV_245", "CLASS_6_Marigold", [["Wednesday", 5]], "EV_6_MARIGOLD_SPORTS", "Sports", "Shikha Mishra", [["Tuesday", 6]]),
    ("EV_251", "CLASS_6_Lily", [["Wednesday", 7]], "EV_6_LILY_GAMES", "Games", "Komal", [["Monday", 5]]),
    ("EV_269", "CLASS_6_Sunflower", [["Saturday", 3]], "EV_6_SUNFLOWER_GAMES", "Games", "Geetesh", [["Friday", 6]]),
    ("EV_282", "CLASS_7_Rose", [["Friday", 5]], "EV_7_ROSE_GAMES", "Games", "Geetesh", [["Thursday", 2]]),
    ("EV_295", "CLASS_7_Marigold", [["Friday", 1]], "EV_7_MARIGOLD_GAMES", "Games", "Geetesh", [["Saturday", 1]]),
    ("EV_306", "CLASS_7_Lily", [["Friday", 2]], "EV_7_LILY_GAMES", "Games", "Geetesh", [["Thursday", 7]]),
    ("EV_317", "CLASS_7_Sunflower", [["Thursday", 6]], "EV_7_SUNFLOWER_GAMES", "Games", "Komal", [["Wednesday", 6]]),
    ("EV_321", "CLASS_8_Rose", [["Monday", 2]], "EV_8_ROSE_GAMES", "Games", "Komal", [["Saturday", 5]]),
    ("EV_341", "CLASS_8_Marigold", [["Wednesday", 1]], "EV_8_MARIGOLD_GAMES", "Games", "Komal", [["Thursday", 1]]),
    ("EV_348", "CLASS_8_Lily", [["Wednesday", 3]], "EV_8_LILY_GAMES", "Games", "Komal", [["Monday", 6]])
]

# Update Class 6 Sunflower Hindi EV_264: swap Friday slot from index 6 to index 3
for ev in cfg["events"]:
    if ev["id"] == "EV_264":
        ev["locked_slots"] = [
            ["Friday", 3] if slot == ["Friday", 6] else slot for slot in ev.get("locked_slots", [])
        ]

new_game_events = []
existing_ev_ids = {e["id"] for e in cfg["events"]}

for old_ev_id, cls_id, rem_slots, new_ev_id, new_subj, new_teacher, new_slots in event_updates:
    target_ev = next((e for e in cfg["events"] if e["id"] == old_ev_id), None)
    if target_ev:
        target_ev["weekly_quota"] = 1
        target_ev["locked_slots"] = rem_slots
        target_ev["subject"] = "Art & Craft"
        target_ev["room_type"] = "Classroom"
    
    if new_ev_id not in existing_ev_ids:
        new_game_events.append({
            "id": new_ev_id,
            "subject": new_subj,
            "teacher_ids": [new_teacher],
            "section_ids": [cls_id],
            "weekly_quota": 1,
            "room_type": "Ground",
            "duration": 1,
            "locked_slots": new_slots,
            "is_joint": False,
            "joint_label": None
        })
        existing_ev_ids.add(new_ev_id)

cfg["events"].extend(new_game_events)

# Update assigned_periods in cfg["teachers"]
for t_obj in cfg["teachers"]:
    t_name = t_obj["name"]
    if t_name in teacher_export:
        t_obj["assigned_periods"] = teacher_export[t_name]["total_weekly_teaching_periods"]

with open(os.path.join(BASE_DIR, "timetable_config.json"), "w", encoding="utf-8") as f:
    json.dump(cfg, f, indent=2, ensure_ascii=False)
print("Saved updated timetable_config.json")

print("\n--- Sports Teachers Loads ---")
for t in ["Komal", "Geetesh", "Shikha Mishra", "Rajaram", "Shewta Dubey"]:
    print(f"{t}: {teacher_export[t]['total_weekly_teaching_periods']} p/w")
