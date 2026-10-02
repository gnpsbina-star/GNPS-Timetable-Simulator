# GNPS Timetable Simulator (2026-27)
**Gomti Nandan Public School**

[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![Tests Passing](https://img.shields.io/badge/Tests-105%20Passed-success?style=flat&logo=pytest)](tests/)
[![Deployment](https://img.shields.io/badge/Deployment-Vercel%20%2B%20GitHub-black?style=flat&logo=vercel)](https://vercel.com)
[![Platform](https://img.shields.io/badge/Architecture-Vanilla%20JS%20%7C%20Tailwind%20%7C%20SQLite-indigo)](https://tailwindcss.com)

A high-performance, zero-external-build timetable scheduling, constraint-satisfaction solver, and daily substitution management platform built specifically for the academic operations of **Gomti Nandan Public School** for the 2026-27 academic session.

---

## 🌟 Key Modules & Core Features

### 1. 📅 Master Timetable Portal (`index.html`)
- **Multi-View Modes**: Switch instantly between Class Timetables, Individual Teacher Schedules, and Consolidated Wing views.
- **Academic Wing Filtering**: Grouped into Primary (Classes 1–5), Middle (Classes 6–8), Secondary (Classes 9–10), and Senior Secondary (Classes 11–12).
- **Single-Line Matrix Badges**: Normalized subject-teacher badges with color-coded categories (Theory, Practical Labs, Activities/Sports, Languages).
- **Weekly Load & Subject Distribution**: Class-level breakdown of weekly lesson quotas and faculty teaching hours.
- **Print & Export**: Print-ready A4 landscape styling with zero text truncation; 1-click export to multi-sheet Excel workbooks and raw CSV.

### 2. 🔄 Daily Substitution & Proxy Studio (`substitution.html`)
- **Intelligent Substitute Ranking**: Algorithmic scoring evaluating teacher availability, subject alignment, current daily workload, and wing familiarity.
- **Master Proxy Register**: Automatically generates a formal Daily Substitution & Proxy Register.
- **Optimized Multi-Page Print Layout**: Fixed table pagination with repeating `thead`, atomic row break protection, and signature block fitting cleanly across pages.
- **Session History & Auditing**: Tracks all recorded leaves, assigned proxies, and room relocations with localStorage persistence and server-side backup.

### 3. 👥 Faculty Availability Matrix (`free_teachers.html`)
- Period-by-period matrix of free faculty across all 6 working days (Monday–Saturday).
- Real-time filtering by subject specialization, wing, and period index.
- Respects custom user blackout slots and assigned non-teaching periods.

### 4. ⚙️ Prerequisites & Master Catalog (`prerequisites.html`)
- **Master School Timings**: Configurable period bells, morning assemblies, lunch breaks, and prayer sessions.
- **Faculty Quota Manager**: Weekly teaching limits, max daily periods, and Class Teacher assignments.
- **Subject & Room Constraints**: Dedicated lab requirements (Physics, Chemistry, Biology, Computer Labs), sports ground rules, and activity hall allocations.
- **Cascade Deletion Engine**: Removing a faculty member automatically purges references across all configurations, database tables, and operational rosters.

### 5. 🧩 CSP Solver Engine (`engine/`, via `POST /api/run-generate`)
- **Automated Scheduling Engine**: Powered by Constraint Satisfaction Problem (CSP) algorithms enforcing hard constraints (0 teacher clashes, 0 room conflicts, max 1 double lab/day) and soft preferences.
- **Feasibility Precheck**: Audits room quotas, teacher hours, and section requirements before generation.
- **Class Teacher Period 1 Rule**: Ensures Class Teachers are prioritized for Period 1 with their designated class.

### 6. 🔐 User Authentication & Roles (`login.html`, `auth.js`, `nav.js`)
- **Google Workspace OAuth 2.0**: Official Google Identity Services (GSI) SDK sign-in with JWT token decoding.
- **Customizable Google Client ID**: In-browser configuration drawer allowing easy pairing with your school's Google Cloud project.
- **Instant Demo Logins**: 1-click test roles for Administrator (`admin@gnps.ac.in`) and Faculty (`jyotsharan@gnps.ac.in`) for offline/local workflows.
- **Unified Navigation Bar**: User avatar, role badges, and universal logout synced across all pages.

---

## 🏗️ System Architecture & Data Flow

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

---

## 💻 Tech Stack

- **Frontend**: Vanilla JavaScript (ES6+), HTML5, Tailwind CSS (via CDN), Google Identity Services (GSI) SDK.
- **Backend / Server**: Python 3 standard library (`http.server`, `socketserver`, `sqlite3`, `json`, `csv`). No external framework dependencies required.
- **Database**: SQLite3 (`timetable.sqlite`).
- **Scheduling Engine**: Custom Python CSP / Constraint Satisfaction Engine (`engine/`).
- **Cloud Hosting & CI/CD**: Vercel (Frontend static assets) + GitHub (`gnpsbina-star/GNPS-Timetable-Simulator`).

---

## 🚀 Quick Start (Local Setup)

### 1. Prerequisites
- Python 3.9 or higher.
- A modern web browser (Google Chrome, Edge, Safari, Firefox).

### 2. Start the Local Server
From the project root directory, run:
```bash
python3 server.py
```

The server will start on:
👉 **`http://localhost:8080`** (or `http://127.0.0.1:8080`)

### 3. Open in Browser
| Page | URL | Description |
| :--- | :--- | :--- |
| **Login / Sign In** | `http://localhost:8080/login.html` | Google Sign-In & Demo role access |
| **Master Timetable** | `http://localhost:8080/index.html` | Class & Teacher timetable viewer |
| **Substitution Studio** | `http://localhost:8080/substitution.html` | Proxy assignment & register printing |
| **Free Teachers** | `http://localhost:8080/free_teachers.html` | Teacher vacancy matrix |
| **Prerequisites** | `http://localhost:8080/prerequisites.html` | Rules, periods, and catalog setup |

---

## 🌐 Online Deployment (Vercel & GitHub)

- **Repository**: [github.com/gnpsbina-star/GNPS-Timetable-Simulator](https://github.com/gnpsbina-star/GNPS-Timetable-Simulator)
- **Live Deployment**: Connected to **Vercel** for automated continuous deployment.

### 1-Click Online Sync Script
To verify timetable validity and push updates to the live site:
```bash
./update_online.sh
```
This script automatically:
1. Runs `import_timetable.py` and `generate_timetable.py --verify` to guarantee 0 teacher/room clashes.
2. Commits and pushes changes to the GitHub repository.
3. Triggers immediate deployment on Vercel.

---

## 🛠️ CLI Utilities & Maintenance Scripts

| Script | Command | Purpose |
| :--- | :--- | :--- |
| **Cascade Faculty Purge** | `python3 purge_faculty.py "<Faculty Name>"` | Completely unassigns and deletes a faculty member across all JSONs, database tables, and rosters. |
| **Master Data Sync** | `python3 sync_master_data.py` | Synchronizes SQLite entries and config into compiled JSON rosters and CSV exports. |
| **Clash Verifier** | `python3 generate_timetable.py --verify` | Audits the current master timetable for any duplicate teacher assignments or room over-allocations. |
| **Excel Exporter** | `python3 -c "import sync_master_data"` | Refreshes `timetable_entries.csv` and class matrices. |

---

## 📡 REST API Reference (`server.py`)

When running `server.py`, the following REST endpoints are available:

- `POST /api/save-config`: Atomically writes updated configuration to `timetable_config.json`, detects deleted faculty, and triggers auto-purge.
- `POST /api/purge-faculty`: Accepts `{"faculty_name": "Name"}` and executes a multi-layer cascade unassignment across databases and outputs.
- `POST /api/run-audit`: Runs a feasibility check on current rules and quotas without modifying the live schedule.
- `POST /api/run-generate`: Executes the CSP solver to build a fresh timetable and updates `timetable.sqlite` and JSON files.
- `GET /api/export-excel`: Generates and serves a formatted Excel workbook with separate sheets for each class.

---

## 🧪 Testing & Quality Assurance

The codebase includes an extensive automated test suite covering CSP constraints, data integrity, substitutions, and bug regression:

```bash
python3 -m unittest discover -s tests
```

**Status**: 105 tests passing (0 failures, 0 errors).

---

## 📁 Repository Directory Structure

```
├── README.md                           # This documentation
├── server.py                           # Python HTTP server & REST API
├── index.html                          # Master Timetable portal
├── substitution.html                   # Daily substitution & proxy register
├── free_teachers.html                  # Availability matrix
├── prerequisites.html                  # Rules, periods & teachers setup
├── login.html                          # Google Sign-In & authentication
├── auth.js                             # Client-side session and auth manager
├── nav.js                              # Shared responsive navigation header
├── purge_faculty.py                    # Multi-layer cascade faculty deletion tool
├── sync_master_data.py                 # SQLite-to-JSON data synchronizer
├── generate_timetable.py               # CSP timetable generator CLI
├── import_timetable.py                 # Initial data ingestion utility
├── update_online.sh                    # 1-click sync and Vercel publisher
├── timetable_config.json               # Master school configuration file
├── timetable.sqlite                    # Master SQLite schedule database
├── timetable.json                      # Compiled class timetable export
├── timetable_teachers.json             # Compiled teacher schedule export
├── free_teachers.json                  # Compiled free periods roster
├── timetable_rooms.json                # Room reservation and allocation registry
├── timetable_entries.csv               # Flat CSV timetable records
├── engine/                             # Core Python engine
│   ├── models.py                       # Data models & schemas
│   ├── generator.py                    # CSP scheduling logic
│   ├── substitution.py                 # Proxy ranking algorithm
│   └── excel_exporter.py               # Excel formatting utility
├── tests/                              # Unit & integration test suite (105 tests)
└── archive/                            # Retired one-off migration scripts and HTML prototypes
```

---

## 🏫 Attribution & License

Designed and maintained for **Gomti Nandan Public School (2026-27)**.  
All school schedules, period layouts, and faculty structures are configured according to GNPS institutional guidelines.
