#!/usr/bin/env bash
set -euo pipefail

DB="rag-instabot/db/app_data.sqlite"

if [ ! -f "$DB" ]; then
  echo "ERROR: $DB not found. Place your DB first."
  exit 1
fi

sqlite3 "$DB" <<'SQL'
-- Create FTS5 virtual table indexing name + description; content is products
CREATE VIRTUAL TABLE IF NOT EXISTS products_fts
USING fts5(name, description, content='products', content_rowid='id');

-- Initial sync from products -> products_fts
INSERT INTO products_fts(rowid, name, description)
SELECT id, name, description FROM products
WHERE id NOT IN (SELECT rowid FROM products_fts);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS products_ai AFTER INSERT ON products BEGIN
  INSERT INTO products_fts(rowid, name, description)
  VALUES (new.id, new.name, new.description);
END;

CREATE TRIGGER IF NOT EXISTS products_ad AFTER DELETE ON products BEGIN
  INSERT INTO products_fts(products_fts, rowid, name, description)
  VALUES ('delete', old.id, old.name, old.description);
END;

CREATE TRIGGER IF NOT EXISTS products_au AFTER UPDATE ON products BEGIN
  INSERT INTO products_fts(products_fts, rowid, name, description)
  VALUES ('delete', old.id, old.name, old.description);
  INSERT INTO products_fts(rowid, name, description)
  VALUES (new.id, new.name, new.description);
END;
SQL

echo "FTS5 setup complete."
