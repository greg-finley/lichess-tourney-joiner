CREATE TABLE IF NOT EXISTS latest_tourney (
    id TEXT PRIMARY KEY,
    finishes_at TEXT NOT NULL
    );

INSERT INTO latest_tourney (id)
SELECT 'abc' WHERE NOT EXISTS (SELECT 1 FROM latest_tourney);

CREATE TABLE IF NOT EXISTS tourney_stats (
    username TEXT PRIMARY KEY,
    score INTEGER NOT NULL,
    games INTEGER NOT NULL,
    num_tournaments INTEGER NOT NULL,
    tournament_wins INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    draws INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tourney_stats_username ON tourney_stats(username); 
