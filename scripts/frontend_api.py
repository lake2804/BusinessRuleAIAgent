"""Shared command/API helpers used by the React frontend Python API servers."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sqlite3
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DB_PATH = Path(os.getenv("APP_DB_PATH", ROOT / "data" / "app.db"))


def connect():
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def parse_json(value: str):
    try:
        return json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}


def domains():
    conn = connect()
    if not conn:
        return {"domains": []}
    rows = conn.execute(
        """
        SELECT
            d.*,
            COUNT(doc.document_id) AS document_count,
            COALESCE(SUM(doc.chunk_count), 0) AS chunk_count
        FROM domains d
        LEFT JOIN documents doc ON doc.domain_id = d.domain_id
        GROUP BY d.domain_id
        ORDER BY d.created_at DESC
        """
    ).fetchall()
    conn.close()
    return {"domains": [dict(row) for row in rows]}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or f"domain_{uuid.uuid4().hex[:8]}"


def domain_create(name: str, description: str = "", domain_id: str = ""):
    from shared.storage import create_domain

    cleaned_name = name.strip()
    if not cleaned_name:
        return {"error": "Domain name is required"}
    cleaned_domain_id = slugify(domain_id or cleaned_name)
    try:
        domain = create_domain(cleaned_domain_id, cleaned_name, description.strip())
        return {"domain": domain}
    except sqlite3.IntegrityError:
        return {"error": f"Domain '{cleaned_domain_id}' already exists"}


def rag_files(domain_id: str, search: str = ""):
    conn = connect()
    if not conn or not domain_id:
        return {"files": []}
    rows = conn.execute(
        "SELECT * FROM documents WHERE domain_id = ? ORDER BY uploaded_at DESC",
        (domain_id,),
    ).fetchall()
    conn.close()
    search_lower = search.lower()
    files = []
    for row in rows:
        item = dict(row)
        item["metadata"] = parse_json(item.pop("metadata_json", "{}"))
        haystack = json.dumps(item, ensure_ascii=False).lower()
        if not search_lower or search_lower in haystack:
            files.append(item)
    return {"files": files}


def rag_file(document_id: str):
    conn = connect()
    if not conn:
        return {"error": "Database not found"}
    row = conn.execute("SELECT * FROM documents WHERE document_id = ?", (document_id,)).fetchone()
    conn.close()
    if not row:
        return {"error": "File not found"}
    item = dict(row)
    item["metadata"] = parse_json(item.pop("metadata_json", "{}"))
    return {"file": item}


def infer_document_status(file_name: str) -> str:
    upper_name = file_name.upper()
    if "ARCHIVED" in upper_name or "DEPRECATED" in upper_name:
        return "archived"
    return "active"


def _resolve_manifest_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def _relative_to_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def rag_ingest(domain_id: str, ruleset_name: str, version: str, manifest_path: str):
    from rag_app.parsers.business_rule_parser import BusinessRuleFileParser
    from shared.storage import save_ingestion_job

    if not domain_id:
        return {"error": "Domain is required"}
    if not ruleset_name.strip():
        return {"error": "Ruleset name is required"}

    manifest = _resolve_manifest_path(manifest_path)
    records = json.loads(manifest.read_text(encoding="utf-8-sig"))
    if isinstance(records, dict):
        records = [records]
    if not records:
        return {"error": "No files were provided"}

    for record in records:
        save_ingestion_job(
            record.get("job_id") or str(uuid.uuid4()),
            domain_id,
            record.get("source_file", ""),
            "queued",
            "Waiting for vector store initialization",
        )

    try:
        from rag_app.vector_store import VectorStore
        from shared.rule_conflicts import detect_rule_conflicts
        from shared.rule_metadata import extract_rule_metadata
        from shared.storage import save_document_record

        for record in records:
            save_ingestion_job(
                record.get("job_id") or str(uuid.uuid4()),
                domain_id,
                record.get("source_file", ""),
                "running",
                "Initializing vector store and embedding model",
            )
        vector_store = VectorStore()
        vector_store.initialize()
    except Exception as exc:
        for record in records:
            save_ingestion_job(
                record.get("job_id") or str(uuid.uuid4()),
                domain_id,
                record.get("source_file", ""),
                "failed",
                message=f"Vector store initialization failed: {exc}",
            )
        return {
            "results": [
                {
                    "source_file": record.get("source_file", ""),
                    "status": "failed",
                    "message": f"Vector store initialization failed: {exc}",
                    "chunk_count": 0,
                    "conflict_count": 0,
                    "conflicts": [],
                }
                for record in records
            ],
            "succeeded": 0,
            "failed": len(records),
        }

    parser = BusinessRuleFileParser()
    ruleset_id = slugify(ruleset_name)
    version = version.strip() or "1.0.0"
    results = []

    for record in records:
        source_file = record.get("source_file", "")
        job_id = record.get("job_id") or str(uuid.uuid4())
        stored_path = _resolve_manifest_path(record.get("stored_path", ""))

        try:
            save_ingestion_job(job_id, domain_id, source_file, "running", "Parsing file")
            file_bytes = stored_path.read_bytes()
            content_hash = hashlib.sha256(file_bytes).hexdigest()
            document_id = hashlib.sha256(f"{domain_id}:".encode("utf-8") + file_bytes).hexdigest()
            document_status = infer_document_status(source_file)

            _text, chunks = parser.parse(stored_path)
            save_ingestion_job(
                job_id,
                domain_id,
                source_file,
                "running",
                f"Embedding {len(chunks)} chunks",
            )
            existing_active = vector_store.list_rules(
                domain_id=domain_id,
                active_only=True,
                limit=500,
            )
            conflicts = detect_rule_conflicts(chunks, existing_active)

            texts = [chunk["content"] for chunk in chunks]
            metadata = [
                {
                    "domain_id": domain_id,
                    "ruleset_id": ruleset_id,
                    "version": version,
                    "document_id": document_id,
                    "source_file": chunk["source_file"],
                    "chunk_type": chunk["chunk_type"],
                    "section_path": chunk["section_path"],
                    "parent_id": chunk.get("parent_id") or "",
                    "source_page": chunk.get("source_page") or "",
                    "status": document_status,
                    "active": document_status == "active",
                    **extract_rule_metadata(chunk["content"], chunk["section_path"]),
                }
                for chunk in chunks
            ]

            ids = vector_store.add_rules(texts, metadata)
            vector_store.deactivate_rules(
                domain_id=domain_id,
                document_id=document_id,
                exclude_ids=set(ids),
            )
            save_document_record(
                document_id=document_id,
                domain_id=domain_id,
                ruleset_id=ruleset_id,
                version=version,
                source_file=source_file,
                status=document_status,
                content_hash=content_hash,
                chunk_count=len(ids),
                metadata={
                    "stored_path": _relative_to_root(stored_path),
                    "uploaded_file_name": source_file,
                    "ingested_from": "react_frontend",
                },
            )
            save_ingestion_job(
                job_id,
                domain_id,
                source_file,
                "succeeded",
                chunk_count=len(ids),
            )
            results.append(
                {
                    "source_file": source_file,
                    "document_id": document_id,
                    "status": "succeeded",
                    "document_status": document_status,
                    "chunk_count": len(ids),
                    "conflict_count": len(conflicts),
                    "conflicts": conflicts[:25],
                }
            )
        except Exception as exc:
            save_ingestion_job(job_id, domain_id, source_file, "failed", message=str(exc))
            results.append(
                {
                    "source_file": source_file,
                    "status": "failed",
                    "message": str(exc),
                    "chunk_count": 0,
                    "conflict_count": 0,
                    "conflicts": [],
                }
            )

    return {
        "results": results,
        "succeeded": sum(1 for item in results if item["status"] == "succeeded"),
        "failed": sum(1 for item in results if item["status"] == "failed"),
    }


def rag_jobs(limit: int = 25):
    from shared.storage import list_ingestion_jobs

    return {"jobs": list_ingestion_jobs(limit=limit)}


def rag_stats():
    conn = connect()
    domain_count = 0
    document_count = 0
    active_count = 0
    archived_count = 0
    chunk_count = 0
    if conn:
        domain_count = conn.execute("SELECT COUNT(*) FROM domains").fetchone()[0]
        document_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        active_count = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE status = 'active'"
        ).fetchone()[0]
        archived_count = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE status <> 'active'"
        ).fetchone()[0]
        chunk_count = conn.execute("SELECT COALESCE(SUM(chunk_count), 0) FROM documents").fetchone()[0]
        conn.close()

    return {
        "stats": {
            "domain_count": domain_count,
            "document_count": document_count,
            "active_count": active_count,
            "archived_count": archived_count,
            "registered_chunks": chunk_count,
            "vector_chunks": chunk_count,
        }
    }


def rag_chunks(document_id: str, limit: int = 200):
    file_data = rag_file(document_id).get("file")
    if not file_data:
        return {"chunks": [], "error": "File not found"}

    try:
        from rag_app.vector_store import VectorStore

        vector_store = VectorStore()
        vector_store.initialize()
        matches = vector_store.list_rules(
            domain_id=file_data["domain_id"],
            active_only=False,
            limit=max(limit, 500),
        )
        chunks = [
            match for match in matches
            if match.get("metadata", {}).get("document_id") == document_id
        ][:limit]
        return {"chunks": chunks}
    except Exception as exc:
        return {"chunks": [], "error": str(exc)}


def rag_update_status(document_id: str, status: str):
    from rag_app.vector_store import VectorStore
    from shared.storage import update_document_status

    normalized = status.strip().lower()
    if normalized not in {"active", "archived"}:
        return {"error": "Status must be active or archived"}

    file_data = rag_file(document_id).get("file")
    if not file_data:
        return {"error": "File not found"}

    update_document_status(document_id, normalized)
    vector_store = VectorStore()
    vector_store.initialize()
    updated_chunks = vector_store.set_rules_active(
        domain_id=file_data["domain_id"],
        document_id=document_id,
        active=normalized == "active",
    )
    return {"file": rag_file(document_id).get("file"), "updated_chunks": updated_chunks}


def provider_settings():
    from shared.config import (
        get_api_key,
        get_api_key_env_var,
        get_default_model,
        get_models,
        get_providers,
        normalize_model,
        normalize_provider,
    )
    from shared.storage import get_provider_config

    saved_config = get_provider_config() or {}
    provider = normalize_provider(saved_config.get("provider"))
    model = normalize_model(provider, saved_config.get("model", get_default_model(provider)))
    providers = get_providers()
    return {
        "config": {
            "provider": provider,
            "model": model,
            "api_key_saved": False,
            "api_key_env_var": get_api_key_env_var(provider),
            "api_key_from_env": bool(get_api_key(provider)),
        },
        "providers": providers,
        "models": {item: get_models(item) for item in providers},
        "defaults": {item: get_default_model(item) for item in providers},
        "env_vars": {item: get_api_key_env_var(item) for item in providers},
        "env_configured": {item: bool(get_api_key(item)) for item in providers},
    }


def provider_settings_save(provider: str, model: str):
    from shared.config import normalize_model, normalize_provider
    from shared.storage import save_provider_config

    normalized_provider = normalize_provider(provider)
    normalized_model = normalize_model(normalized_provider, model)
    save_provider_config(normalized_provider, normalized_model)
    return {"config": provider_settings()["config"]}


def provider_health(provider: str, model: str, api_key: str):
    from shared.config import get_api_key, normalize_model, normalize_provider
    from shared.llm import LLMFactory

    normalized_provider = normalize_provider(provider)
    normalized_model = normalize_model(normalized_provider, model)
    resolved_key = api_key or get_api_key(normalized_provider)
    if not resolved_key:
        return {
            "ok": False,
            "provider": normalized_provider,
            "model": normalized_model,
            "message": "No API key provided and no environment key is configured.",
        }

    async def _check():
        llm = LLMFactory.create(normalized_provider, resolved_key, normalized_model)
        response = await llm.complete(
            [{"role": "user", "content": "Reply with exactly: OK"}],
            temperature=0,
            max_tokens=8,
        )
        return response

    try:
        response = asyncio.run(_check())
        return {
            "ok": True,
            "provider": normalized_provider,
            "model": response.model or normalized_model,
            "message": "API key health check succeeded.",
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": normalized_provider,
            "model": normalized_model,
            "message": str(exc),
        }


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("domains")
    create = sub.add_parser("domain-create")
    create.add_argument("--name", required=True)
    create.add_argument("--description", default="")
    create.add_argument("--domain-id", default="")
    files = sub.add_parser("rag-files")
    files.add_argument("--domain-id", required=True)
    files.add_argument("--search", default="")
    file_parser = sub.add_parser("rag-file")
    file_parser.add_argument("--document-id", required=True)
    ingest = sub.add_parser("rag-ingest")
    ingest.add_argument("--domain-id", required=True)
    ingest.add_argument("--ruleset-name", required=True)
    ingest.add_argument("--version", default="1.0.0")
    ingest.add_argument("--manifest", required=True)
    jobs = sub.add_parser("rag-jobs")
    jobs.add_argument("--limit", type=int, default=25)
    sub.add_parser("rag-stats")
    chunks = sub.add_parser("rag-chunks")
    chunks.add_argument("--document-id", required=True)
    chunks.add_argument("--limit", type=int, default=200)
    update = sub.add_parser("rag-update-status")
    update.add_argument("--document-id", required=True)
    update.add_argument("--status", required=True)
    sub.add_parser("provider-settings")
    save_settings = sub.add_parser("provider-settings-save")
    save_settings.add_argument("--provider", required=True)
    save_settings.add_argument("--model", required=True)
    health = sub.add_parser("provider-health")
    health.add_argument("--provider", required=True)
    health.add_argument("--model", required=True)
    health.add_argument("--api-key", default="")
    args = parser.parse_args()

    if args.cmd == "domains":
        result = domains()
    elif args.cmd == "domain-create":
        result = domain_create(args.name, args.description, args.domain_id)
    elif args.cmd == "rag-files":
        result = rag_files(args.domain_id, args.search)
    elif args.cmd == "rag-file":
        result = rag_file(args.document_id)
    elif args.cmd == "rag-ingest":
        result = rag_ingest(args.domain_id, args.ruleset_name, args.version, args.manifest)
    elif args.cmd == "rag-jobs":
        result = rag_jobs(args.limit)
    elif args.cmd == "rag-stats":
        result = rag_stats()
    elif args.cmd == "rag-chunks":
        result = rag_chunks(args.document_id, args.limit)
    elif args.cmd == "rag-update-status":
        result = rag_update_status(args.document_id, args.status)
    elif args.cmd == "provider-settings":
        result = provider_settings()
    elif args.cmd == "provider-settings-save":
        result = provider_settings_save(args.provider, args.model)
    else:
        result = provider_health(args.provider, args.model, args.api_key)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
