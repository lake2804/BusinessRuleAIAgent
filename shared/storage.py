"""Shared storage - SQLite for persistence."""
import sqlite3
import json
from typing import Dict, List, Optional
from pathlib import Path

DB_PATH = Path("./data/app.db")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS domains (
            domain_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()


def create_domain(domain_id: str, name: str, description: str = "") -> Dict:
    conn = get_connection()
    conn.execute(
        "INSERT INTO domains (domain_id, name, description) VALUES (?, ?, ?)",
        (domain_id, name, description)
    )
    conn.commit()
    conn.close()
    return {"domain_id": domain_id, "name": name, "description": description}


def list_domains() -> List[Dict]:
    conn = get_connection()
    cursor = conn.execute("SELECT * FROM domains ORDER BY created_at DESC")
    domains = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return domains


def save_setting(key: str, value: str):
    conn = get_connection()
    conn.execute(
        """INSERT INTO settings (key, value) VALUES (?, ?)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
        (key, value)
    )
    conn.commit()
    conn.close()


def get_setting(key: str) -> Optional[str]:
    conn = get_connection()
    cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else None


def save_provider_config(provider: str, api_key: str, model: str):
    config = json.dumps({"provider": provider, "api_key": api_key, "model": model})
    save_setting("provider_config", config)


def get_provider_config() -> Optional[Dict]:
    value = get_setting("provider_config")
    return json.loads(value) if value else None


init_db()
