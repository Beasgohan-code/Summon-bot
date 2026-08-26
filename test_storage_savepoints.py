import unittest

from storage import PostgresCursor


class FakeRawCursor:
    def __init__(self, fail_on=None):
        self.fail_on = fail_on
        self.commands = []
        self.description = None

    def execute(self, query, _params=()):
        self.commands.append(query)
        if query == self.fail_on:
            raise RuntimeError("expected statement failure")
        self.description = [("count",)] if query == "SELECT 1" else None

    def executemany(self, query, _params):
        self.execute(query)

    def fetchone(self):
        return (1,)

    def fetchall(self):
        return [(1,)]

    def close(self):
        return None


class FakeRawConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.rollback_calls = 0

    def cursor(self):
        return self.cursor_instance

    def rollback(self):
        self.rollback_calls += 1


class FakeConnection:
    def __init__(self, raw_connection):
        self._connection = raw_connection


class StorageSavepointTests(unittest.TestCase):
    def test_successful_select_remains_fetchable(self):
        raw_cursor = FakeRawCursor()
        cursor = PostgresCursor(FakeConnection(FakeRawConnection(raw_cursor)))

        cursor.execute("SELECT 1")

        self.assertEqual(cursor.fetchone()[0], 1)
        self.assertEqual(raw_cursor.commands, ["SAVEPOINT summon_statement", "SELECT 1"])

    def test_failed_statement_rolls_back_only_to_savepoint(self):
        raw_cursor = FakeRawCursor(fail_on="BROKEN")
        raw_connection = FakeRawConnection(raw_cursor)
        cursor = PostgresCursor(FakeConnection(raw_connection))

        with self.assertRaisesRegex(RuntimeError, "expected statement failure"):
            cursor.execute("BROKEN")

        self.assertEqual(raw_connection.rollback_calls, 0)
        self.assertEqual(
            raw_cursor.commands,
            ["SAVEPOINT summon_statement", "BROKEN", "ROLLBACK TO SAVEPOINT summon_statement", "RELEASE SAVEPOINT summon_statement"],
        )


if __name__ == "__main__":
    unittest.main()
