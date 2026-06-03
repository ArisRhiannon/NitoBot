"""Per-(guild, user) activity — message count + distinct active days — goodfaith's
core trust signal (active days is harder to farm than raw count). SQLite, testable."""
import sqlite3
import time


class ActivityStore:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path)
        self.db.executescript(
            "CREATE TABLE IF NOT EXISTS counts(guild TEXT, user TEXT, n INTEGER, PRIMARY KEY(guild,user));"
            "CREATE TABLE IF NOT EXISTS days(guild TEXT, user TEXT, day TEXT, PRIMARY KEY(guild,user,day));")
        self.db.commit()

    def bump(self, guild, user, ts: float = None) -> None:
        g, u = str(guild), str(user)
        day = time.strftime("%Y-%m-%d", time.gmtime(ts if ts is not None else time.time()))
        self.db.execute("INSERT INTO counts(guild,user,n) VALUES(?,?,1) "
                        "ON CONFLICT(guild,user) DO UPDATE SET n=n+1", (g, u))
        self.db.execute("INSERT OR IGNORE INTO days(guild,user,day) VALUES(?,?,?)", (g, u, day))
        self.db.commit()

    def msg_count(self, guild, user) -> int:
        r = self.db.execute("SELECT n FROM counts WHERE guild=? AND user=?", (str(guild), str(user))).fetchone()
        return r[0] if r else 0

    def active_days(self, guild, user) -> int:
        return self.db.execute("SELECT COUNT(*) FROM days WHERE guild=? AND user=?",
                               (str(guild), str(user))).fetchone()[0]
