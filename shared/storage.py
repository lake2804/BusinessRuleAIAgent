import os
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

DB_PATH = Path(os.getenv("APP_DB_PATH", "./data/app.db"))


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            document_id TEXT PRIMARY KEY,
            domain_id TEXT NOT NULL,
            ruleset_id TEXT NOT NULL,
            version TEXT NOT NULL,
            source_file TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            content_hash TEXT NOT NULL,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS review_runs (
            review_id TEXT PRIMARY KEY,
            domain_id TEXT NOT NULL,
            query TEXT NOT NULL,
            input_file TEXT DEFAULT '',
            confidence_json TEXT NOT NULL DEFAULT '{}',
            structured_json TEXT NOT NULL DEFAULT '{}',
            evidence_json TEXT NOT NULL DEFAULT '[]',
            export_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_jobs (
            job_id TEXT PRIMARY KEY,
            domain_id TEXT NOT NULL,
            source_file TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT DEFAULT '',
            chunk_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    _apply_migrations(conn)
    
    conn.commit()
    conn.close()


def _migration_applied(conn: sqlite3.Connection, version: int) -> bool:
    row = conn.execute("SELECT version FROM schema_migrations WHERE version = ?", (version,)).fetchone()
    return row is not None


def _mark_migration(conn: sqlite3.Connection, version: int):
    conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))


def _apply_migrations(conn: sqlite3.Connection):
    if not _migration_applied(conn, 1):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_domain ON documents(domain_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_ruleset ON documents(ruleset_id, version)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)")
        _mark_migration(conn, 1)


def create_domain(domain_id: str, name: str, description: str = "") -> Dict:
    conn = get_connection()
    conn.execute(
        "INSERT INTO domains (domain_id, name, description) VALUES (?, ?, ?)",
        (domain_id, name, description)
    )
    conn.commit()
    conn.close()
    return {"domain_id": domain_id, "name": name, "description": description}


def get_domain(domain_id: str) -> Optional[Dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM domains WHERE domain_id = ?", (domain_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_domains() -> List[Dict]:
    conn = get_connection()
    cursor = conn.execute("SELECT * FROM domains ORDER BY created_at DESC")
    domains = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return domains


def save_document_record(
    document_id: str,
    domain_id: str,
    ruleset_id: str,
    version: str,
    source_file: str,
    status: str,
    content_hash: str,
    chunk_count: int,
    metadata: Optional[Dict] = None,
) -> Dict:
    conn = get_connection()
    metadata_json = json.dumps(metadata or {})
    conn.execute(
        """INSERT INTO documents (
               document_id, domain_id, ruleset_id, version, source_file, status,
               content_hash, chunk_count, metadata_json
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(document_id) DO UPDATE SET
               domain_id = excluded.domain_id,
               ruleset_id = excluded.ruleset_id,
               version = excluded.version,
               source_file = excluded.source_file,
               status = excluded.status,
               content_hash = excluded.content_hash,
               chunk_count = excluded.chunk_count,
               metadata_json = excluded.metadata_json,
               updated_at = CURRENT_TIMESTAMP""",
        (
            document_id,
            domain_id,
            ruleset_id,
            version,
            source_file,
            status,
            content_hash,
            chunk_count,
            metadata_json,
        ),
    )
    conn.commit()
    conn.close()
    return {
        "document_id": document_id,
        "domain_id": domain_id,
        "ruleset_id": ruleset_id,
        "version": version,
        "source_file": source_file,
        "status": status,
        "content_hash": content_hash,
        "chunk_count": chunk_count,
        "metadata": metadata or {},
    }


def list_documents(domain_id: Optional[str] = None) -> List[Dict]:
    conn = get_connection()
    if domain_id:
        cursor = conn.execute(
            "SELECT * FROM documents WHERE domain_id = ? ORDER BY uploaded_at DESC",
            (domain_id,),
        )
    else:
        cursor = conn.execute("SELECT * FROM documents ORDER BY uploaded_at DESC")
    documents = []
    for row in cursor.fetchall():
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        documents.append(item)
    conn.close()
    return documents


def update_document_status(document_id: str, status: str):
    conn = get_connection()
    conn.execute(
        "UPDATE documents SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE document_id = ?",
        (status, document_id),
    )
    conn.commit()
    conn.close()


def save_review_run(
    review_id: str,
    domain_id: str,
    query: str,
    input_file: str,
    confidence: Dict,
    structured_output: Optional[Dict],
    evidence: List[Dict],
    exports: Dict,
):
    conn = get_connection()
    conn.execute(
        """INSERT INTO review_runs (
               review_id, domain_id, query, input_file, confidence_json,
               structured_json, evidence_json, export_json
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            review_id,
            domain_id,
            query,
            input_file,
            json.dumps(confidence or {}),
            json.dumps(structured_output or {}),
            json.dumps(evidence or []),
            json.dumps(exports or {}),
        ),
    )
    conn.commit()
    conn.close()


def list_review_runs(limit: int = 25) -> List[Dict]:
    conn = get_connection()
    cursor = conn.execute(
        "SELECT * FROM review_runs ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    runs = []
    for row in cursor.fetchall():
        item = dict(row)
        item["confidence"] = json.loads(item.pop("confidence_json") or "{}")
        item["structured_output"] = json.loads(item.pop("structured_json") or "{}")
        item["evidence"] = json.loads(item.pop("evidence_json") or "[]")
        item["exports"] = json.loads(item.pop("export_json") or "{}")
        runs.append(item)
    conn.close()
    return runs


def save_ingestion_job(
    job_id: str,
    domain_id: str,
    source_file: str,
    status: str,
    message: str = "",
    chunk_count: int = 0,
):
    conn = get_connection()
    conn.execute(
        """INSERT INTO ingestion_jobs (
               job_id, domain_id, source_file, status, message, chunk_count
           ) VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(job_id) DO UPDATE SET
               status = excluded.status,
               message = excluded.message,
               chunk_count = excluded.chunk_count,
               updated_at = CURRENT_TIMESTAMP""",
        (job_id, domain_id, source_file, status, message, chunk_count),
    )
    conn.commit()
    conn.close()


def list_ingestion_jobs(limit: int = 25) -> List[Dict]:
    conn = get_connection()
    cursor = conn.execute(
        "SELECT * FROM ingestion_jobs ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    )
    jobs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jobs


def save_setting(key: str, value: str):
    conn = get_connection()
    conn.execute(
        """INSERT INTO settings (key, value) VALUES (?, ?)
           ON CONFLICT(key) DO UPDATE SET
               value = excluded.value,
               updated_at = CURRENT_TIMESTAMP""",
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


def save_provider_config(provider: str, model: str):
    """Persist non-secret provider preferences only.

    API keys must come from environment variables or the current UI session.
    Older database rows may contain api_key, but get_provider_config strips it.
    """
    config = json.dumps({"provider": provider, "model": model})
    save_setting("provider_config", config)


def get_provider_config() -> Optional[Dict]:
    value = get_setting("provider_config")
    if not value:
        return None
    config = json.loads(value)
    if "api_key" in config:
        config.pop("api_key", None)
        save_setting("provider_config", json.dumps(config))
    return config


init_db()
