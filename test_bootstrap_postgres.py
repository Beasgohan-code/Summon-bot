import unittest

from bootstrap_postgres import assert_target_compatible


class FakeCursor:
    def __init__(self, tables, user_columns):
        self.tables = tables
        self.user_columns = user_columns
        self.last_query = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query):
        self.last_query = query

    def fetchall(self):
        if "information_schema.tables" in self.last_query:
            return [(name,) for name in self.tables]
        return [(name,) for name in self.user_columns]


class FakeConnection:
    def __init__(self, tables, user_columns=()):
        self.cursor_instance = FakeCursor(tables, user_columns)

    def cursor(self):
        return self.cursor_instance


class BootstrapPreflightTests(unittest.TestCase):
    def test_empty_target_is_allowed(self):
        assert_target_compatible(FakeConnection(()))

    def test_compatible_summon_target_is_allowed(self):
        assert_target_compatible(
            FakeConnection(("users", "characters"), ("user_id", "username", "balance", "banned", "favorite"))
        )

    def test_existing_incompatible_users_table_is_rejected(self):
        with self.assertRaisesRegex(SystemExit, "not a Summon users table"):
            assert_target_compatible(FakeConnection(("users",), ("id", "username", "is_banned")))

    def test_non_empty_target_without_users_is_rejected(self):
        with self.assertRaisesRegex(SystemExit, "without the Summon users table"):
            assert_target_compatible(FakeConnection(("other_application_table",)))


if __name__ == "__main__":
    unittest.main()
