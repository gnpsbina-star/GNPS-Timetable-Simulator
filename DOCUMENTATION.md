# GNPS Timetable Simulator (2026-27)
## Comprehensive Technical Architecture & Operational Guide
**Institution**: Gomti Nandan Public School  
**Academic Session**: 2026–2027  
**Version**: 2.4.0 (Production Release)  
**Repository**: `github.com/gnpsbina-star/GNPS-Timetable-Simulator` (Branch: `main`)  

---

## 1. Executive Summary & Institutional Context

Managing the academic operations of a multi-wing K-12 institution like **Gomti Nandan Public School** involves complex combinatorial and operational challenges:
1. **Curricular Constraints**: Managing distinct requirements across Primary (Classes 1–5), Middle (Classes 6–8), Secondary (Classes 9–10), and Senior Secondary (Classes 11–12), including double-period laboratory practicals, joint elective baskets, language electives, and physical education grounds.
2. **Faculty Quotas & Well-being**: Ensuring 49+ faculty members have balanced weekly lesson counts (typically 30–34 periods max), preventing cognitive burnout by capping daily teaching loads at 5–6 periods, and guaranteeing non-teaching preparation periods.
3. **Daily Substitution Volatility**: When teachers take leave, the school must rapidly reallocate unassigned periods to qualified, available colleagues without violating faculty load maximums or creating room conflicts, followed by generating official physical proxy registers for the morning assembly.
4. **Data Integrity & Synchronization**: Historical timetable systems often suffer from "ghost records"—where deleting a teacher or reassigning a class leaves orphaned references across printed schedules, daily rosters, and databases.

To address these challenges, this system was developed as a unified, zero-dependency academic operating system combining **automated Constraint Satisfaction Problem (CSP) generation**, **real-time substitution dispatch**, **dynamic multi-view dashboards**, and **multi-page print engines**.

---

## 2. System Architecture & Design Philosophy

```
                      ┌────────────────────────────┐
                      │   timetable_config.json    │
                      │  (Master Rules & Catalogs) │
                      └─────────────┬──────────────┘
                                    │
                  ┌─────────────────┴─────────────────┐
                  ▼                                   ▼
      ┌───────────────────────┐           ┌───────────────────────┐
      │   timetable.sqlite    │           │      engine/          │
      │  (Relational Database)│◄──────────┤   - generator.py      │
      └───────────┬───────────┘           │   - substitution.py   │
                  │                       │   - models.py         │
                  ▼                       └───────────────────────┘
      ┌───────────────────────┐
      │   sync_master_data.py │
      └───────────┬───────────┘
                  │
  ┌───────────────┼───────────────────────────────┐
  ▼               ▼                               ▼
timetable.json  timetable_teachers.json  free_teachers.json
  │               │                               │
  └───────────────┼───────────────────────────────┘
                  ▼
      ┌───────────────────────┐
      │ Frontend Web Studio   │
      │ - index.html          │
      │ - substitution.html   │
      │ - free_teachers.html  │
      │ - prerequisites.html  │
      │ - login.html          │
      └───────────────────────┘
```

### 2.1 The Zero-External-Dependency Philosophy
A key architectural principle of this system is that **it requires no external pip packages and no npm build steps**. 
- The backend relies exclusively on Python's built-in libraries: `http.server`, `socketserver`, `sqlite3`, `json`, `csv`, `re`, and `urllib`.
- The frontend uses pure modern standard ES6+ JavaScript, native browser APIs (`fetch`, `localStorage`, `DOMParser`), and Tailwind CSS served via CDN.
- **Why this matters**: Educational software often becomes unmaintainable over 3–5 years due to broken npm dependencies, conflicting virtual environments, or deprecated build tooling. This system will execute reliably on any machine with standard Python 3.9+ without running `pip install` or `npm install`.

### 2.2 Dual-Tier Operational Topology
1. **Local Administrative Node (`http://localhost:8080`)**:
   - Runs on the administrator's Mac via `python3 server.py`.
   - Has full write access to the filesystem, executes the CSP solver, performs SQLite mutations, triggers cascade faculty purges, and rebuilds JSON caches.
2. **Cloud Public/Faculty Mirror (`https://gnpstimetablesimulator.vercel.app`)**:
   - Hosted on Vercel and connected to GitHub repository `gnpsbina-star/GNPS-Timetable-Simulator`.
   - Serves static pre-compiled JSONs and HTML pages to teachers, students, and parents with CDN performance and 99.99% availability.
   - Pushing updates takes one click via `./update_online.sh`.

---

## 3. Deep Dive: Key Modules & Workflows

### 3.1 Module 1: Master Timetable Portal (`index.html`)

- **Class Timetables Mode**: Renders the complete weekly schedule (Monday through Saturday, Periods 0 to 8) for any selected class.
- **Faculty Timetables Mode**: Provides personalized schedules for each of the 49 faculty members, displaying their teaching commitments, designated rooms, and free periods.
- **Wing Consolidated View**: Allows administrators to view all classes within a specific educational wing simultaneously on a single unified grid.

#### Academic Wing Grouping
| Wing Identifier | Covered Grades | Bell Schedule Characteristics |
| :--- | :--- | :--- |
| **Primary Wing** | Classes 1 to 5 (Rose, Lotus, Sunflower sections) | Foundational periods, earlier lunch, activity emphasis |
| **Middle Wing** | Classes 6 to 8 | 8 academic periods + assembly |
| **Secondary Wing** | Classes 9 to 10 | Subject specialization, board preparation |
| **Senior Secondary Wing** | Classes 11 to 12 (Science & Commerce streams) | Double lab blocks, joint electives, 60-min senior lunch |

#### Single-Line Matrix Badging
To eliminate clutter, subject and teacher information is rendered using normalized compact badges:
- **Theory Subjects** (e.g. `Maths_Vandna Saraf`, `Eng_Jyotsharan`): Crisp indigo/slate pills.
- **Practical Science Labs** (e.g. `Phy Lab_Deepmali`, `Chem Lab_Atul`): Emerald-tinted badges indicating Science Lab room requirements.
- **Activities & Physical Education** (e.g. `PE_Geetesh`, `Games_Shailandra`): Amber-tinted badges signifying Sports Ground or Activity Hall usage.

#### Print Layout Engine
The print stylesheet (`@media print`) enforces A4 landscape optimization:
- Auto-scales table column widths so no text is clipped.
- Removes UI chrome, search bars, and navigation headers.
- Displays official school header, academic year, and principal signature lines.

---

### 3.2 Module 2: Daily Substitution & Proxy Studio (`substitution.html`)

When faculty members are absent, `substitution.html` automates the allocation of substitute teachers.

#### Multi-Factor Substitute Scoring Algorithm
When recommending substitute teachers, the engine applies weighted heuristic scoring:
1. **Absolute Availability**: Hard gate. Teacher must have zero assigned teaching lessons in that specific period and not be marked absent or blacked out.
2. **Subject Qualification Match**: $+40$ points if the substitute teaches the same or related subject discipline.
3. **Wing Familiarity**: $+25$ points if the substitute already teaches that class or other classes in the same wing.
4. **Daily Load Balancing**: Inversely proportional to the number of lessons the teacher has already taught that day. Prevents overburdening a teacher who already has 5 or 6 periods.

#### Multi-Page Print Layout Optimization
- Configured natural page division: `table { page-break-inside: auto !important; break-inside: auto !important; }`.
- Repeating headers on every printed page: `thead { display: table-header-group !important; }`.
- Row-level break protection: `tbody tr { page-break-inside: avoid !important; }`.
- Compact signature block (`.print-signatures`) with `break-inside: avoid !important; margin-top: 14px;`, allowing all 32 periods plus signatures to fit cleanly across exactly 2 pages.

---

### 3.3 Module 3: Faculty Availability Matrix (`free_teachers.html`)

- **Interactive Period Filters**: Filter available teachers by specific day and period (e.g., "Who is free on Tuesday Period 3?").
- **Subject Specialization Badges**: Instantly shows whether an available teacher is qualified in Science, Mathematics, Languages, Humanities, or Physical Education.
- **Custom User Blackout Registry**: Allows administrators to mark specific teachers as unavailable for substitutions during administrative duty periods, exam evaluations, or meetings (`localStorage.getItem('gnps_blackout_slots')`).

---

### 3.4 Module 4: Prerequisites & Quota Studio (`prerequisites.html`)

- **Master School Timings**: Edit start times, end times, and duration of all 9 daily slots (Assembly, Periods 1–8, and Lunch).
- **Faculty Quota Manager**: Set weekly period quotas (e.g., maximum 34 periods) and designate Class Teachers for each section.
- **Room Allocation Rules**: Link practical lab subjects to specialized physical rooms (Science Lab, Computer Lab, Activity Hall, Sports Ground).

#### The Cascade Deletion Engine (`purge_faculty.py`)
1. **`timetable_config.json`**: Removes faculty from teachers list, clears `classes.class_teacher`, removes faculty ID from all `events.teacher_ids`.
2. **`timetable.sqlite`**: Deletes from `teachers` table, clears `schedule_entries.class_teacher`, cleans `schedule_entries.teacher`.
3. **Legacy `timetable.db`**: Cleans `timetable_entries.teacher` and `timetable_entries.raw_value`.
4. **Data Synchronization**: Automatically rebuilds `timetable.json`, `timetable_teachers.json`, `free_teachers.json`, and `timetable_entries.csv`.
5. **Client Browser**: Immediately syncs `localStorage('gnps_timetable_config')`.

---

### 3.5 Module 5: CSP Solver Engine (`engine/`)

The Python Constraint Satisfaction Problem (CSP) scheduling engine in `engine/generator.py`, run through `POST /api/run-generate`.
- **Hard Constraints**: 0 faculty clashes, 0 room clashes, weekly teacher quotas, daily load limits, double-period lab continuity.
- **Soft Constraints**: Prioritizes Class Teachers for Period 1 with their designated class.
- **Feasibility Audit**: Pre-checks room capacities, teacher hours, and section quotas before running the solver.

---

### 3.6 Module 6: Authentication & Navigation (`login.html`, `auth.js`, `nav.js`)

- **Google Workspace OAuth 2.0**: Official Google Identity Services (GSI) SDK integration with JWT credential decoding.
- **Customizable Google Client ID**: In-browser configuration drawer allowing easy pairing with your school's Google Cloud project.
- **Instant Demo Logins**: 1-click test roles for Administrator (`admin@gnps.ac.in`) and Faculty (`jyotsharan@gnps.ac.in`) for offline/local workflows.
- **Unified Navigation Bar**: User avatar, role badges, and universal logout synced across all pages.

---

## 4. Standard Operating Procedures (SOPs)

### SOP 1: Daily Morning Substitution Routine (7:40 AM – 7:55 AM)
1. Open `http://localhost:8080/substitution.html`.
2. Under **Absent Faculty Selection**, check off teachers on leave today.
3. Review the automatically generated substitution suggestions.
4. If necessary, use the dropdown to reassign any period to a different available teacher.
5. Click **"Print Substitution Register"** (prints a 2-page document with repeating headers and signature block).
6. Click **"Save Substitution Record"** to archive the session.

### SOP 2: Deleting or Replacing a Faculty Member
1. Open `http://localhost:8080/prerequisites.html`.
2. Navigate to **Faculty Directory & Quotas**.
3. Locate the departing faculty member and click **"Delete"**.
4. Confirm the prompt to trigger automatic cascade purge across all files and databases.
5. Or run via terminal: `python3 purge_faculty.py "Faculty Name"`.

### SOP 3: Publishing Live Updates to the Cloud
1. In the terminal, execute:
   ```bash
   ./update_online.sh
   ```
2. The script runs clash verification (`generate_timetable.py --verify`).
3. If 0 clashes are found, it commits all files to Git and pushes to `main`.
4. Vercel automatically deploys the update to `https://gnpstimetablesimulator.vercel.app`.

---

## 5. Automated Testing & Verification Framework

Run the automated test suite:
```bash
python3 -m unittest discover -s tests
```
**Status**: 105 tests passing, 0 failures, 0 errors.

---

## 6. Institutional Summary

| Metric | Current Operational Value |
| :--- | :--- |
| **Total Registered Faculty** | 49 active teachers |
| **Total Class Sections** | Classes 1 to 12 (Primary, Middle, Secondary, Senior Secondary) |
| **Periods per Day** | 9 slots (Assembly + 8 Teaching/Activity periods + Lunch) |
| **Working Days** | 6 days (Monday through Saturday) |
| **Hard Timetable Clashes** | **0** (Mathematically verified) |
| **External pip / npm dependencies** | **0** (Pure Python 3 standard library + CDN CSS) |
| **Primary Code Repository** | `github.com/gnpsbina-star/GNPS-Timetable-Simulator` |
| **Live Web URL** | `https://gnpstimetablesimulator.vercel.app` |
| **Local Web URL** | `http://localhost:8080` |
