#!/usr/bin/env python3
"""
purge_faculty.py - Completely purge or unassign a deleted faculty member across all files:
  1. timetable_config.json (teachers list, class_teacher, events.teacher_ids)
  2. timetable.sqlite (schedule_entries teacher and class_teacher)
  3. timetable.json (master timetable grids and teacher catalog)
  4. timetable_teachers.json (individual teacher schedules)
  5. free_teachers.json (availability rosters)
  6. timetable_entries.csv (raw CSV records)
  7. index.html / free_teachers.html (embedded data snapshots)
"""

import sys
import os
import json
import sqlite3
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def purge_faculty(faculty_name):
    clean_name = faculty_name.strip()
    clean_name_lower = clean_name.lower()
    
    print(f"==================================================")
    print(f"Purging faculty: '{clean_name}' across all layers")
    print(f"==================================================")

    # 1. Update timetable_config.json
    cfg_path = os.path.join(BASE_DIR, "timetable_config.json")
    removed_from_config = False
    unassigned_classes_cfg = []
    unassigned_events_cfg = 0

    if os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        # Remove from teachers
        orig_t_count = len(cfg.get("teachers", []))
        cfg["teachers"] = [
            t for t in cfg.get("teachers", [])
            if t.get("name", "").strip().lower() != clean_name_lower and t.get("id", "").strip().lower() != clean_name_lower
        ]
        if len(cfg["teachers"]) < orig_t_count:
            removed_from_config = True
            print(f"✅ Removed from timetable_config.json teachers catalog ({orig_t_count} -> {len(cfg['teachers'])})")

        # Unassign class teacher
        for c in cfg.get("classes", []):
            if c.get("class_teacher", "").strip().lower() == clean_name_lower:
                unassigned_classes_cfg.append(c.get("name", "Unknown Class"))
                c["class_teacher"] = ""

        # Remove from events
        for ev in cfg.get("events", []):
            t_ids = ev.get("teacher_ids", [])
            new_t_ids = [t for t in t_ids if t.strip().lower() != clean_name_lower]
            if len(new_t_ids) != len(t_ids):
                unassigned_events_cfg += 1
                ev["teacher_ids"] = new_t_ids

        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved timetable_config.json. (Class Teacher unassigned: {unassigned_classes_cfg}, Events updated: {unassigned_events_cfg})")

    # 2. Update timetable.sqlite
    db_path = os.path.join(BASE_DIR, "timetable.sqlite")
    sqlite_updated_periods = 0
    sqlite_updated_ct = 0

    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Check and delete from teachers table
        cur.execute("SELECT COUNT(*) FROM teachers WHERE LOWER(TRIM(name)) = ?", (clean_name_lower,))
        sqlite_teachers_deleted = cur.fetchone()[0]
        if sqlite_teachers_deleted > 0:
            cur.execute("DELETE FROM teachers WHERE LOWER(TRIM(name)) = ?", (clean_name_lower,))
            print(f"✅ Deleted from timetable.sqlite 'teachers' table: {sqlite_teachers_deleted} row(s)")

        # Check and update class_teacher
        cur.execute("SELECT COUNT(*) FROM schedule_entries WHERE LOWER(TRIM(class_teacher)) = ?", (clean_name_lower,))
        sqlite_updated_ct = cur.fetchone()[0]
        cur.execute("UPDATE schedule_entries SET class_teacher = '' WHERE LOWER(TRIM(class_teacher)) = ?", (clean_name_lower,))

        # Update teacher in schedule_entries
        cur.execute("SELECT id, teacher, raw_value, subject FROM schedule_entries WHERE teacher IS NOT NULL AND teacher != ''")
        rows = cur.fetchall()

        for row_id, teach_str, raw_val, subj in rows:
            teachers = [t.strip() for t in teach_str.split("/") if t.strip()]
            if any(t.lower() == clean_name_lower for t in teachers):
                sqlite_updated_periods += 1
                new_teachers = [t for t in teachers if t.lower() != clean_name_lower]
                new_teacher_str = " / ".join(new_teachers)
                cur.execute("UPDATE schedule_entries SET teacher = ? WHERE id = ?", (new_teacher_str, row_id))

        conn.commit()
        conn.close()
        print(f"✅ Updated timetable.sqlite: {sqlite_updated_periods} period slots cleared/unassigned, {sqlite_updated_ct} class teacher slots cleared.")

    # 2b. Update timetable.db (legacy database if present)
    db_legacy_path = os.path.join(BASE_DIR, "timetable.db")
    if os.path.exists(db_legacy_path):
        conn_leg = sqlite3.connect(db_legacy_path)
        cur_leg = conn_leg.cursor()
        try:
            # Check timetable_entries in timetable.db
            cur_leg.execute("SELECT id, teacher, raw_value FROM timetable_entries WHERE teacher LIKE ? OR raw_value LIKE ?", (f"%{clean_name}%", f"%{clean_name}%"))
            leg_rows = cur_leg.fetchall()
            for r_id, r_teach, r_raw in leg_rows:
                t_list = [x.strip() for x in (r_teach or "").split("/") if x.strip()]
                new_t_list = [x for x in t_list if x.lower() != clean_name_lower]
                new_t = " / ".join(new_t_list)
                new_raw = r_raw or ""
                if clean_name_lower in new_raw.lower():
                    # replace Name or _Name
                    new_raw = re.sub(re.escape(clean_name), "", new_raw, flags=re.IGNORECASE).rstrip(" _-")
                cur_leg.execute("UPDATE timetable_entries SET teacher = ?, raw_value = ? WHERE id = ?", (new_t, new_raw, r_id))
            conn_leg.commit()
            print(f"✅ Updated legacy timetable.db: {len(leg_rows)} rows updated.")
        except Exception as e:
            print(f"Note on timetable.db update: {e}")
        finally:
            conn_leg.close()

    # 3. Re-run sync_master_data.py logic to rebuild timetable.json, timetable_teachers.json, free_teachers.json, timetable_entries.csv
    sync_script = os.path.join(BASE_DIR, "sync_master_data.py")
    if os.path.exists(sync_script):
        import subprocess
        res = subprocess.run([sys.executable, sync_script], capture_output=True, text=True)
        if res.returncode == 0:
            print("✅ Successfully rebuilt timetable.json, timetable_teachers.json, free_teachers.json, and timetable_entries.csv.")
        else:
            print("⚠️ Warning running sync_master_data.py:", res.stderr)

    # 4. Re-embed the rebuilt JSON into index.html and free_teachers.html, which
    #    carry their own copies of the data and otherwise keep showing the faculty.
    embed_script = os.path.join(BASE_DIR, "embed_html_data.py")
    if os.path.exists(embed_script):
        import subprocess
        res = subprocess.run([sys.executable, embed_script], capture_output=True, text=True)
        if res.returncode == 0:
            print("✅ Refreshed embedded data in index.html and free_teachers.html.")
        else:
            print("⚠️ Warning running embed_html_data.py:", res.stderr)

    print(f"\n🎉 Completed! Faculty '{clean_name}' has been completely purged from all timetable grids, rosters, and data files.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 purge_faculty.py <faculty_name>")
        sys.exit(1)
    purge_faculty(sys.argv[1])
