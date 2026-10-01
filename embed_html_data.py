import os
import json
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load fresh datasets
with open(os.path.join(BASE_DIR, "timetable.json"), "r", encoding="utf-8") as f:
    tt_data = json.load(f)

with open(os.path.join(BASE_DIR, "timetable_teachers.json"), "r", encoding="utf-8") as f:
    teacher_data = json.load(f)

with open(os.path.join(BASE_DIR, "free_teachers.json"), "r", encoding="utf-8") as f:
    free_data = json.load(f)

# Serialize compact JSON strings for embedding
tt_json_str = json.dumps(tt_data, ensure_ascii=False)
teacher_json_str = json.dumps(teacher_data, ensure_ascii=False)
free_json_str = json.dumps(free_data, ensure_ascii=False)

print("1. Updating index.html...")
index_path = os.path.join(BASE_DIR, "index.html")
with open(index_path, "r", encoding="utf-8") as f:
    index_content = f.read()

# Replace embedded TIMETABLE_DATA, TEACHER_DATA, FREE_DATA
index_content = re.sub(
    r'const TIMETABLE_DATA = .*?;\n',
    f'const TIMETABLE_DATA = {tt_json_str};\n',
    index_content
)
index_content = re.sub(
    r'const TEACHER_DATA = .*?;\n',
    f'const TEACHER_DATA = {teacher_json_str};\n',
    index_content
)
index_content = re.sub(
    r'const FREE_DATA = .*?;\n',
    f'const FREE_DATA = {free_json_str};\n',
    index_content
)

# Apply defensive JS fixes to index.html
# Fix 1: teacherSelect in init()
old_init_teachers = """      const teacherSelect = document.getElementById('teacher-select');
      teacherSelect.innerHTML = '';
      TIMETABLE_DATA.teachers.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t;
        const load = TEACHER_DATA[t] ? TEACHER_DATA[t].total_weekly_teaching_periods : 0;
        opt.textContent = `${t} (${load})`;
        teacherSelect.appendChild(opt);
      });"""

new_init_teachers = """      const teacherSelect = document.getElementById('teacher-select');
      teacherSelect.innerHTML = '';
      TIMETABLE_DATA.teachers.forEach(t => {
        const opt = document.createElement('option');
        const tName = typeof t === 'string' ? t : (t.teacher_name || t.name || t.id);
        opt.value = tName;
        const load = TEACHER_DATA[tName] ? TEACHER_DATA[tName].total_weekly_teaching_periods : 0;
        opt.textContent = `${tName} (${load})`;
        teacherSelect.appendChild(opt);
      });"""

if old_init_teachers in index_content:
    index_content = index_content.replace(old_init_teachers, new_init_teachers)
    print("Applied Fix 1 (init teacherSelect)")
else:
    print("Warning: old_init_teachers block not found directly, checking regex")
    index_content = re.sub(
        r'TIMETABLE_DATA\.teachers\.forEach\(t => \{\s*const opt = document\.createElement\(\'option\'\);\s*opt\.value = t;\s*const load = TEACHER_DATA\[t\] \? TEACHER_DATA\[t\]\.total_weekly_teaching_periods : 0;\s*opt\.textContent = `\$\{t\} \(\$\{load\}\)`;\s*teacherSelect\.appendChild\(opt\);\s*\}\);',
        """TIMETABLE_DATA.teachers.forEach(t => {
        const opt = document.createElement('option');
        const tName = typeof t === 'string' ? t : (t.teacher_name || t.name || t.id);
        opt.value = tName;
        const load = TEACHER_DATA[tName] ? TEACHER_DATA[tName].total_weekly_teaching_periods : 0;
        opt.textContent = `${tName} (${load})`;
        teacherSelect.appendChild(opt);
      });""",
        index_content
    )

# Fix 2: filterTeacherDropdown
old_filter = """function filterTeacherDropdown() {
      const query = document.getElementById('teacher-search').value.toLowerCase();
      const select = document.getElementById('teacher-select');
      select.innerHTML = '';
      TIMETABLE_DATA.teachers.forEach(t => {
        if (t.toLowerCase().includes(query)) {
          const opt = document.createElement('option');
          opt.value = t;
          const load = TEACHER_DATA[t] ? TEACHER_DATA[t].total_weekly_teaching_periods : 0;
          opt.textContent = `${t} (${load})`;
          select.appendChild(opt);
        }
      });
      if (select.options.length > 0) {
        renderTeacherTimetable();
      }
    }"""

new_filter = """function filterTeacherDropdown() {
      const query = document.getElementById('teacher-search').value.toLowerCase();
      const select = document.getElementById('teacher-select');
      select.innerHTML = '';
      TIMETABLE_DATA.teachers.forEach(t => {
        const tName = typeof t === 'string' ? t : (t.teacher_name || t.name || t.id);
        if (tName.toLowerCase().includes(query)) {
          const opt = document.createElement('option');
          opt.value = tName;
          const load = TEACHER_DATA[tName] ? TEACHER_DATA[tName].total_weekly_teaching_periods : 0;
          opt.textContent = `${tName} (${load})`;
          select.appendChild(opt);
        }
      });
      if (select.options.length > 0) {
        renderTeacherTimetable();
      }
    }"""

if old_filter in index_content:
    index_content = index_content.replace(old_filter, new_filter)
    print("Applied Fix 2 (filterTeacherDropdown)")

# Fix 3: renderClassTimetable defensive period_definitions
old_render_pdefs = """      const table = document.getElementById('class-table');
      const numPeriods = classObj.period_definitions.length;
      const periodWidthStyle = `style="width: calc((100% - 95px) / ${numPeriods});"`;
      let html = `<thead class="bg-slate-900 text-white border-b-2 border-slate-950 uppercase tracking-wider"><tr>`;
      html += `<th class="py-3 px-2 sticky left-0 bg-slate-950 text-white z-20 w-[95px] min-w-[95px] max-w-[95px] border-r border-slate-700 text-center font-black text-sm tt-th-day">Day</th>`;
      
      classObj.period_definitions.forEach(p => {"""

new_render_pdefs = """      const table = document.getElementById('class-table');
      const periodDefs = classObj.period_definitions || (TIMETABLE_DATA.classes && TIMETABLE_DATA.classes[0] && TIMETABLE_DATA.classes[0].period_definitions) || [];
      const numPeriods = periodDefs.length || 8;
      const periodWidthStyle = `style="width: calc((100% - 95px) / ${numPeriods});"`;
      let html = `<thead class="bg-slate-900 text-white border-b-2 border-slate-950 uppercase tracking-wider"><tr>`;
      html += `<th class="py-3 px-2 sticky left-0 bg-slate-950 text-white z-20 w-[95px] min-w-[95px] max-w-[95px] border-r border-slate-700 text-center font-black text-sm tt-th-day">Day</th>`;
      
      periodDefs.forEach(p => {"""

if old_render_pdefs in index_content:
    index_content = index_content.replace(old_render_pdefs, new_render_pdefs)
    print("Applied Fix 3 (renderClassTimetable periodDefs)")
else:
    print("Warning: old_render_pdefs not found directly, checking regex")
    index_content = re.sub(
        r'const numPeriods = classObj\.period_definitions\.length;\s*const periodWidthStyle = `style="width: calc\(\(100% - 95px\) / \$\{numPeriods\}\);"`\;\s*let html = `<thead class="bg-slate-900 text-white border-b-2 border-slate-950 uppercase tracking-wider"><tr>`;\s*html \+= `<th class="py-3 px-2 sticky left-0 bg-slate-950 text-white z-20 w-\[95px\] min-w-\[95px\] max-w-\[95px\] border-r border-slate-700 text-center font-black text-sm tt-th-day">Day</th>`;\s*classObj\.period_definitions\.forEach\(p => \{',
        """const periodDefs = classObj.period_definitions || (TIMETABLE_DATA.classes && TIMETABLE_DATA.classes[0] && TIMETABLE_DATA.classes[0].period_definitions) || [];
      const numPeriods = periodDefs.length || 8;
      const periodWidthStyle = `style="width: calc((100% - 95px) / ${numPeriods});"`;
      let html = `<thead class="bg-slate-900 text-white border-b-2 border-slate-950 uppercase tracking-wider"><tr>`;
      html += `<th class="py-3 px-2 sticky left-0 bg-slate-950 text-white z-20 w-[95px] min-w-[95px] max-w-[95px] border-r border-slate-700 text-center font-black text-sm tt-th-day">Day</th>`;
      
      periodDefs.forEach(p => {""",
        index_content
    )

with open(index_path, "w", encoding="utf-8") as f:
    f.write(index_content)
print("Saved index.html successfully.")

print("2. Updating free_teachers.html...")
free_html_path = os.path.join(BASE_DIR, "free_teachers.html")
with open(free_html_path, "r", encoding="utf-8") as f:
    free_html = f.read()

free_html = re.sub(
    r'const FREE_DATA = .*?;\n',
    f'const FREE_DATA = {free_json_str};\n',
    free_html
)
free_html = re.sub(
    r'const TEACHER_DATA = .*?;\n',
    f'const TEACHER_DATA = {teacher_json_str};\n',
    free_html
)

with open(free_html_path, "w", encoding="utf-8") as f:
    f.write(free_html)
print("Saved free_teachers.html successfully.")
