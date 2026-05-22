"""
Unit tests for common.db helpers.
"""

from common import db as db_module


class FakeCursor:
    """
    Test double for a MariaDB cursor.
    """

    def __init__(
        self,
        fetchall_result=None,
        fetchone_result=None,
        description=None,
        rowcount=0,
        lastrowid=0,
    ):
        self.fetchall_result = fetchall_result or []
        self.fetchone_result = fetchone_result
        self.description = description or []
        self.rowcount = rowcount
        self.lastrowid = lastrowid
        self.execute_calls = []
        self.closed = False

    def execute(self, sql, params=None):
        """
        Record execute calls for assertions.
        """
        self.execute_calls.append((sql, params))

    def fetchall(self):
        """
        Return the configured list of rows.
        """
        return self.fetchall_result

    def fetchone(self):
        """
        Return the configured single row.
        """
        return self.fetchone_result

    def close(self):
        """
        Mark the cursor as closed.
        """
        self.closed = True


class FakeConnection:
    """
    Test double for a MariaDB connection.
    """

    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.closed = False

    def cursor(self):
        """
        Return the configured cursor.
        """
        return self._cursor

    def commit(self):
        """
        Record commit calls.
        """
        self.commits += 1

    def close(self):
        """
        Mark the connection as closed.
        """
        self.closed = True


def test_db_get_connection_passes_expected_environment_values(monkeypatch):
    """
    Test that db_get_connection forwards environment configuration to mariadb.connect.
    """
    calls = []
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_DB", "national_acts")
    monkeypatch.setenv("DB_USER", "api_user")
    monkeypatch.setenv("DB_PASSWORD", "secret")
    monkeypatch.setattr(
        db_module.mariadb,
        "connect",
        lambda **kwargs: calls.append(kwargs) or "connection",
    )

    connection = db_module.db_get_connection()

    assert connection == "connection"
    assert calls[0] == {
        "user": "api_user",
        "password": "secret",
        "host": "localhost",
        "database": "national_acts",
        "connect_timeout": 3000,
        "port": 3306,
        "autocommit": True,
    }


def test_db_query_all_uses_existing_connection_and_maps_rows():
    """
    Test that db_query_all maps all cursor rows and keeps provided connections open.
    """
    cursor = FakeCursor(
        fetchall_result=[(1, "Ada"), (2, "Grace")],
        description=[("UserId",), ("FirstName",)],
    )
    connection = FakeConnection(cursor)

    rows = db_module.db_query_all("SELECT * FROM Users", {"active": 1}, connection)

    assert rows == [
        {"UserId": 1, "FirstName": "Ada"},
        {"UserId": 2, "FirstName": "Grace"},
    ]
    assert cursor.execute_calls == [("SELECT * FROM Users", {"active": 1})]
    assert cursor.closed is True
    assert connection.closed is False


def test_db_query_all_opens_and_closes_its_own_connection(monkeypatch):
    """
    Test that db_query_all opens and closes a connection when none is provided.
    """
    cursor = FakeCursor(
        fetchall_result=[(1,)],
        description=[("Id",)],
    )
    connection = FakeConnection(cursor)
    monkeypatch.setattr(db_module, "db_get_connection", lambda: connection)

    rows = db_module.db_query_all("SELECT 1")

    assert rows == [{"Id": 1}]
    assert cursor.execute_calls == [("SELECT 1", None)]
    assert connection.closed is True


def test_db_query_one_returns_mapped_row_when_present():
    """
    Test that db_query_one maps the fetched row into a dictionary.
    """
    cursor = FakeCursor(
        fetchone_result=(7, "Admin"),
        description=[("RoleId",), ("RoleName",)],
    )
    connection = FakeConnection(cursor)

    row = db_module.db_query_one("SELECT * FROM Roles", {"id": 7}, connection)

    assert row == {"RoleId": 7, "RoleName": "Admin"}
    assert cursor.execute_calls == [("SELECT * FROM Roles", {"id": 7})]
    assert connection.closed is False


def test_db_query_one_returns_empty_dict_when_no_row_is_found(monkeypatch):
    """
    Test that db_query_one returns an empty dictionary when no row is fetched.
    """
    cursor = FakeCursor(fetchone_result=None, description=[("RoleId",)])
    connection = FakeConnection(cursor)
    monkeypatch.setattr(db_module, "db_get_connection", lambda: connection)

    row = db_module.db_query_one("SELECT * FROM Roles", {"id": 7})

    assert not row
    assert connection.closed is True


def test_convert_cursor_row_to_dictionary_uses_column_order():
    """
    Test that the internal cursor-row converter maps values by description order.
    """
    converter = db_module.__dict__["__convert_cursor_row_to_dictionary"]
    cursor = FakeCursor(description=[("A",), ("B",), ("C",)])

    row = converter((1, 2, 3), cursor)

    assert row == {"A": 1, "B": 2, "C": 3}


def test_db_update_executes_with_parameters_and_commits():
    """
    Test that db_update executes parameterized SQL, commits, and returns True on affected rows.
    """
    cursor = FakeCursor(rowcount=2)
    connection = FakeConnection(cursor)

    success = db_module.db_update("UPDATE Users SET Active=1", {"id": 7}, connection)

    assert success is True
    assert cursor.execute_calls == [("UPDATE Users SET Active=1", {"id": 7})]
    assert connection.commits == 1
    assert cursor.closed is True
    assert connection.closed is False


def test_db_update_executes_without_parameters_and_returns_false(monkeypatch):
    """
    Test that db_update executes SQL without parameters and returns False for zero affected rows.
    """
    cursor = FakeCursor(rowcount=0)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(db_module, "db_get_connection", lambda: connection)

    success = db_module.db_update("UPDATE Users SET Active=1")

    assert success is False
    assert cursor.execute_calls == [("UPDATE Users SET Active=1", None)]
    assert connection.commits == 1
    assert connection.closed is True


def test_db_insert_executes_and_returns_last_row_id():
    """
    Test that db_insert returns the cursor lastrowid after committing.
    """
    cursor = FakeCursor(lastrowid=55)
    connection = FakeConnection(cursor)

    new_id = db_module.db_insert(
        "INSERT INTO Users(Name) VALUES (%(name)s)",
        {"name": "Ada"},
        connection,
    )

    assert new_id == 55
    assert cursor.execute_calls == [
        ("INSERT INTO Users(Name) VALUES (%(name)s)", {"name": "Ada"})
    ]
    assert connection.commits == 1


def test_db_insert_executes_without_parameters(monkeypatch):
    """
    Test that db_insert executes SQL without parameters when none are supplied.
    """
    cursor = FakeCursor(lastrowid=11)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(db_module, "db_get_connection", lambda: connection)

    new_id = db_module.db_insert("INSERT INTO Logs DEFAULT VALUES")

    assert new_id == 11
    assert cursor.execute_calls == [("INSERT INTO Logs DEFAULT VALUES", None)]
    assert connection.closed is True


def test_db_delete_executes_and_returns_true_for_affected_rows():
    """
    Test that db_delete commits and returns True when rows are deleted.
    """
    cursor = FakeCursor(rowcount=1)
    connection = FakeConnection(cursor)

    success = db_module.db_delete(
        "DELETE FROM Users WHERE Id=%(id)s", {"id": 7}, connection
    )

    assert success is True
    assert cursor.execute_calls == [("DELETE FROM Users WHERE Id=%(id)s", {"id": 7})]
    assert connection.commits == 1


def test_db_delete_executes_without_parameters_and_returns_false(monkeypatch):
    """
    Test that db_delete returns False when no rows are deleted.
    """
    cursor = FakeCursor(rowcount=0)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(db_module, "db_get_connection", lambda: connection)

    success = db_module.db_delete("DELETE FROM Logs")

    assert success is False
    assert cursor.execute_calls == [("DELETE FROM Logs", None)]
    assert connection.closed is True


def test_db_convert_list_to_parameters_builds_parameterized_sql_and_mutates_params():
    """
    Test that db_convert_list_to_parameters returns SQL placeholders and fills the param dict.
    """
    params = {}

    sql = db_module.db_convert_list_to_parameters([10, 20, 30], params, "seller")

    assert sql == "(%(seller_0)s, %(seller_1)s, %(seller_2)s)"
    assert params == {"seller_0": 10, "seller_1": 20, "seller_2": 30}


def test_db_convert_list_to_parameters_handles_empty_lists():
    """
    Test that db_convert_list_to_parameters returns empty parentheses for an empty list.
    """
    params = {}

    sql = db_module.db_convert_list_to_parameters([], params, "seller")

    assert sql == "()"
    assert params == {}
