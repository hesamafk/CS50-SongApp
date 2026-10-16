import tempfile
import unittest
from pathlib import Path
import app as module


class SongAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = module.DB_PATH
        module.DB_PATH = str(Path(self.temp.name) / "test.db")
        module.app.config.update(TESTING=True, SECRET_KEY="test-key")
        self.client = module.app.test_client()
        result = module.app.test_cli_runner().invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0, result.output)

    def tearDown(self):
        module.DB_PATH = self.old_path
        self.temp.cleanup()

    def post(self, url, data):
        self.client.get("/")
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        return self.client.post(url, data={**data, "csrf_token": token})

    def login(self):
        self.assertEqual(self.post("/register", data={"username": "tester", "password": " secret "}).status_code, 302)
        self.assertEqual(self.post("/login", data={"username": "tester", "password": " secret "}).status_code, 302)

    def test_song_playback_comments_and_safe_reinitialization(self):
        self.login()
        audio = "https://example.com/audio.mp3"
        self.assertEqual(self.post("/add_song", data={"title": "Track", "file_path": audio}).status_code, 302)
        self.assertIn(audio.encode(), self.client.get("/").data)
        song_id = self.client.get("/api/songs").json[0]["id"]
        self.assertEqual(self.post("/add_comment", data={"song_id": song_id, "comment": "<script>bad()</script>"}).status_code, 302)
        page = self.client.get("/").data
        self.assertIn(b"&lt;script&gt;", page)
        self.assertNotIn(b"<script>bad()", page)
        result = module.app.test_cli_runner().invoke(args=["init-db"])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(len(self.client.get("/api/songs").json), 1)
        self.assertEqual(len(self.client.get("/api/songs").json[0]["comments"]), 1)

    def test_missing_password_duplicate_user_and_invalid_song(self):
        self.login()
        self.assertEqual(self.post("/login", data={"username": "tester"}).status_code, 400)
        self.assertEqual(self.post("/register", data={"username": "tester", "password": "other"}).status_code, 400)
        self.assertEqual(self.post("/add_comment", data={"song_id": 99999, "comment": "orphan"}).status_code, 404)
        self.assertEqual(self.post("/add_song", data={"title": "invalid", "file_path": "javascript:alert(1)"}).status_code, 400)

    def test_anonymous_write_is_denied(self):
        self.assertEqual(self.post("/add_song", data={"title": "test", "file_path": "https://example.com/a.mp3"}).status_code, 403)
        self.assertEqual(self.post("/add_comment", data={"song_id": 1, "comment": "test"}).status_code, 403)

    def test_csrf_and_logout(self):
        self.login()
        self.assertEqual(self.client.post("/add_song", data={"title": "Track"}).status_code, 400)
        self.assertEqual(self.client.get("/logout").status_code, 405)
        self.assertEqual(self.post("/logout", {}).status_code, 302)
        self.assertEqual(self.post("/add_comment", {"song_id": 1, "comment": "test"}).status_code, 403)
