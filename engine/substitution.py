"""
Autonomous Daily Substitution & Absentee Coverage Engine.
Provides intelligent multi-tier candidate ranking, dynamic fatigue load balancing,
and global constraint satisfaction auto-assignment.
"""

import os
import json
from typing import Dict, List, Any, Optional, Set, Tuple

EXCLUDED_BREAK_SUBJECTS = {
    "Lunch",
    "Prayer",
    "Lunch _ Class Teacher",
    "Morning Assembly",
    "CYCLE TEST",
    "CCA",
    "Recess",
    "Assembly"
}

MANAGEMENT_TEACHERS = {"sonakshi", "shailandra", "shailendra", "shailendra kurmi", "shailandra kurmi"}

def is_management_teacher(name: Optional[str]) -> bool:
    """Checks whether a faculty member belongs to the management team (Sonakshi & Shailendra Kurmi)."""
    if not name:
        return False
    clean = name.strip().lower()
    return clean in MANAGEMENT_TEACHERS or \
           clean.startswith("sonakshi") or clean.startswith("shailandra") or clean.startswith("shailendra")

def normalize_subject(subj: Optional[str]) -> str:
    s = (subj or "").strip().lower()
    if s in ("math", "maths", "mathematics"):
        return "maths"
    if s in ("sci", "science"):
        return "science"
    if s in ("game", "games"):
        return "games"
    if s in ("art&craft", "art & craft", "drawing"):
        return "art & craft"
    if s in ("distation & cursive", "dictation & cursive"):
        return "dictation & cursive"
    if s in ("eng", "english"):
        return "eng"
    if s in ("skt", "sanskrit"):
        return "skt"
    if s in ("pe", "physical education", "pe practical"):
        return "pe"
    return s

def get_subject_family(subj: Optional[str]) -> str:
    s = (subj or "").strip().lower()
    if any(m in s for m in ("math", "mathematics")):
        return "maths"
    if any(sc in s for sc in ("physic", "chem", "bio", "sci", "science", "evs")):
        return "science"
    if any(en in s for en in ("eng", "english", "dictation", "cursive")):
        return "english"
    if any(hi in s for hi in ("hindi", "skt", "sanskrit")):
        return "hindi"
    if any(so in s for so in ("sst", "social", "geo", "history", "civic", "political")):
        return "social"
    if any(co in s for co in ("account", "bst", "business", "eco", "commerce")):
        return "commerce"
    if any(pe in s for pe in ("pe", "physical", "game", "yoga", "sport")):
        return "sports"
    if any(ar in s for ar in ("art", "craft", "drawing", "music")):
        return "arts"
    if any(it in s for it in ("it", "comp", "computer")):
        return "it"
    if "lib" in s:
        return "library"
    if "gk" in s:
        return "gk"
    return "general"

def match_subject(target_subj: Optional[str], cand_subjs: List[str]) -> Tuple[int, Optional[str]]:
    """
    Returns (score, reason) for candidate's subject match against target slot.
    Exact Match: +100
    Related Subject Family: +60
    No Match: 0
    """
    if not target_subj or not cand_subjs:
        return 0, None
    t_norm = normalize_subject(target_subj)
    cand_norms = [normalize_subject(s) for s in cand_subjs]
    if t_norm in cand_norms:
        return 120, "Subject Match"
    t_fam = get_subject_family(target_subj)
    if t_fam != "general":
        for s in cand_subjs:
            if get_subject_family(s) == t_fam:
                return 70, "Related Subject"
    return 0, None

class SubstitutionManager:
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.teacher_data: Dict[str, Any] = {}
        self.free_data: Dict[str, Any] = {}
        self.timetable_data: Dict[str, Any] = {}
        self.config_data: Dict[str, Any] = {}
        self.blackout_slots: Dict[str, Set[Tuple[str, int]]] = {}
        self.period_name_to_index: Dict[str, int] = {}
        self.class_wings: Dict[str, str] = {}
        self.teacher_wings: Dict[str, Set[str]] = {}
        self.is_loaded = False
        self.load_data()

    def load_data(self, base_dir: Optional[str] = None):
        if base_dir:
            self.base_dir = base_dir
        
        teachers_path = os.path.join(self.base_dir, "timetable_teachers.json")
        free_path = os.path.join(self.base_dir, "free_teachers.json")
        timetable_path = os.path.join(self.base_dir, "timetable.json")
        config_path = os.path.join(self.base_dir, "timetable_config.json")

        if os.path.exists(teachers_path):
            with open(teachers_path, "r", encoding="utf-8") as f:
                self.teacher_data = json.load(f)
        
        if os.path.exists(free_path):
            with open(free_path, "r", encoding="utf-8") as f:
                self.free_data = json.load(f)

        if os.path.exists(timetable_path):
            with open(timetable_path, "r", encoding="utf-8") as f:
                self.timetable_data = json.load(f)

        self.config_data = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                self.config_data = json.load(f)

        self._build_blackout_index()
        self._build_wing_index()
        self.is_loaded = bool(self.teacher_data and self.free_data)

    def _build_wing_index(self):
        """Index class wing mappings and compute active teaching wings for each teacher."""
        self.class_wings = {}
        for c in self.config_data.get("classes", []):
            name = c.get("name")
            wing = c.get("wing")
            if name and wing:
                self.class_wings[name] = wing

        self.teacher_wings = {}
        for t_name, t_info in self.teacher_data.items():
            wings = set()
            for c_name in t_info.get("classes", []):
                w = self.class_wings.get(c_name)
                if not w:
                    w = self.get_class_wing(c_name)
                if w:
                    wings.add(w)
            self.teacher_wings[t_name] = wings

    def get_class_wing(self, class_name: Optional[str]) -> str:
        if not class_name:
            return "General"
        if class_name in self.class_wings:
            return self.class_wings[class_name]
        c_upper = class_name.upper()
        if any(c_upper.startswith(f"CLASS {i} ") for i in range(1, 6)) or "PRIMARY" in c_upper:
            return "Primary"
        if any(c_upper.startswith(f"CLASS {i} ") for i in range(6, 9)) or "MIDDLE" in c_upper:
            return "Middle"
        if any(c_upper.startswith(f"CLASS {i} ") for i in range(9, 13)) or "SENIOR" in c_upper:
            return "Senior"
        return "General"

    def get_wing_compatibility_score(self, target_class: str, cand_name: str) -> Tuple[int, Optional[str]]:
        target_wing = self.get_class_wing(target_class)
        cand_wings = self.teacher_wings.get(cand_name, set())
        if not cand_wings:
            return 0, None
        if target_wing in cand_wings:
            return 30, "Same Wing"
        if target_wing == "Middle" and ("Primary" in cand_wings or "Senior" in cand_wings):
            return 15, "Adjacent Wing"
        if target_wing in ("Primary", "Senior") and "Middle" in cand_wings:
            return 15, "Adjacent Wing"
        if target_wing == "Primary" and cand_wings == {"Senior"}:
            return -50, None
        if target_wing == "Senior" and cand_wings == {"Primary"}:
            return -50, None
        return 0, None

    def _build_blackout_index(self):
        """Index unavailable / blackout slots per teacher."""
        self.blackout_slots = {}
        self.period_name_to_index = {}
        for p in self.config_data.get("config", {}).get("period_definitions", []):
            p_name = p.get("name", "").strip().lower()
            self.period_name_to_index[p_name] = p.get("period_index", 0)

        for t in self.config_data.get("teachers", []):
            t_name = t.get("name", "").strip().lower()
            s_set = set()
            for slot in t.get("unavailable_slots", []):
                if isinstance(slot, (list, tuple)) and len(slot) == 2:
                    s_set.add((str(slot[0]), int(slot[1])))
                elif isinstance(slot, dict):
                    s_set.add((str(slot.get("day", "")), int(slot.get("period_index", 0))))
            if s_set:
                self.blackout_slots[t_name] = s_set

    def is_teacher_blackout(
        self,
        teacher_name: str,
        day: str,
        period_index: Optional[int] = None,
        period_name: Optional[str] = None
    ) -> bool:
        """
        Returns True if the teacher has marked the given day and period as Blackout / Unavailable.
        """
        if not teacher_name or not self.blackout_slots:
            return False

        t_clean = teacher_name.strip().lower()
        slots_set = self.blackout_slots.get(t_clean)
        if slots_set is None:
            for k, s in self.blackout_slots.items():
                if k == t_clean or k.startswith(t_clean + " ") or t_clean.startswith(k + " "):
                    slots_set = s
                    break

        if not slots_set:
            return False

        p_idx = period_index
        if p_idx is None and period_name:
            p_idx = self.period_name_to_index.get(period_name.strip().lower())

        if p_idx is not None and (day, p_idx) in slots_set:
            return True

        return False

    def get_affected_slots(self, day: str, absent_teachers: List[str]) -> List[Dict[str, Any]]:
        """
        Retrieves all valid teaching periods for the given absent teachers on `day`,
        excluding break periods like Lunch, Prayer, and Morning Assembly.
        ALSO generates Morning Assembly and Lunch Break duty coverage slots whenever
        a designated Class Teacher is absent.
        """
        slots = []
        t_key_map = {k.strip().lower(): k for k in self.teacher_data.keys()}
        absent_canonical = set()
        for t in absent_teachers:
            if t:
                t_clean = t.strip().lower()
                canonical = t_key_map.get(t_clean)
                if not canonical:
                    # Match unique prefix or prefix match (e.g. "Vandna" -> "Vandna Saraf")
                    prefix_matches = [k for k_lower, k in t_key_map.items() if k_lower.startswith(t_clean) or t_clean.startswith(k_lower)]
                    if len(prefix_matches) == 1:
                        canonical = prefix_matches[0]
                absent_canonical.add(canonical or t)

        for teacher in absent_canonical:
            t_info = self.teacher_data.get(teacher)
            if not t_info or "weekly_schedule" not in t_info:
                continue

            # 1. Regular academic and activity teaching slots
            day_sched = t_info.get("weekly_schedule", {}).get(day, [])
            for p in day_sched:
                subj = p.get("subject", "").strip()
                if subj and subj.upper() not in {s.upper() for s in EXCLUDED_BREAK_SUBJECTS}:
                    p_name = p.get("period_name", f"Period {p.get('period_index', 0)}")
                    c_name = p.get("class_name", "")
                    slot_key = f"{p_name}__{c_name}__{subj}" if p.get("parallel_group_id") else f"{p_name}__{c_name}"
                    slots.append({
                        "key": slot_key,
                        "period_index": p.get("period_index", 0),
                        "period_name": p_name,
                        "period_time": p.get("period_time", ""),
                        "class_name": c_name,
                        "subject": subj,
                        "absent_teacher": teacher,
                        "is_joint": p.get("is_joint", False),
                        "joint_label": p.get("joint_label"),
                        "parallel_group_id": p.get("parallel_group_id"),
                        "room_type": p.get("room_type", "Classroom"),
                        "is_duty": False
                    })

            # 2. Homeroom Duties: Morning Assembly & Lunch Break
            # The class teacher pays the duty for her homeroom class. In her absence,
            # someone must be sent to supervise Morning Assembly and Lunch Break.
            ct_classes = t_info.get("is_class_teacher_of", [])
            for c_name in ct_classes:
                slots.append({
                    "key": f"Morning Assembly__{c_name}",
                    "period_index": 0,
                    "period_name": "Morning Assembly",
                    "period_time": "07:50 to 08:20",
                    "class_name": c_name,
                    "subject": "Duty: Morning Assembly",
                    "absent_teacher": teacher,
                    "is_joint": False,
                    "joint_label": None,
                    "parallel_group_id": None,
                    "room_type": "Assembly Ground",
                    "is_duty": True
                })
                slots.append({
                    "key": f"Lunch__{c_name}",
                    "period_index": 4,
                    "period_name": "Lunch",
                    "period_time": "10:45 to 11:05",
                    "class_name": c_name,
                    "subject": "Duty: Lunch Break",
                    "absent_teacher": teacher,
                    "is_joint": False,
                    "joint_label": None,
                    "parallel_group_id": None,
                    "room_type": "Classroom",
                    "is_duty": True
                })

        # Sort by period_index, then class_name
        return sorted(slots, key=lambda s: (s["period_index"], s["class_name"]))

    def rank_candidates_for_slot(
        self,
        slot: Dict[str, Any],
        day: str,
        absent_teachers: List[str],
        current_assignments: Dict[str, str],
        max_proxies_per_day: int = 2,
        max_duties_per_day: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Calculates multi-tier heuristic rankings for all free teachers for a specific slot.
        Enforces hard clash prevention, absentee exclusion, and daily proxy ceilings.
        """
        p_name = slot.get("period_name", "")
        day_roster = self.free_data.get("roster", {}).get(day, {}).get(p_name, {})
        free_candidates = day_roster.get("free_teachers", [])
        if not free_candidates:
            return []

        t_key_map = {k.strip().lower(): k for k in self.teacher_data.keys()}
        absent_set_lower = set()
        for a in absent_teachers:
            if a:
                a_clean = a.strip().lower()
                absent_set_lower.add(a_clean)
                canonical = t_key_map.get(a_clean)
                if not canonical:
                    prefix_matches = [k for k_lower, k in t_key_map.items() if k_lower.startswith(a_clean) or a_clean.startswith(k_lower)]
                    if len(prefix_matches) == 1:
                        canonical = prefix_matches[0]
                if canonical:
                    absent_set_lower.add(canonical.strip().lower())
        slot_absent_lower = (slot.get("absent_teacher") or "").strip().lower()
        slot_key = slot.get("key", "")
        target_subject = slot.get("subject") or ""
        target_class = slot.get("class_name") or ""
        is_duty = slot.get("is_duty", False) or (p_name in ("Morning Assembly", "Lunch")) or (slot.get("period_index") in (0, 4))

        # Identify teachers currently assigned to other classes in this exact period
        occupied_in_this_period = set()
        for s_key, sub_name in current_assignments.items():
            if s_key.startswith(f"{p_name}__") and s_key != slot_key:
                occupied_in_this_period.add(sub_name)

        # Count teaching proxies and duty proxies separately
        teaching_proxy_counts: Dict[str, int] = {}
        duty_proxy_counts: Dict[str, int] = {}
        for s_key, sub_name in current_assignments.items():
            if not sub_name:
                continue
            is_s_duty = (
                s_key.startswith("Morning Assembly__") or
                s_key.startswith("Lunch__") or
                "__Duty:" in s_key
            )
            if is_s_duty:
                duty_proxy_counts[sub_name] = duty_proxy_counts.get(sub_name, 0) + 1
            else:
                teaching_proxy_counts[sub_name] = teaching_proxy_counts.get(sub_name, 0) + 1

        ranked = []
        for cand in free_candidates:
            cand_name = cand.get("name", "")
            cand_name_lower = cand_name.strip().lower()

            # Hard Constraint 0: Management Faculty Excluded (Sonakshi & Shailendra Kurmi look after management)
            if is_management_teacher(cand_name):
                continue

            # Hard Constraint 1: Teacher cannot be absent today (case-insensitive & whitespace-safe)
            if cand_name_lower in absent_set_lower or any(cand_name_lower == a or cand_name_lower.startswith(a + " ") or a.startswith(cand_name_lower + " ") for a in absent_set_lower):
                continue

            # Hard Constraint 1b: Teacher cannot be assigned to cover their own class
            if cand_name_lower == slot_absent_lower:
                continue

            # Hard Constraint 1c: Teacher has marked this period as Blackout / Unavailable
            if self.is_teacher_blackout(cand_name, day, slot.get("period_index"), p_name):
                continue

            # Hard Constraint 2: Teacher cannot be assigned to another class in this period
            if cand_name in occupied_in_this_period:
                continue

            is_currently_assigned_here = (current_assignments.get(slot_key) == cand_name)

            ct_classes = cand.get("is_class_teacher_of", [])
            cand_classes = cand.get("classes", [])
            cand_subjects = cand.get("subjects", [])

            # Hard Constraint 3: Proxy ceilings
            if is_duty:
                # Class teachers must pay duty with their own homeroom class and cannot substitute
                if ct_classes:
                    continue
                d_today = duty_proxy_counts.get(cand_name, 0)
                if d_today >= max_duties_per_day and not is_currently_assigned_here:
                    continue
                # If candidate has reached overall max_proxies_per_day + (max_duties_per_day - 1), exclude from duty as well
                total_assigned_today = teaching_proxy_counts.get(cand_name, 0) + d_today
                if total_assigned_today >= (max_proxies_per_day + (max_duties_per_day - 1)) and not is_currently_assigned_here:
                    continue
            else:
                # Daily teaching proxy fatigue ceiling
                t_proxies_today = teaching_proxy_counts.get(cand_name, 0)
                if t_proxies_today >= max_proxies_per_day and not is_currently_assigned_here:
                    continue

            score = 0
            reasons = []

            if is_duty:
                # Homeroom Duty: Morning Assembly & Lunch Break
                score += 50
                reasons.append("Duty Available")

                w_score, w_reason = self.get_wing_compatibility_score(target_class, cand_name)
                score += w_score
                if w_reason:
                    reasons.append(w_reason)

                if target_class in cand_classes:
                    score += 30
                    reasons.append("Teaches Class")

                # Soft duty fatigue: prefer fresh teachers for duty
                d_today = duty_proxy_counts.get(cand_name, 0)
                score -= (d_today * 25)
                is_subj_match = False
            else:
                # Regular Academic Teaching Slot Heuristics:
                # Priority 1: Subject Specialization (+100 exact match, +60 related family)
                s_score, s_reason = match_subject(target_subject, cand_subjects)
                score += s_score
                if s_reason:
                    reasons.append(s_reason)
                is_subj_match = (s_score > 0)

                # Priority 2: Familiarity with class (+50 for Class Teacher, +40 for teaches class)
                if target_class in ct_classes:
                    score += 50
                    reasons.append("Class Teacher")
                elif target_class in cand_classes:
                    score += 40
                    reasons.append("Teaches Class")

                # Priority 3: Wing / Grade-Level Alignment (+35 same wing, +15 adjacent, -60 extreme cross-wing)
                w_score, w_reason = self.get_wing_compatibility_score(target_class, cand_name)
                score += w_score
                if w_reason:
                    reasons.append(w_reason)

                # Activity vs Academic adjustment: pure activity teachers deprioritized for academic slots
                is_academic_slot = get_subject_family(target_subject) not in ("sports", "arts", "library")
                cand_is_activity_only = cand_subjects and all(
                    get_subject_family(s) in ("sports", "arts", "library") for s in cand_subjects
                )
                if is_academic_slot and cand_is_activity_only and s_score == 0:
                    score -= 20

            # Priority 4: Light weekly workload
            load = cand.get("weekly_load", 0)
            if load < 20:
                score += 15
                reasons.append("Light Load")
            elif load < 25:
                score += 8
            elif load >= 28:
                score -= 10

            # Priority 5: Fatigue for teaching proxies
            t_proxies = teaching_proxy_counts.get(cand_name, 0)
            if t_proxies == 0:
                score += 10
            elif t_proxies == 1:
                score -= 15
            else:
                score -= 35

            ranked.append({
                "name": cand_name,
                "score": score,
                "reasons": reasons,
                "subjects": cand_subjects,
                "weekly_load": load,
                "proxies_today": t_proxies if not is_duty else duty_proxy_counts.get(cand_name, 0),
                "is_class_teacher": target_class in ct_classes,
                "teaches_this_class": target_class in cand_classes,
                "subject_match": is_subj_match
            })

        # Sort descending by score, ascending by weekly load, then alphabetical
        return sorted(ranked, key=lambda x: (-x["score"], x["weekly_load"], x["name"]))

    def auto_assign(
        self,
        day: str,
        absent_teachers: List[str],
        max_proxies_per_day: int = 2
    ) -> Dict[str, Any]:
        """
        Global constraint satisfaction auto-assigner.
        Pass 1: Solves using preferred max_proxies_per_day (default 2) with MRV.
        Pass 2: Flexible expansion to max_proxies_per_day + 1 (e.g. 3) for any unassigned slots.
        """
        slots = self.get_affected_slots(day, absent_teachers)
        if not slots:
            return {
                "success": True,
                "day": day,
                "total_slots": 0,
                "assigned_count": 0,
                "unassigned_count": 0,
                "assignments": {},
                "unassigned_slots": [],
                "proxy_counts": {}
            }

        assignments: Dict[str, str] = {}
        unassigned_slots: List[Dict[str, Any]] = []

        # --- PASS 1: Standard MRV Solver with preferred limit ---
        remaining_slots = list(slots)

        while remaining_slots:
            # Evaluate candidates for all remaining slots
            slot_candidate_map = []
            for s in remaining_slots:
                cands = self.rank_candidates_for_slot(
                    s, day, absent_teachers, assignments, max_proxies_per_day
                )
                slot_candidate_map.append((s, cands))

            # Pick slot with fewest available candidates (MRV)
            slot_candidate_map.sort(key=lambda item: len(item[1]))
            chosen_slot, candidates = slot_candidate_map[0]

            if not candidates:
                # Postpone for flexible auto-expansion pass
                unassigned_slots.append(chosen_slot)
                remaining_slots.remove(chosen_slot)
                continue

            top_cand = candidates[0]
            cand_name = top_cand["name"]

            assignments[chosen_slot["key"]] = cand_name
            remaining_slots.remove(chosen_slot)

        # --- PASS 2: Flexible Auto-Expansion (relax to max_proxies_per_day + 1) ---
        if unassigned_slots:
            retry_slots = list(unassigned_slots)
            unassigned_slots = []
            expanded_limit = max_proxies_per_day + 1

            while retry_slots:
                slot_candidate_map = []
                for s in retry_slots:
                    cands = self.rank_candidates_for_slot(
                        s, day, absent_teachers, assignments, expanded_limit, max_duties_per_day=2
                    )
                    slot_candidate_map.append((s, cands))

                slot_candidate_map.sort(key=lambda item: len(item[1]))
                chosen_slot, candidates = slot_candidate_map[0]

                if not candidates:
                    # Slot remains unassigned even with expanded limit
                    unassigned_slots.append(chosen_slot)
                    retry_slots.remove(chosen_slot)
                    continue

                top_cand = candidates[0]
                cand_name = top_cand["name"]

                assignments[chosen_slot["key"]] = cand_name
                retry_slots.remove(chosen_slot)

        # Count total proxies assigned to each teacher today
        proxy_counts: Dict[str, int] = {}
        for sub_name in assignments.values():
            if sub_name:
                proxy_counts[sub_name] = proxy_counts.get(sub_name, 0) + 1

        return {
            "success": len(unassigned_slots) == 0,
            "day": day,
            "total_slots": len(slots),
            "assigned_count": len(assignments),
            "unassigned_count": len(unassigned_slots),
            "assignments": assignments,
            "unassigned_slots": unassigned_slots,
            "proxy_counts": proxy_counts
        }

    def save_history(self, record: Dict[str, Any], history_file: Optional[str] = None) -> bool:
        """
        Atomically saves a date-stamped substitution record into substitutions_history.json.
        """
        target_path = history_file or os.path.join(self.base_dir, "substitutions_history.json")
        records = []

        if os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    records = data.get("records", [])
            except Exception:
                records = []

        date_key = record.get("date")
        # Remove previous entry for same date to allow overwrite/update
        records = [r for r in records if r.get("date") != date_key]
        records.insert(0, record)

        # Atomic write: write to temp file first, then replace
        tmp_path = target_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump({"records": records[:100]}, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, target_path)

        return True

    def get_history(self, history_file: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieves the past substitution records list.
        """
        target_path = history_file or os.path.join(self.base_dir, "substitutions_history.json")
        if not os.path.exists(target_path):
            return []

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("records", [])
        except Exception:
            return []

    def generate_substitution_report(
        self,
        day: str,
        absent_teachers: List[str],
        assignments: Dict[str, str],
        date_str: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Generates a formatted Substitution Report sorted alphabetically by
        Substitution teacher name, and secondarily by period sequence.

        Columns:
        - date: Formatted arrangement date (DD/MM/YYYY)
        - substitute_teacher: Name of the Substitution teacher
        - period: Period details with timing and class
        - subject: Subject covered or duty description
        - absent_teacher: Regular faculty member who is absent
        - signature: Blank field for teacher's signature acknowledgment
        """
        slots = self.get_affected_slots(day, absent_teachers)
        report_rows = []

        # Standard display date: convert YYYY-MM-DD to DD/MM/YYYY if applicable
        display_date = date_str or ""
        if "-" in display_date:
            parts = display_date.split("-")
            if len(parts) == 3 and len(parts[0]) == 4:
                display_date = f"{parts[2]}/{parts[1]}/{parts[0]}"

        for slot in slots:
            slot_key = slot.get("key")
            sub_name = assignments.get(slot_key)
            if not sub_name:
                continue

            p_name = slot.get("period_name", "")
            p_time = slot.get("period_time", "")
            c_name = slot.get("class_name", "")
            p_str = f"{p_name} ({p_time}) — {c_name}" if p_time else f"{p_name} — {c_name}"

            report_rows.append({
                "date": display_date,
                "substitute_teacher": sub_name,
                "period": p_str,
                "period_index": slot.get("period_index", 99),
                "period_name": p_name,
                "period_time": p_time,
                "class_name": c_name,
                "subject": slot.get("subject", ""),
                "absent_teacher": slot.get("absent_teacher", ""),
                "signature": ""
            })

        # Sort strictly by substitute_teacher name (case-insensitive A to Z), then by period_index
        report_rows.sort(key=lambda r: (r["substitute_teacher"].lower(), r["period_index"]))
        return report_rows


def sync_free_teachers(base_dir: str, config_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Rebuilds and saves free_teachers.json by evaluating occupied slots from
    timetable_teachers.json and filtering out teachers marked with Blackout /
    Unavailable slots in timetable_config.json.
    """
    config_path = os.path.join(base_dir, "timetable_config.json")
    if config_data is None and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
    config_data = config_data or {}

    teachers_path = os.path.join(base_dir, "timetable_teachers.json")
    teacher_export: Dict[str, Any] = {}
    if os.path.exists(teachers_path):
        with open(teachers_path, "r", encoding="utf-8") as f:
            teacher_export = json.load(f)

    period_defs = config_data.get("config", {}).get("period_definitions", [])
    days = config_data.get("config", {}).get("days", [
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"
    ])
    periods_meta = [
        {
            "index": p.get("period_index", 0),
            "id": f"P{p.get('period_index', 0)}",
            "name": p.get("name", f"Period {p.get('period_index', 0)}"),
            "time": p.get("time", "")
        }
        for p in period_defs
    ]

    # Map unavailable/blackout slots per teacher name
    blackout_map: Dict[str, Set[Tuple[str, int]]] = {}
    for t in config_data.get("teachers", []):
        t_name = t.get("name", "").strip().lower()
        unavail = set()
        for s in t.get("unavailable_slots", []):
            if isinstance(s, (list, tuple)) and len(s) == 2:
                unavail.add((str(s[0]), int(s[1])))
            elif isinstance(s, dict):
                unavail.add((str(s.get("day", "")), int(s.get("period_index", 0))))
        if unavail:
            blackout_map[t_name] = unavail

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

            occupied: Dict[str, Any] = {}
            for t_name, t_info in teacher_export.items():
                day_slots = t_info.get("weekly_schedule", {}).get(day, [])
                for slot in day_slots:
                    if slot.get("period_index") == p_idx:
                        occupied[t_name] = {
                            "class_name": slot.get("class_name", ""),
                            "subject": slot.get("subject", ""),
                            "raw": slot.get("raw_value", "")
                        }
                        break

            # Class teachers must pay homeroom duty during Morning Assembly and Lunch; not considered free
            is_assembly_or_lunch = (p_idx in (0, 4)) or (p_name in ("Morning Assembly", "Lunch"))
            if is_assembly_or_lunch:
                for t_name, t_info in teacher_export.items():
                    ct_classes = t_info.get("is_class_teacher_of", [])
                    if ct_classes and t_name not in occupied:
                        occupied[t_name] = {
                            "class_name": ct_classes[0],
                            "subject": f"Homeroom Duty ({p_name})",
                            "raw": f"Duty_{p_name}_{t_name}"
                        }

            free_candidates = []
            for t_name, t_info in teacher_export.items():
                if t_name not in occupied:
                    # Check if teacher has marked this slot as Blackout
                    t_lower = t_name.strip().lower()
                    t_blackouts = blackout_map.get(t_lower, set())
                    if not t_blackouts:
                        for k, b_set in blackout_map.items():
                            if k == t_lower or k.startswith(t_lower + " ") or t_lower.startswith(k + " "):
                                t_blackouts = b_set
                                break

                    if (day, p_idx) in t_blackouts:
                        continue  # EXCLUDED: On Blackout

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
                "period_info": p_info,
                "free_count": len(free_candidates),
                "busy_count": len(occupied),
                "busy_teachers": occupied,
                "free_teachers": free_candidates
            }

    free_path = os.path.join(base_dir, "free_teachers.json")
    tmp_path = free_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(free_data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, free_path)
    return free_data
