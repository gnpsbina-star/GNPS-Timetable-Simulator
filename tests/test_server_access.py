"""
Tests that only the computer running server.py can call the endpoints that
change files, and that other websites cannot read server responses.
"""

import os
import sys
import json
import shutil
import tempfile
import functools
import threading
import unittest
import urllib.request
import urllib.error
import socketserver

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import server
from server import is_loopback_host, is_loopback_origin, is_local_request, is_private_file


class TestLocalChangeRules(unittest.TestCase):
    def test_loopback_hosts(self):
        for host in ['127.0.0.1', '127.0.0.5', '::1', '[::1]', 'localhost', '::ffff:127.0.0.1']:
            self.assertTrue(is_loopback_host(host), host)
        for host in ['192.168.1.20', '10.0.0.4', '0.0.0.0', 'example.com', '', None]:
            self.assertFalse(is_loopback_host(host), host)

    def test_loopback_origins(self):
        for origin in ['http://localhost:8080', 'http://127.0.0.1:8080', 'http://[::1]:8080']:
            self.assertTrue(is_loopback_origin(origin), origin)
        for origin in ['https://evil.example', 'http://192.168.1.20:8080', 'null', '', None,
                       'http://localhost.evil.example']:
            self.assertFalse(is_loopback_origin(origin), origin)

    def test_change_request_rules(self):
        # This computer, no browser Origin (e.g. a script or curl)
        self.assertTrue(is_local_request('127.0.0.1', None))
        # This computer, page served by this computer
        self.assertTrue(is_local_request('127.0.0.1', 'http://localhost:8080'))
        # Another computer on the network
        self.assertFalse(is_local_request('192.168.1.20', None))
        self.assertFalse(is_local_request('192.168.1.20', 'http://192.168.1.5:8080'))
        # Another website open in the admin's browser on this computer
        self.assertFalse(is_local_request('127.0.0.1', 'https://evil.example'))
        self.assertFalse(is_local_request('127.0.0.1', 'null'))

    def test_private_files(self):
        for path in ['/substitutions_history.json', '/SUBSTITUTIONS_HISTORY.JSON',
                     '/%73ubstitutions_history.json', '/./substitutions_history.json',
                     '/x/../substitutions_history.json', '/substitutions_history.json.tmp']:
            self.assertTrue(is_private_file(path), path)
        for path in ['/timetable.json', '/free_teachers.json', '/', '/substitution.html']:
            self.assertFalse(is_private_file(path), path)


class TestServerAccess(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Point the API at an empty temp folder so a broken guard can never touch real data
        cls.real_base_dir = server.BASE_DIR
        cls.tmp_dir = tempfile.mkdtemp()
        server.BASE_DIR = cls.tmp_dir
        handler = functools.partial(server.TimetableRequestHandler, directory=BASE_DIR)
        socketserver.TCPServer.allow_reuse_address = True
        cls.httpd = socketserver.TCPServer(('127.0.0.1', 0), handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server.BASE_DIR = cls.real_base_dir
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def _request(self, path, body=None, origin=None):
        req = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}', method='POST' if body is not None else 'GET')
        if body is not None:
            req.data = json.dumps(body).encode('utf-8')
            req.add_header('Content-Type', 'application/json')
        if origin:
            req.add_header('Origin', origin)
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_change_from_other_website_is_blocked(self):
        # An empty faculty name would get a 400 if the request reached the handler
        status, _, body = self._request('/api/purge-faculty', {'faculty_name': ''}, origin='https://evil.example')
        self.assertEqual(status, 403)
        self.assertFalse(json.loads(body)['success'])

    def test_change_from_this_computer_reaches_handler(self):
        status, _, _ = self._request('/api/purge-faculty', {'faculty_name': ''})
        self.assertEqual(status, 400)
        status, _, _ = self._request('/api/purge-faculty', {'faculty_name': ''}, origin=f'http://localhost:{self.port}')
        self.assertEqual(status, 400)

    def test_all_change_endpoints_are_guarded(self):
        for path in server.CHANGE_ENDPOINTS:
            status, _, _ = self._request(path, {}, origin='https://evil.example')
            self.assertEqual(status, 403, path)

    def test_history_file_is_never_served(self):
        for path in ['/substitutions_history.json', '/SUBSTITUTIONS_HISTORY.JSON', '/%73ubstitutions_history.json']:
            status, _, _ = self._request(path)
            self.assertEqual(status, 403, path)

    def test_history_endpoint_only_for_this_computer(self):
        status, _, body = self._request('/api/substitutions/history')
        self.assertEqual(status, 200)
        self.assertIn('records', json.loads(body))
        status, _, _ = self._request('/api/substitutions/history', origin='https://evil.example')
        self.assertEqual(status, 403)

    def test_other_websites_cannot_read_responses(self):
        _, headers, _ = self._request('/index.html', origin='https://evil.example')
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        origin = f'http://localhost:{self.port}'
        _, headers, _ = self._request('/index.html', origin=origin)
        self.assertEqual(headers.get('Access-Control-Allow-Origin'), origin)


if __name__ == '__main__':
    unittest.main()
