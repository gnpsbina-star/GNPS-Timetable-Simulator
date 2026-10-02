"""
Excel Timetable Exporter Module.
Generates professional, styled multi-sheet Microsoft Excel (.xlsx) workbooks 
for individual classes or any custom range (Class X to Class Y) without external C-extensions.
"""

import io
import re
import zipfile
from xml.sax.saxutils import escape
from typing import List, Dict, Any, Optional

def sanitize_sheet_name(name: str) -> str:
    """Sanitize sheet name for Excel (max 31 chars, no invalid characters \\ / ? * : [ ])."""
    clean = re.sub(r'CLASS\s*', '', name, flags=re.IGNORECASE)
    clean = re.sub(r'[\\/\?\*:\(\)\[\]]', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean[:31] if clean else "Class Sheet"

def _resolve_class_index(query: Optional[str], names: List[str], is_end: bool = False) -> int:
    default_val = len(names) - 1 if is_end else 0
    if not query or not names:
        return default_val
    q = query.strip().lower()
    if not q:
        return default_val
    # 1. Exact or case-insensitive match
    for idx, n in enumerate(names):
        if n.lower() == q:
            return idx
    # 2. Stripped "CLASS" match (e.g. '6 Rose' matches 'CLASS 6 Rose')
    for idx, n in enumerate(names):
        clean = re.sub(r'^CLASS\s*', '', n, flags=re.IGNORECASE).strip().lower()
        if clean == q:
            return idx
    # 3. Grade / partial match (e.g. '6' matches 'CLASS 6 ...')
    matches = []
    for idx, n in enumerate(names):
        nl = n.lower()
        if q in nl or f"class {q}" in nl or f" {q} " in f" {nl} ":
            matches.append(idx)
    if matches:
        return matches[-1] if is_end else matches[0]
    return default_val

def get_class_range_slice(all_classes: List[Dict[str, Any]], from_class: Optional[str], to_class: Optional[str]) -> List[Dict[str, Any]]:
    """Extracts a slice of classes from from_class to to_class (inclusive)."""
    if not all_classes:
        return []
    
    names = [c["class_name"] for c in all_classes]
    
    from_idx = _resolve_class_index(from_class, names, is_end=False)
    to_idx = _resolve_class_index(to_class, names, is_end=True)
        
    if from_idx > to_idx:
        from_idx, to_idx = to_idx, from_idx
        
    return all_classes[from_idx : to_idx + 1]

def col_idx_to_letter(col_idx: int) -> str:
    """Convert 1-based column index to Excel letter (1 -> A, 2 -> B, ..., 27 -> AA)."""
    result = ""
    while col_idx > 0:
        col_idx, remainder = divmod(col_idx - 1, 26)
        result = chr(65 + remainder) + result
    return result

def build_styles_xml() -> str:
    """Constructs the OpenXML stylesheet with school colors and borders."""
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="8">
    <!-- 0: Normal Base -->
    <font><sz val="10"/><name val="Calibri"/></font>
    <!-- 1: School Main Title (White, 15pt, Bold) -->
    <font><b/><sz val="15"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
    <!-- 2: Class Subtitle / Banner (White, 11pt, Bold) -->
    <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
    <!-- 3: Table Header (White, 10pt, Bold) -->
    <font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
    <!-- 4: Cell Bold Subject (Slate, 10pt, Bold) -->
    <font><b/><sz val="10"/><color rgb="FF0F172A"/><name val="Calibri"/></font>
    <!-- 5: Cell Normal (Slate, 9.5pt) -->
    <font><sz val="9.5"/><color rgb="FF1E293B"/><name val="Calibri"/></font>
    <!-- 6: Lunch Cell Text (Amber-950, 9.5pt, Bold) -->
    <font><b/><sz val="9.5"/><color rgb="FF78350F"/><name val="Calibri"/></font>
    <!-- 7: Separator Text (Slate-500, 9pt, Bold) -->
    <font><b/><sz val="9"/><color rgb="FF64748B"/><name val="Calibri"/></font>
  </fonts>
  <fills count="10">
    <!-- 0: None -->
    <fill><patternFill patternType="none"/></fill>
    <!-- 1: Gray125 -->
    <fill><patternFill patternType="gray125"/></fill>
    <!-- 2: Deep Indigo / Navy Title (#1E1B4B) -->
    <fill><patternFill patternType="solid"><fgColor rgb="FF1E1B4B"/></patternFill></fill>
    <!-- 3: Slate Class Banner (#1E293B) -->
    <fill><patternFill patternType="solid"><fgColor rgb="FF1E293B"/></patternFill></fill>
    <!-- 4: Table Header Dark (#0F172A) -->
    <fill><patternFill patternType="solid"><fgColor rgb="FF0F172A"/></patternFill></fill>
    <!-- 5: Lunch Warm Amber Tint (#FEF3C7) -->
    <fill><patternFill patternType="solid"><fgColor rgb="FFFEF3C7"/></patternFill></fill>
    <!-- 6: Games Soft Emerald Tint (#ECFDF5) -->
    <fill><patternFill patternType="solid"><fgColor rgb="FFECFDF5"/></patternFill></fill>
    <!-- 7: Lunch Column Header Amber (#F59E0B) -->
    <fill><patternFill patternType="solid"><fgColor rgb="FFF59E0B"/></patternFill></fill>
    <!-- 8: Day Column Light Slate (#F1F5F9) -->
    <fill><patternFill patternType="solid"><fgColor rgb="FFF1F5F9"/></patternFill></fill>
    <!-- 9: Divider Row Light Slate (#F8FAFC) -->
    <fill><patternFill patternType="solid"><fgColor rgb="FFF8FAFC"/></patternFill></fill>
  </fills>
  <borders count="2">
    <!-- 0: None -->
    <border><left/><right/><top/><bottom/></border>
    <!-- 1: Thin Slate Grid Border (#CBD5E1) -->
    <border>
      <left style="thin"><color rgb="FFCBD5E1"/></left>
      <right style="thin"><color rgb="FFCBD5E1"/></right>
      <top style="thin"><color rgb="FFCBD5E1"/></top>
      <bottom style="thin"><color rgb="FFCBD5E1"/></bottom>
    </border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="10">
    <!-- 0: Default -->
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
    <!-- 1: School Title -->
    <xf numFmtId="0" fontId="1" fillId="2" borderId="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">
      <alignment horizontal="center" vertical="center"/>
    </xf>
    <!-- 2: Class Subtitle / Banner (wrapText=1) -->
    <xf numFmtId="0" fontId="2" fillId="3" borderId="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">
      <alignment horizontal="center" vertical="center" wrapText="1"/>
    </xf>
    <!-- 3: Table Column Header -->
    <xf numFmtId="0" fontId="3" fillId="4" borderId="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">
      <alignment horizontal="center" vertical="center" wrapText="1"/>
    </xf>
    <!-- 4: Day Column Header / Cell -->
    <xf numFmtId="0" fontId="4" fillId="8" borderId="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">
      <alignment horizontal="center" vertical="center"/>
    </xf>
    <!-- 5: Regular Timetable Period Cell -->
    <xf numFmtId="0" fontId="5" fillId="0" borderId="1" applyFont="1" applyBorder="1" applyAlignment="1">
      <alignment horizontal="center" vertical="center" wrapText="1"/>
    </xf>
    <!-- 6: Lunch Period Cell -->
    <xf numFmtId="0" fontId="6" fillId="5" borderId="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">
      <alignment horizontal="center" vertical="center" wrapText="1"/>
    </xf>
    <!-- 7: Games Period Cell -->
    <xf numFmtId="0" fontId="4" fillId="6" borderId="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">
      <alignment horizontal="center" vertical="center" wrapText="1"/>
    </xf>
    <!-- 8: Lunch Column Header (Amber bg, Dark bold text) -->
    <xf numFmtId="0" fontId="4" fillId="7" borderId="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">
      <alignment horizontal="center" vertical="center" wrapText="1"/>
    </xf>
    <!-- 9: Divider Row Cell -->
    <xf numFmtId="0" fontId="7" fillId="9" borderId="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">
      <alignment horizontal="center" vertical="center"/>
    </xf>
  </cellXfs>
</styleSheet>"""

def build_class_worksheet_xml(class_data: Dict[str, Any], academic_year: str = "2026-27") -> str:
    """Renders a single class timetable grid into OpenXML worksheet format."""
    c_name = class_data.get("class_name", "")
    ct_name = class_data.get("class_teacher", "Not Assigned")
    p_defs = class_data.get("period_definitions", [])
    schedule = class_data.get("schedule", {})
    
    total_cols = len(p_defs) + 1  # Col A = Day, Cols B.. = Periods
    last_col_letter = col_idx_to_letter(total_cols)
    
    # Column widths
    col_xml = f"""  <cols>
    <col min="1" max="1" width="14" customWidth="1"/>
    <col min="2" max="{total_cols}" width="23" customWidth="1"/>
  </cols>"""

    rows_xml = []
    
    # Row 1: School Title Banner
    rows_xml.append(f"""    <row r="1" ht="32" customHeight="1">
      <c r="A1" s="1" t="inlineStr"><is><t>GOMTI NANDAN PUBLIC SCHOOL, BINA</t></is></c>
    </row>""")
    
    # Row 2: Class & Session Subtitle
    rows_xml.append(f"""    <row r="2" ht="26" customHeight="1">
      <c r="A2" s="2" t="inlineStr"><is><t>{escape(c_name.upper())} — WEEKLY TIMETABLE ({escape(academic_year)})</t></is></c>
    </row>""")

    # Row 3: Class Teacher & Timings Info
    ct_info = f"Class Teacher: {ct_name}    |    Timings: 07:50 AM to 01:10 PM"
    rows_xml.append(f"""    <row r="3" ht="22" customHeight="1">
      <c r="A3" s="5" t="inlineStr"><is><t>{escape(ct_info)}</t></is></c>
    </row>""")

    # Row 4: Empty space
    rows_xml.append("""    <row r="4" ht="10" customHeight="1"/>""")

    # Row 5: Table Header Row
    header_cells = ['<c r="A5" s="3" t="inlineStr"><is><t>DAY</t></is></c>']
    for p_i, p in enumerate(p_defs):
        c_letter = col_idx_to_letter(p_i + 2)
        p_name = p.get("name", f"Period {p_i}")
        p_time = p.get("time", "")
        header_text = f"{p_name}\n({p_time})" if p_time else p_name
        header_cells.append(f'<c r="{c_letter}5" s="3" t="inlineStr"><is><t>{escape(header_text)}</t></is></c>')
        
    rows_xml.append(f"""    <row r="5" ht="36" customHeight="1">
      {''.join(header_cells)}
    </row>""")

    # Rows 6..11: Monday through Saturday
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    row_num = 6
    for day in days:
        day_cells = [f'<c r="A{row_num}" s="4" t="inlineStr"><is><t>{escape(day)}</t></is></c>']
        day_schedule = schedule.get(day, [])
        
        for p_i, p in enumerate(p_defs):
            c_letter = col_idx_to_letter(p_i + 2)
            slot = next((s for s in day_schedule if s.get("period_index") == p.get("period_index")), None)
            
            if slot:
                subj = slot.get("subject", "")
                teach = slot.get("teacher", "")
                raw = slot.get("raw_value", "")
                
                # Check slot type
                is_lunch = p.get("is_lunch") or subj == "Lunch" or "Lunch" in raw
                is_games = subj in ["Games", "Sports", "PE"]
                
                if is_lunch:
                    style_id = 6
                    cell_text = f"LUNCH BREAK\n({teach})" if teach else "LUNCH BREAK"
                elif is_games:
                    style_id = 7
                    cell_text = f"{subj.upper()}\n({teach})" if teach else subj.upper()
                elif subj == "Morning Assembly" or "Assembly" in raw:
                    style_id = 5
                    cell_text = f"ASSEMBLY\n({teach or ct_name})"
                elif subj:
                    style_id = 5
                    cell_text = f"{subj}\n({teach})" if teach else subj
                else:
                    style_id = 5
                    cell_text = "—"
            else:
                style_id = 5
                cell_text = "—"
                
            day_cells.append(f'<c r="{c_letter}{row_num}" s="{style_id}" t="inlineStr"><is><t>{escape(cell_text)}</t></is></c>')

        rows_xml.append(f"""    <row r="{row_num}" ht="46" customHeight="1">
      {''.join(day_cells)}
    </row>""")
        row_num += 1

    # Merge cells for title rows A1:lastCol, A2:lastCol, A3:lastCol
    merge_xml = f"""  <mergeCells count="3">
    <mergeCell ref="A1:{last_col_letter}1"/>
    <mergeCell ref="A2:{last_col_letter}2"/>
    <mergeCell ref="A3:{last_col_letter}3"/>
  </mergeCells>"""

    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
{col_xml}
  <sheetData>
{chr(10).join(rows_xml)}
  </sheetData>
{merge_xml}
</worksheet>"""

def build_summary_worksheet_xml(classes_subset: List[Dict[str, Any]], academic_year: str = "2026-27") -> str:
    """Renders a master summary table listing all selected classes."""
    rows_xml = []
    
    # Title
    rows_xml.append("""    <row r="1" ht="30" customHeight="1">
      <c r="A1" s="1" t="inlineStr"><is><t>GOMTI NANDAN PUBLIC SCHOOL, BINA - TIMETABLE RANGE SUMMARY</t></is></c>
    </row>""")
    
    rows_xml.append(f"""    <row r="2" ht="24" customHeight="1">
      <c r="A2" s="2" t="inlineStr"><is><t>Session: {escape(academic_year)} | Total Classes in Range: {len(classes_subset)}</t></is></c>
    </row>""")
    
    rows_xml.append("""    <row r="3" ht="10" customHeight="1"/>""")
    
    # Headers
    rows_xml.append("""    <row r="4" ht="28" customHeight="1">
      <c r="A4" s="3" t="inlineStr"><is><t>S.No</t></is></c>
      <c r="B4" s="3" t="inlineStr"><is><t>Class & Section</t></is></c>
      <c r="C4" s="3" t="inlineStr"><is><t>Class Teacher</t></is></c>
      <c r="D4" s="3" t="inlineStr"><is><t>Active Periods / Week</t></is></c>
      <c r="E4" s="3" t="inlineStr"><is><t>Weekly Games</t></is></c>
      <c r="F4" s="3" t="inlineStr"><is><t>Weekly Art & Craft</t></is></c>
    </row>""")
    
    for idx, c in enumerate(classes_subset, start=1):
        r_num = idx + 4
        c_name = c.get("class_name", "")
        ct = c.get("class_teacher", "Not Assigned")
        
        # Count teaching slots
        total_p = 0
        games_p = 0
        art_p = 0
        for day, p_list in c.get("schedule", {}).items():
            for p in p_list:
                s = p.get("subject", "")
                if s and s not in ["Lunch", "Prayer", "Morning Assembly"]:
                    total_p += 1
                if s in ["Games", "Sports"]:
                    games_p += 1
                if s == "Art & Craft":
                    art_p += 1
                    
        rows_xml.append(f"""    <row r="{r_num}" ht="22" customHeight="1">
      <c r="A{r_num}" s="5" t="inlineStr"><is><t>{idx}</t></is></c>
      <c r="B{r_num}" s="5" t="inlineStr"><is><t>{escape(c_name)}</t></is></c>
      <c r="C{r_num}" s="5" t="inlineStr"><is><t>{escape(ct)}</t></is></c>
      <c r="D{r_num}" s="5" t="inlineStr"><is><t>{total_p}</t></is></c>
      <c r="E{r_num}" s="5" t="inlineStr"><is><t>{games_p}</t></is></c>
      <c r="F{r_num}" s="5" t="inlineStr"><is><t>{art_p}</t></is></c>
    </row>""")

    cols_xml = """  <cols>
    <col min="1" max="1" width="8" customWidth="1"/>
    <col min="2" max="2" width="28" customWidth="1"/>
    <col min="3" max="3" width="26" customWidth="1"/>
    <col min="4" max="4" width="22" customWidth="1"/>
    <col min="5" max="5" width="24" customWidth="1"/>
    <col min="6" max="6" width="22" customWidth="1"/>
  </cols>"""

    merge_xml = """  <mergeCells count="2">
    <mergeCell ref="A1:F1"/>
    <mergeCell ref="A2:F2"/>
  </mergeCells>"""

    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
{cols_xml}
  <sheetData>
{chr(10).join(rows_xml)}
  </sheetData>
{merge_xml}
</worksheet>"""

def build_stacked_worksheet_xml(classes_subset: List[Dict[str, Any]], academic_year: str = "2026-27") -> str:
    """
    Renders all selected classes sequentially into a single unified master worksheet.
    - Class name & class teacher in the same banner cell (one below other with wrapText).
    - Top header row with Period Numbers and Timings for EACH class.
    - Lunch Break strictly in Column F across all classes.
    - Clean separator row between classes.
    """
    cols_xml = """  <cols>
    <col min="1" max="1" width="14" customWidth="1"/>
    <col min="2" max="10" width="23" customWidth="1"/>
  </cols>"""

    rows_xml = []
    merges = []

    # Row 1: Master School Title Banner
    school_title = f"GOMTI NANDAN PUBLIC SCHOOL, BINA — MASTER TIMETABLE ({academic_year})"
    rows_xml.append(f"""    <row r="1" ht="32" customHeight="1">
      <c r="A1" s="1" t="inlineStr"><is><t>{escape(school_title)}</t></is></c>
    </row>""")
    merges.append("A1:J1")

    current_row = 2

    # Period configuration (columns B through J)
    period_cols = [
        {"col": "B", "idx": 0, "name": "MORNING ASSEMBLY", "time": "07:50 to 08:20", "is_lunch": False},
        {"col": "C", "idx": 1, "name": "1ST PERIOD", "time": "08:30 to 9:15", "is_lunch": False},
        {"col": "D", "idx": 2, "name": "2ND PERIOD", "time": "9:15 to 10:00", "is_lunch": False},
        {"col": "E", "idx": 3, "name": "3RD PERIOD", "time": "10:00 to 10:45", "is_lunch": False},
        {"col": "F", "idx": 4, "name": "LUNCH BREAK", "time": "10:45 to 11:05", "is_lunch": True},
        {"col": "G", "idx": 5, "name": "4TH PERIOD", "time": "11:05 to 11:50", "is_lunch": False},
        {"col": "H", "idx": 6, "name": "5TH PERIOD", "time": "11:50 to 12:30", "is_lunch": False},
        {"col": "I", "idx": 7, "name": "6TH PERIOD", "time": "12:30 to 1:10", "is_lunch": False},
        {"col": "J", "idx": 8, "name": "7TH PERIOD", "time": "1:10 to 1:50", "is_lunch": False},
    ]

    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    for cls in classes_subset:
        c_name = cls.get("class_name", "").upper()
        ct_name = cls.get("class_teacher", "Not Assigned")

        # 1. Class Banner Row (Class & Teacher in Same Cell, One Below Other)
        banner_r = current_row
        banner_text = f"{c_name}\nClass Teacher: {ct_name}"
        escaped_banner = escape(banner_text).replace("\n", "&#10;")
        rows_xml.append(f"""    <row r="{banner_r}" ht="32" customHeight="1">
      <c r="A{banner_r}" s="2" t="inlineStr"><is><t xml:space="preserve">{escaped_banner}</t></is></c>
    </row>""")
        merges.append(f"A{banner_r}:J{banner_r}")
        current_row += 1

        # 2. Period Numbers & Timings Header Row (repeated for this class)
        header_r = current_row
        header_cells = [f'<c r="A{header_r}" s="3" t="inlineStr"><is><t>DAY</t></is></c>']
        for p in period_cols:
            style_id = 8 if p["is_lunch"] else 3
            header_text = f"{p['name']}\n({p['time']})"
            escaped_ht = escape(header_text).replace("\n", "&#10;")
            header_cells.append(f'<c r="{p["col"]}{header_r}" s="{style_id}" t="inlineStr"><is><t xml:space="preserve">{escaped_ht}</t></is></c>')

        rows_xml.append(f"""    <row r="{header_r}" ht="36" customHeight="1">
      {''.join(header_cells)}
    </row>""")
        current_row += 1

        # 3. Monday through Saturday rows
        day_schedule_map = cls.get("schedule", {})
        for day in days:
            day_r = current_row
            day_cells = [f'<c r="A{day_r}" s="4" t="inlineStr"><is><t>{escape(day)}</t></is></c>']
            day_slots = day_schedule_map.get(day, [])

            for p in period_cols:
                p_idx = p["idx"]
                col_letter = p["col"]
                slot = next((s for s in day_slots if s.get("period_index") == p_idx), None)

                if p["is_lunch"]:
                    duty_teach = slot.get("teacher") if slot else None
                    if not duty_teach:
                        duty_teach = ct_name
                    cell_text = f"LUNCH BREAK\n(Duty: {duty_teach})" if duty_teach else "LUNCH BREAK"
                    style_id = 6
                elif p_idx == 0:  # Assembly
                    teach = slot.get("teacher") if slot else None
                    cell_text = f"ASSEMBLY\n({teach or ct_name})"
                    style_id = 5
                elif slot and slot.get("subject"):
                    subj = slot.get("subject", "").strip()
                    teach = slot.get("teacher", "").strip()
                    is_games = subj in ["Games", "Sports", "PE"]
                    style_id = 7 if is_games else 5
                    cell_text = f"{subj}\n({teach})" if teach else subj
                else:
                    style_id = 5
                    cell_text = "—"

                escaped_ct = escape(cell_text).replace("\n", "&#10;")
                day_cells.append(f'<c r="{col_letter}{day_r}" s="{style_id}" t="inlineStr"><is><t xml:space="preserve">{escaped_ct}</t></is></c>')

            rows_xml.append(f"""    <row r="{day_r}" ht="44" customHeight="1">
      {''.join(day_cells)}
    </row>""")
            current_row += 1

        # 4. Clean Separator Row between classes
        sep_r = current_row
        rows_xml.append(f"""    <row r="{sep_r}" ht="16" customHeight="1">
      <c r="A{sep_r}" s="9" t="inlineStr"><is><t>↓ NEXT CLASS DIRECTLY BELOW ↓</t></is></c>
    </row>""")
        merges.append(f"A{sep_r}:J{sep_r}")
        current_row += 1

    merge_tags = [f'    <mergeCell ref="{m}"/>' for m in merges]
    merge_xml = f"""  <mergeCells count="{len(merges)}">
{chr(10).join(merge_tags)}
  </mergeCells>"""

    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
{cols_xml}
  <sheetData>
{chr(10).join(rows_xml)}
  </sheetData>
{merge_xml}
</worksheet>"""

def export_classes_to_excel(
    all_classes: List[Dict[str, Any]],
    from_class: Optional[str] = None,
    to_class: Optional[str] = None,
    academic_year: str = "2026-27",
    layout: str = "stacked"
) -> bytes:
    """
    Builds a professional .xlsx workbook containing all classes in the specified range.
    - layout="stacked" (default): Generates a single master worksheet where classes are stacked
      one below the other, with Lunch in Column F, Class & Teacher in same cell, and Period/Time headers.
    - layout="tabs": Generates separate worksheet tabs for each class.
    Returns the binary .xlsx bytes.
    """
    selected_classes = get_class_range_slice(all_classes, from_class, to_class)
    if not selected_classes:
        selected_classes = all_classes

    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        # 1. Styles
        z.writestr("xl/styles.xml", build_styles_xml())

        # 2. Worksheets
        sheet_entries = []

        if layout == "tabs":
            # First: Summary Sheet
            summary_sheet_xml = build_summary_worksheet_xml(selected_classes, academic_year)
            z.writestr("xl/worksheets/sheet1.xml", summary_sheet_xml)
            sheet_entries.append(("Range Summary", "sheet1.xml"))

            # Individual Class Sheets
            used_sheet_names = {"Range Summary"}
            for idx, cls in enumerate(selected_classes, start=2):
                raw_s_name = sanitize_sheet_name(cls.get("class_name", f"Class {idx-1}"))
                s_name = raw_s_name
                suffix = 1
                while s_name in used_sheet_names:
                    suffix += 1
                    s_name = f"{raw_s_name[:28]} {suffix}"
                used_sheet_names.add(s_name)

                class_xml = build_class_worksheet_xml(cls, academic_year)
                part_name = f"sheet{idx}.xml"
                z.writestr(f"xl/worksheets/{part_name}", class_xml)
                sheet_entries.append((s_name, part_name))
        else:
            # Stacked Layout (Default): Single unified master worksheet
            stacked_sheet_xml = build_stacked_worksheet_xml(selected_classes, academic_year)
            z.writestr("xl/worksheets/sheet1.xml", stacked_sheet_xml)
            sheet_entries.append(("Master Timetable", "sheet1.xml"))

            # Second: Summary Sheet
            summary_sheet_xml = build_summary_worksheet_xml(selected_classes, academic_year)
            z.writestr("xl/worksheets/sheet2.xml", summary_sheet_xml)
            sheet_entries.append(("Range Summary", "sheet2.xml"))

        # 3. Content Types
        override_tags = [
            f'  <Override PartName="/xl/worksheets/{part}" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for _, part in sheet_entries
        ]
        content_types_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
{chr(10).join(override_tags)}
</Types>"""
        z.writestr("[Content_Types].xml", content_types_xml)

        # 4. _rels/.rels
        z.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""")

        # 5. xl/_rels/workbook.xml.rels
        rel_tags = []
        for i, (_, part) in enumerate(sheet_entries, start=1):
            rel_tags.append(
                f'  <Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/{part}"/>'
            )
        styles_rid = len(sheet_entries) + 1
        rel_tags.append(
            f'  <Relationship Id="rId{styles_rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        )

        workbook_rels_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{chr(10).join(rel_tags)}
</Relationships>"""
        z.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)

        # 6. xl/workbook.xml
        sheet_tags = [
            f'    <sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
            for i, (name, _) in enumerate(sheet_entries, start=1)
        ]
        workbook_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
{chr(10).join(sheet_tags)}
  </sheets>
</workbook>"""
        z.writestr("xl/workbook.xml", workbook_xml)

    return bio.getvalue()
