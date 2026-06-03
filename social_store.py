"""Counters for social actions (hug/pat/kiss/...). SQLite-backed, Discord-free, testable."""
import sqlite3


class SocialStore:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS acts("
            "action TEXT, actor TEXT, target TEXT, n INTEGER, "
            "PRIMARY KEY(action, actor, target))")
        self.db.commit()

    def record(self, action: str, actor, target) -> int:
        """Record one `action` from actor to target; return the new actor→target count."""
        self.db.execute(
            "INSERT INTO acts(action, actor, target, n) VALUES(?,?,?,1) "
            "ON CONFLICT(action, actor, target) DO UPDATE SET n = n + 1",
            (action, str(actor), str(target)))
        self.db.commit()
        return self.pair_count(action, actor, target)

    def pair_count(self, action: str, actor, target) -> int:
        row = self.db.execute(
            "SELECT n FROM acts WHERE action=? AND actor=? AND target=?",
            (action, str(actor), str(target))).fetchone()
        return row[0] if row else 0

    def received(self, user, action: str = None) -> int:
        if action:
            q, args = "SELECT COALESCE(SUM(n),0) FROM acts WHERE target=? AND action=?", (str(user), action)
        else:
            q, args = "SELECT COALESCE(SUM(n),0) FROM acts WHERE target=?", (str(user),)
        return self.db.execute(q, args).fetchone()[0]

    def given(self, user, action: str = None) -> int:
        if action:
            q, args = "SELECT COALESCE(SUM(n),0) FROM acts WHERE actor=? AND action=?", (str(user), action)
        else:
            q, args = "SELECT COALESCE(SUM(n),0) FROM acts WHERE actor=?", (str(user),)
        return self.db.execute(q, args).fetchone()[0]
