#!/usr/bin/env python3
"""
Custom HTTP Server for Timetable Portal & Prerequisites Studio.
Serves static web files and provides REST APIs for:
  - POST /api/save-config : Atomically saves timetable_config.json
  - POST /api/run-audit   : Runs precheck feasibility audit
  - POST /api/run-generate: Runs CSP generator and updates all output files
"""

import os
import sys
import json
import ipaddress
import http.server
import socketserver
import traceback

import urllib.parse
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8080

from engine.models import SchoolConfig, Teacher, ClassSection, Room, Event
from engine.generator import TimetableGenerator
from engine.substitution import SubstitutionManager
from engine.excel_exporter import export_classes_to_excel

# Endpoints that change files on disk. Only this computer may call them; other
# computers on the network can still view pages and use the read-only endpoints.
CHANGE_ENDPOINTS = {
    '/api/save-config',
    '/api/run-generate',
    '/api/purge-faculty',
    '/api/substitutions/save',
}


def is_loopback_host(host):
    """True for localhost or a loopback IP such as 127.0.0.1 or ::1."""
    if not host:
        return False
    if host.lower() == 'localhost':
        return True
    try:
        ip = ipaddress.ip_address(host.strip('[]'))
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback


def is_loopback_origin(origin):
    """True when a browser Origin header names a page served from this computer."""
    if not origin or origin == 'null':
        return False
    return is_loopback_host(urlparse(origin).hostname)


def is_local_change_request(client_ip, origin):
    """
    A change is allowed only when the connection comes from this computer and,
    if a browser sent it, from a page this computer served. The Origin check stops
    other websites open in the admin's browser from making changes.
    """
    if not is_loopback_host(client_ip):
        return False
    return origin is None or is_loopback_origin(origin)


class TimetableRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Only pages served from this computer may read responses cross-origin.
        origin = self.headers.get('Origin')
        if is_loopback_origin(origin):
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def _send_json(self, data, status=200):
        response_bytes = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(response_bytes)))
        self.end_headers()
        self.wfile.write(response_bytes)

    def _read_json_body(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length).decode('utf-8')
        try:
            return json.loads(body)
        except json.JSONDecodeError as e:
            self._send_json({'success': False, 'error': f'Invalid JSON: {str(e)}'}, status=400)
            raise

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/substitutions/history':
            try:
                mgr = SubstitutionManager(BASE_DIR)
                records = mgr.get_history()
                self._send_json({'records': records})
            except Exception as e:
                self._send_json({'records': [], 'error': str(e)}, status=500)
        elif parsed.path == '/api/export-excel':
            try:
                params = parse_qs(parsed.query)
                from_class = params.get('from', [None])[0]
                to_class = params.get('to', [None])[0]
                layout = params.get('layout', ['stacked'])[0]

                master_path = os.path.join(BASE_DIR, 'timetable.json')
                with open(master_path, 'r', encoding='utf-8') as f:
                    master = json.load(f)

                classes = master.get('classes', [])
                academic_year = master.get('academic_year', '2026-27')

                excel_bytes = export_classes_to_excel(classes, from_class, to_class, academic_year, layout=layout)

                fn_from = (from_class or 'All').replace(' ', '_').replace('/', '_')
                fn_to = (to_class or 'All').replace(' ', '_').replace('/', '_')
                filename = f"Timetable_{fn_from}_to_{fn_to}.xlsx"

                self.send_response(200)
                self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.send_header('Content-Length', str(len(excel_bytes)))
                self.end_headers()
                self.wfile.write(excel_bytes)
            except Exception as e:
                traceback.print_exc()
                self._send_json({'success': False, 'error': str(e)}, status=500)
        else:
            # Security: only serve whitelisted static file extensions and block source code directories
            SAFE_EXTENSIONS = {'.html', '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.webp', '.json', '.csv', '.xlsx', '.pdf'}
            FORBIDDEN_DIRS = {'engine', 'tests', '__pycache__'}
            clean_path = parsed.path.strip('/')
            path_parts = clean_path.split('/')
            path_lower = parsed.path.lower()

            is_forbidden = any(part in FORBIDDEN_DIRS or part.startswith('.') for part in path_parts)
            is_safe_ext = path_lower == '/' or path_lower == '' or any(path_lower.endswith(ext) for ext in SAFE_EXTENSIONS)

            if not is_forbidden and is_safe_ext:
                super().do_GET()
            else:
                self.send_error(403, "Forbidden: file or path not allowed")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in CHANGE_ENDPOINTS and not is_local_change_request(
                self.client_address[0], self.headers.get('Origin')):
            print(f"⛔ Blocked {path} from {self.client_address[0]} (origin: {self.headers.get('Origin')})", flush=True)
            self._send_json({
                'success': False,
                'error': 'Changes can only be made on the computer running the server (http://localhost:8080).'
            }, status=403)
            return
        if path == '/api/save-config':
            try:
                data = self._read_json_body()
                config_path = os.path.join(BASE_DIR, 'timetable_config.json')
                
                # Backup existing config if present
                if os.path.exists(config_path):
                    backup_path = config_path + '.bak'
                    try:
                        with open(config_path, 'r', encoding='utf-8') as src, open(backup_path, 'w', encoding='utf-8') as dst:
                            dst.write(src.read())
                    except Exception:
                        pass

                # Detect if any teacher was removed in incoming config
                old_teachers = set()
                if os.path.exists(config_path):
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f_old:
                            old_cfg = json.load(f_old)
                            old_teachers = {t.get('name', '').strip() for t in old_cfg.get('teachers', []) if t.get('name')}
                    except Exception:
                        pass

                new_teachers = {t.get('name', '').strip() for t in data.get('teachers', []) if t.get('name')}
                deleted_teachers = old_teachers - new_teachers
                for del_t in deleted_teachers:
                    try:
                        from purge_faculty import purge_faculty
                        print(f"⚡ Auto-purging deleted faculty: {del_t}", flush=True)
                        purge_faculty(del_t)
                    except Exception as purge_err:
                        print(f"Warning during cascade purge of {del_t}: {purge_err}", flush=True)

                    # The incoming config is written over the purged file below, so
                    # also drop the deleted faculty from its class teacher and event slots.
                    del_lower = del_t.lower()
                    for c in data.get('classes', []):
                        if (c.get('class_teacher') or '').strip().lower() == del_lower:
                            c['class_teacher'] = ''
                    for ev in data.get('events', []):
                        if 'teacher_ids' in ev:
                            ev['teacher_ids'] = [t for t in ev['teacher_ids'] if t.strip().lower() != del_lower]

                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                # Sync school_timings and metadata into timetable.json
                master_path = os.path.join(BASE_DIR, 'timetable.json')
                if os.path.exists(master_path):
                    try:
                        with open(master_path, 'r', encoding='utf-8') as mf:
                            master = json.load(mf)
                        if 'config' in data and 'school_timings' in data['config']:
                            master['school_timings'] = data['config']['school_timings']
                        if 'config' in data and 'academic_year' in data['config']:
                            master['academic_year'] = data['config']['academic_year']
                        if 'config' in data and 'title' in data['config']:
                            master['title'] = data['config']['title']
                        with open(master_path, 'w', encoding='utf-8') as mf:
                            json.dump(master, mf, indent=2, ensure_ascii=False)
                        print("✅ Synced school_timings with timetable.json", flush=True)
                    except Exception as err:
                        print(f"Warning syncing with timetable.json: {err}", flush=True)

                # Sync free_teachers.json with updated blackout slots
                try:
                    from engine.substitution import sync_free_teachers
                    sync_free_teachers(BASE_DIR, config_data=data)
                    print("✅ Synced free_teachers.json with updated blackout slots", flush=True)
                except Exception as sync_err:
                    print(f"Warning syncing free_teachers.json: {sync_err}", flush=True)

                print("✅ Successfully updated timetable_config.json", flush=True)
                self._send_json({
                    'success': True,
                    'message': 'Configuration successfully saved to timetable_config.json'
                })
            except Exception as e:
                traceback.print_exc()
                self._send_json({'success': False, 'error': str(e)}, status=500)

        elif path == '/api/run-audit':
            try:
                data = self._read_json_body()
                if not data:
                    config_path = os.path.join(BASE_DIR, 'timetable_config.json')
                    generator = TimetableGenerator.from_json(config_path)
                else:
                    generator = TimetableGenerator.from_dict(data)
                
                audit = generator.pre_audit()
                self._send_json({
                    'success': True,
                    'report': audit.to_dict()
                })
            except Exception as e:
                traceback.print_exc()
                self._send_json({'success': False, 'error': str(e)}, status=500)

        elif path == '/api/run-generate':
            try:
                config_path = os.path.join(BASE_DIR, 'timetable_config.json')
                data = self._read_json_body()
                if data:
                    with open(config_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)

                generator = TimetableGenerator.from_json(config_path)
                audit = generator.pre_audit()
                if not audit.is_feasible:
                    self._send_json({
                        'success': False,
                        'message': 'Audit failed with fatal errors',
                        'errors': audit.errors,
                        'warnings': audit.warnings
                    }, status=400)
                    return

                result = generator.generate(time_limit=45)
                if result.success and result.grid:
                    exported = generator.export(result.grid, BASE_DIR)
                    self._send_json({
                        'success': True,
                        'message': result.message,
                        'exported': list(exported.keys())
                    })
                else:
                    self._send_json({
                        'success': False,
                        'message': result.message,
                        'conflicts': result.conflict_details
                    }, status=422)
            except Exception as e:
                traceback.print_exc()
                self._send_json({'success': False, 'error': str(e)}, status=500)
        elif path == '/api/substitutions/affected-slots':
            try:
                import importlib, engine.substitution
                importlib.reload(engine.substitution)
                from engine.substitution import SubstitutionManager
                data = self._read_json_body()
                day = data.get("day", "Monday")
                absent = data.get("absent_teachers", [])
                mgr = SubstitutionManager(BASE_DIR)
                slots = mgr.get_affected_slots(day, absent)
                self._send_json({"success": True, "slots": slots, "day": day, "total": len(slots)})
            except Exception as e:
                traceback.print_exc()
                self._send_json({"success": False, "error": str(e)}, status=500)

        elif path == '/api/substitutions/recommend':
            try:
                import importlib, engine.substitution
                importlib.reload(engine.substitution)
                from engine.substitution import SubstitutionManager
                data = self._read_json_body()
                day = data.get("day", "Monday")
                slot = data.get("slot", {})
                absent = data.get("absent_teachers", [])
                assignments = data.get("current_assignments", {})
                max_proxies = int(data.get("max_proxies", 2))
                mgr = SubstitutionManager(BASE_DIR)
                candidates = mgr.rank_candidates_for_slot(slot, day, absent, assignments, max_proxies)
                self._send_json({"success": True, "candidates": candidates, "total": len(candidates)})
            except Exception as e:
                traceback.print_exc()
                self._send_json({"success": False, "error": str(e)}, status=500)

        elif path == '/api/substitutions/auto-assign':
            try:
                import importlib, engine.substitution
                importlib.reload(engine.substitution)
                from engine.substitution import SubstitutionManager
                data = self._read_json_body()
                day = data.get("day", "Monday")
                absent = data.get("absent_teachers", [])
                max_proxies = int(data.get("max_proxies", 2))
                mgr = SubstitutionManager(BASE_DIR)
                result = mgr.auto_assign(day, absent, max_proxies)
                self._send_json(result)
            except Exception as e:
                traceback.print_exc()
                self._send_json({"success": False, "error": str(e)}, status=500)

        elif path == '/api/substitutions/save':
            try:
                data = self._read_json_body()
                mgr = SubstitutionManager(BASE_DIR)
                saved = mgr.save_history(data)
                date_key = data.get('date', 'today')
                print(f"✅ Saved substitution arrangement for {date_key}", flush=True)
                self._send_json({'success': saved, 'message': 'Substitution record saved successfully'})
            except Exception as e:
                traceback.print_exc()
                self._send_json({'success': False, 'error': str(e)}, status=500)

        elif path == '/api/substitutions/report':
            try:
                data = self._read_json_body()
                day = data.get("day", "Monday")
                absent = data.get("absent_teachers", [])
                assignments = data.get("assignments", {})
                date_str = data.get("date", "")
                mgr = SubstitutionManager(BASE_DIR)
                report = mgr.generate_substitution_report(day, absent, assignments, date_str)
                self._send_json({"success": True, "report": report, "total": len(report)})
            except Exception as e:
                traceback.print_exc()
                self._send_json({"success": False, "error": str(e)}, status=500)

        elif path == '/api/substitutions/export-csv':
            try:
                import csv
                import io
                data = self._read_json_body()
                day = data.get("day", "Monday")
                absent = data.get("absent_teachers", [])
                assignments = data.get("assignments", {})
                date_str = data.get("date", "")
                mgr = SubstitutionManager(BASE_DIR)
                report = mgr.generate_substitution_report(day, absent, assignments, date_str)

                output = io.StringIO()
                writer = csv.writer(output)
                # Exact requested columns: Date / Name of the Substitution teacher / Period / Subject / Name of the Teacher who is absent / Signature
                writer.writerow([
                    "Date",
                    "Name of the Substitution teacher",
                    "Period",
                    "Subject",
                    "Name of the Teacher who is absent",
                    "Signature"
                ])
                for r in report:
                    writer.writerow([
                        r.get("date", ""),
                        r.get("substitute_teacher", ""),
                        r.get("period", ""),
                        r.get("subject", ""),
                        r.get("absent_teacher", ""),
                        ""
                    ])

                csv_bytes = output.getvalue().encode('utf-8')
                filename = f"Substitution_Report_{date_str or day}.csv".replace(' ', '_')
                self.send_response(200)
                self.send_header('Content-Type', 'text/csv; charset=utf-8')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.send_header('Content-Length', str(len(csv_bytes)))
                self.end_headers()
                self.wfile.write(csv_bytes)
            except Exception as e:
                traceback.print_exc()
                self._send_json({"success": False, "error": str(e)}, status=500)
        elif self.path == '/api/export-excel':
            try:
                data = self._read_json_body()
                from_class = data.get('from_class')
                to_class = data.get('to_class')
                layout = data.get('layout', 'stacked')

                master_path = os.path.join(BASE_DIR, 'timetable.json')
                with open(master_path, 'r', encoding='utf-8') as f:
                    master = json.load(f)

                classes = master.get('classes', [])
                academic_year = master.get('academic_year', '2026-27')

                excel_bytes = export_classes_to_excel(classes, from_class, to_class, academic_year, layout=layout)

                fn_from = (from_class or 'All').replace(' ', '_').replace('/', '_')
                fn_to = (to_class or 'All').replace(' ', '_').replace('/', '_')
                filename = f"Timetable_{fn_from}_to_{fn_to}.xlsx"

                self.send_response(200)
                self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.send_header('Content-Length', str(len(excel_bytes)))
                self.end_headers()
                self.wfile.write(excel_bytes)
            except Exception as e:
                traceback.print_exc()
                self._send_json({'success': False, 'error': str(e)}, status=500)
        elif path == '/api/purge-faculty':
            try:
                data = self._read_json_body()
                faculty_name = data.get("faculty_name", "").strip()
                if not faculty_name:
                    self._send_json({'success': False, 'error': 'Missing faculty_name'}, status=400)
                    return
                from purge_faculty import purge_faculty
                purge_faculty(faculty_name)
                self._send_json({'success': True, 'message': f'Faculty {faculty_name} successfully purged from all layers.'})
            except Exception as e:
                traceback.print_exc()
                self._send_json({'success': False, 'error': str(e)}, status=500)
        else:
            self.send_error(404, "Endpoint not found")

def run_server(port=PORT):
    os.chdir(BASE_DIR)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), TimetableRequestHandler) as httpd:
        print(f"🚀 Timetable Portal & Studio Server running at http://localhost:{port}/", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    run_server(port)
