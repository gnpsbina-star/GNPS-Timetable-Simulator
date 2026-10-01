#!/usr/bin/env python3
import os
import re
import json
import sqlite3
import csv
import zipfile
import xml.etree.ElementTree as ET

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_FILE = os.path.join(BASE_DIR, 'New Timetable 2026-27.xlsx')

def col2num(col_str):
    num = 0
    for c in col_str:
        num = num * 26 + (ord(c.upper()) - ord('A')) + 1
    return num

def parse_xlsx(file_path):
    with zipfile.ZipFile(file_path) as z:
        shared_strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            tree = ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in tree.findall('.//{*}si'):
                text = ''.join(t.text for t in si.findall('.//{*}t') if t.text)
                shared_strings.append(text)
                
        def get_sheet_data(sheet_name):
            if sheet_name not in z.namelist():
                return {}
            sheet_tree = ET.fromstring(z.read(sheet_name))
            rows_data = {}
            for row in sheet_tree.findall('.//{*}row'):
                r_idx = int(row.attrib.get('r', 0))
                rows_data[r_idx] = {}
                for c in row.findall('.//{*}c'):
                    cell_ref = c.attrib.get('r', '')
                    col_letters = ''.join(re.findall(r'[A-Za-z]+', cell_ref))
                    col_idx = col2num(col_letters)
                    cell_type = c.attrib.get('t', '')
                    val_elem = c.find('.//{*}v')
                    val = val_elem.text if val_elem is not None else ''
                    if cell_type == 's' and val.isdigit():
                        val = shared_strings[int(val)]
                    elif cell_type == 'inlineStr':
                        is_elem = c.find('.//{*}is')
                        if is_elem is not None:
                            val = ''.join(t.text for t in is_elem.findall('.//{*}t') if t.text)
                    rows_data[r_idx][col_idx] = val
            return rows_data

        sheet1_data = get_sheet_data('xl/worksheets/sheet1.xml')
        sheet2_data = get_sheet_data('xl/worksheets/sheet2.xml')
        return sheet1_data, sheet2_data

def clean_name(name):
    if not name:
        return ''
    return re.sub(r'\s+', ' ', name).strip()

def process_timetable():
    print(f'Reading {EXCEL_FILE}...')
    sheet1_data, sheet2_data = parse_xlsx(EXCEL_FILE)

    # 1. School Timings
    school_timings = []
    for r in range(2, 9):
        c1 = clean_name(sheet1_data.get(r, {}).get(1, ''))
        c2 = clean_name(sheet1_data.get(r, {}).get(2, ''))
        if c1 and c2 and c1.upper() != 'CLASS':
            school_timings.append({'category': c1, 'timings': c2})

    # 2. Classes & Schedules
    classes_list = []
    flat_entries = []
    teacher_schedule_map = {}
    all_teachers = set()
    all_subjects = set()

    entry_id = 1
    r = 10
    max_r = max(sheet1_data.keys()) if sheet1_data else 350

    while r <= min(max_r, 350):
        cols = sheet1_data.get(r, {})
        col1 = clean_name(cols.get(1, ''))
        col2 = clean_name(cols.get(2, ''))
        
        if col2.upper() == 'DAY' or col1.upper().startswith('CLASS'):
            class_name = col1
            
            # Parse period column headers
            period_defs = []
            c = 3
            while c in cols:
                raw_h = cols.get(c, '').strip()
                if not raw_h or raw_h in ['1.0', '1', 'Total']:
                    c += 1
                    continue
                parts = [p.strip() for p in raw_h.split('\n') if p.strip()]
                p_name = parts[0] if len(parts) > 0 else f'Period {c-2}'
                p_time = parts[1] if len(parts) > 1 else ''
                if not p_time and ('to' in p_name or '-' in p_name):
                    p_time = p_name
                    p_name = 'Morning Assembly'
                
                period_defs.append({
                    'col_idx': c,
                    'period_index': len(period_defs),
                    'name': p_name,
                    'time': p_time,
                    'raw_header': raw_h.replace('\n', ' ')
                })
                c += 1

            # Parse days
            class_teacher = ''
            days_schedule = {}
            for day_r in range(r + 1, r + 8):
                d_cols = sheet1_data.get(day_r, {})
                day_name = clean_name(d_cols.get(2, ''))
                teacher_cell = clean_name(d_cols.get(1, ''))
                if not class_teacher and teacher_cell:
                    class_teacher = teacher_cell
                    all_teachers.add(class_teacher)

                if day_name in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']:
                    day_periods = []
                    for p_def in period_defs:
                        cell_val = clean_name(d_cols.get(p_def['col_idx'], ''))
                        
                        subj = ''
                        teach = ''
                        if p_def.get('period_index') == 0 or 'Assembly' in p_def.get('name', '') or '07:50' in p_def.get('time', ''):
                            subj = 'Morning Assembly'
                            teach = ''
                            cell_val = 'Morning Assembly'
                        elif p_def.get('is_lunch') or 'Lunch' in p_def.get('name', '') or 'Lunch' in cell_val or p_def.get('period_index') == 4:
                            subj = 'Lunch'
                            teach = class_teacher
                            cell_val = f'Lunch _ {class_teacher}'
                        elif cell_val:
                            if '_' in cell_val:
                                s_parts = cell_val.split('_', 1)
                                subj = clean_name(s_parts[0])
                                teach = clean_name(s_parts[1])
                                if teach: all_teachers.add(teach)
                                if subj: all_subjects.add(subj)
                            else:
                                subj = cell_val
                                if subj: all_subjects.add(subj)

                        period_obj = {
                            'period_index': p_def['period_index'],
                            'period_name': p_def['name'],
                            'period_time': p_def['time'],
                            'raw_value': cell_val,
                            'subject': subj,
                            'teacher': teach
                        }
                        day_periods.append(period_obj)

                        # Flat entry
                        flat_entries.append({
                            'entry_id': entry_id,
                            'class_name': class_name,
                            'class_teacher': class_teacher,
                            'day': day_name,
                            'period_index': p_def['period_index'],
                            'period_name': p_def['name'],
                            'period_time': p_def['time'],
                            'raw_value': cell_val,
                            'subject': subj,
                            'teacher': teach
                        })
                        entry_id += 1

                        # Inverted teacher schedule
                        if teach:
                            teachers_to_add = [clean_name(t) for t in re.split(r'[/,]', teach) if clean_name(t)]
                            for t_name in teachers_to_add:
                                if t_name not in teacher_schedule_map:
                                    teacher_schedule_map[t_name] = {}
                                if day_name not in teacher_schedule_map[t_name]:
                                    teacher_schedule_map[t_name][day_name] = []
                                teacher_schedule_map[t_name][day_name].append({
                                    'class_name': class_name,
                                    'period_index': p_def['period_index'],
                                    'period_name': p_def['name'],
                                    'period_time': p_def['time'],
                                    'subject': subj,
                                    'raw_value': cell_val
                                })

                    days_schedule[day_name] = day_periods

            classes_list.append({
                'class_name': class_name,
                'class_teacher': class_teacher,
                'period_definitions': period_defs,
                'schedule': days_schedule
            })
            r += 7
        else:
            r += 1

    # Parse Sheet2 special allocations (lab schedule)
    lab_entries = []
    if sheet2_data:
        curr_teacher = ''
        s2_header = []
        for r_idx, cols in sorted(sheet2_data.items()):
            col2 = clean_name(cols.get(2, ''))
            col1 = clean_name(cols.get(1, ''))
            if col2.upper() == 'DAY':
                s2_header = [cols.get(c, '').strip() for c in range(3, 10) if cols.get(c, '')]
            elif col2 in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']:
                if col1:
                    curr_teacher = col1
                for c_idx in range(3, 3 + len(s2_header)):
                    val = clean_name(cols.get(c_idx, ''))
                    if val:
                        lab_entries.append({
                            'teacher': curr_teacher,
                            'day': col2,
                            'slot': s2_header[c_idx - 3] if (c_idx - 3) < len(s2_header) else f'Slot {c_idx-2}',
                            'details': val
                        })

    for s in ['', 'Prayer', 'CYCLE TEST', 'CCA']:
        all_subjects.discard(s)
    all_subjects.add('Morning Assembly')
    all_subjects.add('Lunch')

    print(f'Parsed {len(classes_list)} classes')
    print(f'Parsed {len(flat_entries)} total period slots')
    print(f'Identified {len(all_teachers)} teachers and {len(all_subjects)} subjects')

    # 3. Export JSON
    full_export = {
        'academic_year': '2026-27',
        'title': 'School Time Table (w.e.f - 01/04/2026)',
        'school_timings': school_timings,
        'summary': {
            'total_classes': len(classes_list),
            'total_teachers': len(all_teachers),
            'total_subjects': len(all_subjects),
            'total_scheduled_periods': len(flat_entries)
        },
        'teachers': sorted(list(all_teachers)),
        'subjects': sorted(list(all_subjects)),
        'classes': classes_list,
        'lab_and_special_schedules': lab_entries
    }

    json_path = os.path.join(BASE_DIR, 'timetable.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(full_export, f, indent=2, ensure_ascii=False)
    print(f'Saved: {json_path}')

    # Export Teacher-centric JSON
    teacher_export = {}
    for t_name in sorted(all_teachers):
        t_classes_assigned = set()
        t_subjects_taught = set()
        weekly_periods_count = 0
        sched = teacher_schedule_map.get(t_name, {})
        for day, p_list in sched.items():
            for p in p_list:
                if p['subject'] not in ['Lunch', 'Prayer', 'Lunch _ Class Teacher']:
                    weekly_periods_count += 1
                if p['class_name']:
                    t_classes_assigned.add(p['class_name'])
                if p['subject']:
                    t_subjects_taught.add(p['subject'])

        is_class_teacher_of = [c['class_name'] for c in classes_list if c['class_teacher'] == t_name]

        teacher_export[t_name] = {
            'teacher_name': t_name,
            'is_class_teacher_of': is_class_teacher_of,
            'total_weekly_teaching_periods': weekly_periods_count,
            'classes': sorted(list(t_classes_assigned)),
            'subjects': sorted(list(t_subjects_taught)),
            'weekly_schedule': sched
        }

    teacher_json_path = os.path.join(BASE_DIR, 'timetable_teachers.json')
    with open(teacher_json_path, 'w', encoding='utf-8') as f:
        json.dump(teacher_export, f, indent=2, ensure_ascii=False)
    print(f'Saved: {teacher_json_path}')

    # 4. Export CSV
    csv_path = os.path.join(BASE_DIR, 'timetable_entries.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'entry_id', 'class_name', 'class_teacher', 'day',
            'period_index', 'period_name', 'period_time', 'raw_value', 'subject', 'teacher'
        ])
        writer.writeheader()
        writer.writerows(flat_entries)
    print(f'Saved: {csv_path}')

    # 5. Export SQLite Database
    db_path = os.path.join(BASE_DIR, 'timetable.sqlite')
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute('CREATE TABLE school_timings (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, timings TEXT)')
    for st in school_timings:
        cur.execute('INSERT INTO school_timings (category, timings) VALUES (?, ?)', (st['category'], st['timings']))

    cur.execute('CREATE TABLE classes (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, class_teacher TEXT)')
    for c in classes_list:
        cur.execute('INSERT INTO classes (name, class_teacher) VALUES (?, ?)', (c['class_name'], c['class_teacher']))

    cur.execute('CREATE TABLE teachers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)')
    for t in sorted(all_teachers):
        cur.execute('INSERT INTO teachers (name) VALUES (?)', (t,))

    cur.execute('CREATE TABLE subjects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)')
    for s in sorted(all_subjects):
        cur.execute('INSERT INTO subjects (name) VALUES (?)', (s,))

    cur.execute('''CREATE TABLE schedule_entries (
        id INTEGER PRIMARY KEY,
        class_name TEXT,
        class_teacher TEXT,
        day TEXT,
        period_index INTEGER,
        period_name TEXT,
        period_time TEXT,
        raw_value TEXT,
        subject TEXT,
        teacher TEXT
    )''')
    for item in flat_entries:
        cur.execute('''INSERT INTO schedule_entries 
            (id, class_name, class_teacher, day, period_index, period_name, period_time, raw_value, subject, teacher)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
            item['entry_id'], item['class_name'], item['class_teacher'],
            item['day'], item['period_index'], item['period_name'],
            item['period_time'], item['raw_value'], item['subject'], item['teacher']
        ))

    cur.execute('CREATE INDEX idx_sched_class ON schedule_entries(class_name)')
    cur.execute('CREATE INDEX idx_sched_teacher ON schedule_entries(teacher)')
    cur.execute('CREATE INDEX idx_sched_day ON schedule_entries(day)')
    cur.execute('CREATE INDEX idx_sched_subject ON schedule_entries(subject)')

    conn.commit()
    conn.close()
    print(f'Saved: {db_path}')

if __name__ == '__main__':
    process_timetable()
