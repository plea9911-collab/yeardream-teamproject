import sqlite3
import tempfile
import unittest
from pathlib import Path
from tools.backup_webapp import backup_database
from sqlite_repository import SQLiteRepository
from tools.team_check import service, V2


class BackupTests(unittest.TestCase):
    def test_restore_saved_session_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, output = root / 'live.sqlite3', root / 'backup.sqlite3'
            SQLiteRepository(source).initialize_schema()
            original = service(source).start_session(V2)
            counts = backup_database(source, output)
            self.assertEqual(counts['sessions'], 1)
            self.assertEqual(service(output).get_session(original['session_id']), original)
            before = output.read_bytes()
            with self.assertRaises(FileExistsError):
                backup_database(source, output)
            self.assertEqual(output.read_bytes(), before)

    def test_missing_source_does_not_create_empty_database(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'missing.sqlite3'
            with self.assertRaises(ValueError):
                backup_database(source, Path(folder) / 'backup.sqlite3')
            self.assertFalse(source.exists())
