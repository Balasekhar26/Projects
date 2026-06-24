import sqlite3
import time
import uuid

conn = sqlite3.connect(":memory:")
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA foreign_keys = ON")

# Create tables
conn.executescript("""
CREATE TABLE IF NOT EXISTS relationship_entities (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    trust_level TEXT NOT NULL,
    dunbar_layer INTEGER NOT NULL DEFAULT 1,
    pinned INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS relationship_goals (
    goal_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES relationship_entities(entity_id) ON DELETE CASCADE,
    goal_title TEXT NOT NULL,
    goal_description TEXT NOT NULL,
    status TEXT DEFAULT 'ACTIVE',
    priority_weight REAL NOT NULL,
    confidence_score REAL NOT NULL,
    confidence_state TEXT NOT NULL DEFAULT 'INFERRED',
    approved INTEGER DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

DROP VIEW IF EXISTS hm_user_goals;
CREATE VIEW hm_user_goals AS
SELECT goal_id AS id, entity_id, goal_description AS goal, status, priority_weight AS priority, approved, created_at, updated_at
FROM relationship_goals;

DROP TRIGGER IF EXISTS trg_hm_user_goals_insert;
CREATE TRIGGER trg_hm_user_goals_insert INSTEAD OF INSERT ON hm_user_goals BEGIN
    INSERT INTO relationship_goals (goal_id, entity_id, goal_title, goal_description, status, priority_weight, confidence_score, confidence_state, approved, created_at, updated_at)
    VALUES (new.id, new.entity_id, SUBSTR(new.goal, 1, 60), new.goal, new.status, new.priority, 1.0, 'CONFIRMED', new.approved, new.created_at, new.updated_at);
END;

DROP TRIGGER IF EXISTS trg_hm_user_goals_update;
CREATE TRIGGER trg_hm_user_goals_update INSTEAD OF UPDATE ON hm_user_goals BEGIN
    UPDATE relationship_goals
    SET goal_description = new.goal, goal_title = SUBSTR(new.goal, 1, 60), status = new.status, priority_weight = new.priority, approved = new.approved, updated_at = new.updated_at
    WHERE goal_id = old.id;
END;
""")

# Insert entity
conn.execute("INSERT INTO relationship_entities VALUES ('u1', 'user', 'User 1', 'TRUST_USER', 1, 0, ?, ?)", (time.time(), time.time()))

# Insert goal via view
goal_id = "g1"
conn.execute(
    "INSERT INTO hm_user_goals (id, entity_id, goal, status, priority, approved, created_at, updated_at) VALUES (?, 'u1', 'Sample Goal', 'active', 0.8, 0, ?, ?)",
    (goal_id, time.time(), time.time())
)
conn.commit()

# Query goal
row = conn.execute("SELECT * FROM relationship_goals").fetchone()
print("Inserted goal:", dict(row))

# Update via view
cur = conn.execute("UPDATE hm_user_goals SET approved = 1, updated_at = ? WHERE id = ?", (time.time(), goal_id))
conn.commit()
print("Rowcount:", cur.rowcount)
row = conn.execute("SELECT * FROM relationship_goals").fetchone()
print("Updated goal:", dict(row))
