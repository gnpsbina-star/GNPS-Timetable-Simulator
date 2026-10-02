#!/usr/bin/env python3
"""
transfer_faculty.py - Hand over a faculty member's entire timetable to another teacher.

Every period, class-teacher role and lesson allocation of the source teacher is moved to
the target teacher in the same day/period slots, leaving the source teacher completely free:
  1. timetable_config.json (events.teacher_ids, classes.class_teacher)
  2. timetable.sqlite (schedule_entries teacher/raw_value/class_teacher, classes, teachers)
  3. timetable.json, timetable_teachers.json, free_teachers.json, timetable_entries.csv
     (rebuilt via sync_master_data.py)
  4. index.html / free_teachers.html embedded data snapshots (via embed_html_data.py)

The target teacher must already exist in the faculty catalog (add them in Prerequisites first).
If the target already teaches in any of the source teacher's slots, the transfer is refused
unless force=True, because it would create a clash.

Usage: python3 transfer_faculty.py "<From Teacher>" "<To Teacher>" [--force]
"""

import json
import os
import sqlite3
import subprocess
import sys

from engine.substitution import EXCLUDED_BREAK_SUBJECTS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class TransferError(Exception):
    """Raised when a transfer cannot be performed safely."""

    def __init__(self, message, clashes=None):
        super().__init__(message)
        self.clashes = clashes or []


def _norm(name):
    return (name or "").strip().lower()


def _split_teachers(teacher_str):
    return [t.strip() for t in (teacher_str or "").split("/") if t.strip()]


def _swap_in_list(names, old, new):
    """Replace old with new in a list of names (case-insensitive), without duplicating new."""
    out = []
    for n in names:
        repl = new if _norm(n) == _norm(old) else n
        if not any(_norm(x) == _norm(repl) for x in out):
            out.append(repl)
    return out


def _find_teacher(cfg, name):
    return next((t for t in cfg.get("teachers", []) if _norm(t.get("name")) == _norm(name)), None)


def transfer_in_config(cfg, old, new):
    """Move lesson allocations and class-teacher roles from old to new in a config dict (in place)."""
    events_moved = 0
    for ev in cfg.get("events", []):
        ids = ev.get("teacher_ids") or []
        if any(_norm(t) == _norm(old) for t in ids):
            ev["teacher_ids"] = _swap_in_list(ids, old, new)
            events_moved += 1

    classes_moved = []
    for c in cfg.get("classes", []):
        if _norm(c.get("class_teacher")) == _norm(old):
            c["class_teacher"] = new
            classes_moved.append(c.get("name", ""))

    return {"events_moved": events_moved, "class_teacher_of": classes_moved}


def find_clashes(db_path, old, new):
    """Slots where both old and new are already teaching (moving would double-book new)."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT class_name, day, period_index, teacher, subject FROM schedule_entries "
            "WHERE teacher IS NOT NULL AND teacher != ''"
        ).fetchall()
    finally:
        conn.close()

    old_slots, new_slots = {}, {}
    for class_name, day, p_idx, teacher, subject in rows:
        # Lunch/assembly duties sit in the same slot for every class; they never clash
        if (subject or "").strip() in EXCLUDED_BREAK_SUBJECTS:
            continue
        names = {_norm(t) for t in _split_teachers(teacher)}
        if _norm(old) in names:
            old_slots.setdefault((day, p_idx), set()).add(class_name)
        if _norm(new) in names:
            new_slots.setdefault((day, p_idx), set()).add(class_name)

    clashes = []
    for slot in sorted(set(old_slots) & set(new_slots), key=lambda s: (s[0], s[1])):
        # Same class in both is a shared/joint period, not a clash
        if old_slots[slot] == new_slots[slot]:
            continue
        clashes.append({
            "day": slot[0],
            "period_index": slot[1],
            "from_classes": sorted(old_slots[slot]),
            "to_classes": sorted(new_slots[slot]),
        })
    return clashes


def transfer_in_sqlite(db_path, old, new):
    """Rewrite the live timetable so new teaches exactly where old taught."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        periods_moved = 0
        rows = cur.execute(
            "SELECT id, teacher, raw_value FROM schedule_entries WHERE teacher IS NOT NULL AND teacher != ''"
        ).fetchall()
        for row_id, teacher, raw_value in rows:
            names = _split_teachers(teacher)
            if not any(_norm(t) == _norm(old) for t in names):
                continue
            new_teacher = " / ".join(_swap_in_list(names, old, new))
            new_raw = raw_value
            if raw_value:
                # raw_value looks like "Eng_Anjali Jain" or "Bio_Ram Kumar /Math_Rajpal"
                new_raw = "/".join(
                    part.replace(old, new) if _norm(part.split("_", 1)[-1]) == _norm(old) else part
                    for part in raw_value.split("/")
                )
            cur.execute(
                "UPDATE schedule_entries SET teacher = ?, raw_value = ? WHERE id = ?",
                (new_teacher, new_raw, row_id),
            )
            periods_moved += 1

        cur.execute(
            "UPDATE schedule_entries SET class_teacher = ? WHERE LOWER(TRIM(class_teacher)) = ?",
            (new, _norm(old)),
        )
        cur.execute(
            "UPDATE classes SET class_teacher = ? WHERE LOWER(TRIM(class_teacher)) = ?",
            (new, _norm(old)),
        )
        if not cur.execute("SELECT 1 FROM teachers WHERE LOWER(TRIM(name)) = ?", (_norm(new),)).fetchone():
            cur.execute("INSERT INTO teachers (name) VALUES (?)", (new,))
        conn.commit()
    finally:
        conn.close()
    return periods_moved


def rebuild_outputs(base_dir=BASE_DIR):
    """Regenerate timetable.json, timetable_teachers.json, free_teachers.json and the CSV,
    then re-embed them into index.html and free_teachers.html, which carry their own copies."""
    ok = True
    for script in ("sync_master_data.py", "embed_html_data.py"):
        path = os.path.join(base_dir, script)
        if not os.path.exists(path):
            ok = False
            continue
        res = subprocess.run([sys.executable, path], capture_output=True, text=True, cwd=base_dir)
        if res.returncode != 0:
            print(f"⚠️ Warning running {script}:", res.stderr, flush=True)
            ok = False
    return ok


def transfer_faculty(from_name, to_name, base_dir=BASE_DIR, force=False, rebuild=True):
    """Move from_name's whole timetable to to_name. Returns a summary dict.

    Raises TransferError if the names are invalid, or if the move would create clashes
    and force is False (the clashes are attached to the exception).
    """
    old, new = (from_name or "").strip(), (to_name or "").strip()
    if not old or not new:
        raise TransferError("Both 'from' and 'to' teacher names are required.")
    if _norm(old) == _norm(new):
        raise TransferError("Source and target teacher must be different.")

    cfg_path = os.path.join(base_dir, "timetable_config.json")
    db_path = os.path.join(base_dir, "timetable.sqlite")

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    old_t, new_t = _find_teacher(cfg, old), _find_teacher(cfg, new)
    if not new_t:
        raise TransferError(f"Teacher '{new}' is not in the faculty catalog. Add them in Prerequisites and save first.")
    # Use the catalog spelling of the names
    new = new_t["name"]
    if old_t:
        old = old_t["name"]

    clashes = find_clashes(db_path, old, new) if os.path.exists(db_path) else []
    if clashes and not force:
        raise TransferError(
            f"'{new}' already teaches in {len(clashes)} of '{old}'s slots. Transferring would create clashes.",
            clashes=clashes,
        )

    summary = transfer_in_config(cfg, old, new)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

    summary["periods_moved"] = transfer_in_sqlite(db_path, old, new) if os.path.exists(db_path) else 0
    summary["from"], summary["to"] = old, new
    summary["clashes"] = clashes

    max_weekly = new_t.get("max_weekly_periods")
    if max_weekly and os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT teacher, subject FROM schedule_entries WHERE teacher IS NOT NULL AND teacher != ''"
            ).fetchall()
        finally:
            conn.close()
        load = sum(
            1 for teacher, subj in rows
            if (subj or "").strip() not in EXCLUDED_BREAK_SUBJECTS
            and any(_norm(t) == _norm(new) for t in _split_teachers(teacher))
        )
        summary["new_weekly_load"] = load
        if load > max_weekly:
            summary["warning"] = f"'{new}' now has {load} periods/week, above their cap of {max_weekly}."

    if rebuild:
        summary["outputs_rebuilt"] = rebuild_outputs(base_dir)
    return summary


def main(argv):
    args = [a for a in argv if a != "--force"]
    if len(args) != 2:
        print('Usage: python3 transfer_faculty.py "<From Teacher>" "<To Teacher>" [--force]')
        return 1
    try:
        s = transfer_faculty(args[0], args[1], force="--force" in argv)
    except TransferError as e:
        print(f"❌ {e}")
        for c in e.clashes:
            print(f"   {c['day']} P{c['period_index']}: {', '.join(c['from_classes'])} vs {', '.join(c['to_classes'])}")
        if e.clashes:
            print("   Re-run with --force to transfer anyway.")
        return 1

    print(f"✅ Moved {s['periods_moved']} period slot(s) and {s['events_moved']} lesson allocation(s) "
          f"from '{s['from']}' to '{s['to']}'.")
    if s["class_teacher_of"]:
        print(f"✅ '{s['to']}' is now Class Teacher of: {', '.join(s['class_teacher_of'])}")
    if s.get("warning"):
        print(f"⚠️ {s['warning']}")
    print(f"🎉 '{s['from']}' is now completely free. Run 'python3 generate_timetable.py --verify' to confirm 0 clashes.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
