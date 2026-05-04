from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.frontend_api import (  # noqa: E402
    domain_create,
    domains,
    provider_health,
    provider_settings,
    provider_settings_save,
    rag_chunks,
    rag_file,
    rag_files,
    rag_ingest,
    rag_jobs,
    rag_stats,
    rag_update_status,
)
from shared.simple_http import (  # noqa: E402
    JsonApiHandler,
    file_response,
    json_response,
    parse_multipart,
    query_params,
    read_display_content,
    read_json_body,
    run_server,
    safe_file_name,
)
from shared.storage import init_db  # noqa: E402


UPLOAD_DIR = ROOT / "data" / "uploads"


def _status_for_result(result: dict, default: int = 200) -> int:
    return 400 if result.get("error") else default


def _stored_path(metadata: dict) -> Path | None:
    stored = (metadata or {}).get("stored_path")
    if not stored:
        return None
    path = Path(str(stored))
    return path if path.is_absolute() else ROOT / path


def get_domains(handler):
    json_response(handler, domains())


def post_domain(handler):
    payload = read_json_body(handler)
    result = domain_create(
        payload.get("name", ""),
        payload.get("description", ""),
        payload.get("domainId", "") or payload.get("domain_id", ""),
    )
    json_response(handler, result, _status_for_result(result, 201))


def get_files(handler):
    params = query_params(handler)
    json_response(handler, rag_files(params.get("domainId", "") or params.get("domain_id", ""), params.get("search", "")))


def post_files(handler):
    fields, files = parse_multipart(handler)
    domain_id = fields.get("domainId") or fields.get("domain_id") or ""
    ruleset_name = fields.get("rulesetName") or fields.get("ruleset_name") or ""
    version = fields.get("version") or "1.0.0"
    if not domain_id:
        json_response(handler, {"error": "Domain is required"}, 400)
        return
    if not files:
        json_response(handler, {"error": "No files were uploaded"}, 400)
        return

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    for item in files:
        job_id = str(uuid.uuid4())
        file_name = safe_file_name(item["filename"])
        stored_name = f"{job_id}_{file_name}"
        stored_path = UPLOAD_DIR / stored_name
        stored_path.write_bytes(item["content"])
        records.append(
            {
                "job_id": job_id,
                "source_file": file_name,
                "stored_path": str(stored_path.relative_to(ROOT)).replace("\\", "/"),
            }
        )

    manifest_path = UPLOAD_DIR / f"manifest_{uuid.uuid4().hex}.json"
    manifest_path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    result = rag_ingest(domain_id, ruleset_name, version, str(manifest_path))
    status = 207 if result.get("failed") and result.get("succeeded") else _status_for_result(result, 201)
    json_response(handler, result, status)


def get_file(handler):
    document_id = handler.path_params["document_id"]
    result = rag_file(document_id)
    file_data = result.get("file")
    if not file_data:
        json_response(handler, result, _status_for_result(result, 404))
        return
    content_path = _stored_path(file_data.get("metadata", {})) or (ROOT / "__missing_file__")
    content = read_display_content(content_path, file_data.get("source_file", ""))
    payload = {"file": file_data, "content": content}
    params = query_params(handler)
    if params.get("includeChunks") == "1":
        chunk_result = rag_chunks(document_id)
        payload["chunks"] = chunk_result.get("chunks", [])
        if chunk_result.get("error"):
            payload["chunksError"] = chunk_result["error"]
    json_response(handler, payload)


def patch_file(handler):
    document_id = handler.path_params["document_id"]
    payload = read_json_body(handler)
    result = rag_update_status(document_id, payload.get("status", ""))
    json_response(handler, result, _status_for_result(result))


def download_file(handler):
    document_id = handler.path_params["document_id"]
    result = rag_file(document_id)
    file_data = result.get("file")
    if not file_data:
        json_response(handler, result, _status_for_result(result, 404))
        return
    path = _stored_path(file_data.get("metadata", {}))
    if not path:
        json_response(handler, {"error": "Stored file path is missing"}, 404)
        return
    file_response(handler, path, file_data.get("source_file", path.name))


def preview_file(handler):
    document_id = handler.path_params["document_id"]
    result = rag_file(document_id)
    file_data = result.get("file")
    if not file_data:
        json_response(handler, result, _status_for_result(result, 404))
        return
    path = _stored_path(file_data.get("metadata", {}))
    if not path:
        json_response(handler, {"error": "Stored file path is missing"}, 404)
        return
    file_response(handler, path, file_data.get("source_file", path.name), inline=True)


def get_jobs(handler):
    params = query_params(handler)
    json_response(handler, rag_jobs(int(params.get("limit", "25"))))


def get_stats(handler):
    json_response(handler, rag_stats())


def get_settings(handler):
    json_response(handler, provider_settings())


def post_settings(handler):
    payload = read_json_body(handler)
    provider = payload.get("provider", "")
    model = payload.get("model", "")
    result = provider_settings_save(provider, model)
    if payload.get("checkHealth"):
        result["health"] = provider_health(provider, model, payload.get("apiKey", ""))
    json_response(handler, result, _status_for_result(result))


class RagApiHandler(JsonApiHandler):
    routes = {
        "GET /api/domains": get_domains,
        "POST /api/domains": post_domain,
        "GET /api/rag/files": get_files,
        "POST /api/rag/files": post_files,
        "GET /api/rag/files/<document_id>": get_file,
        "PATCH /api/rag/files/<document_id>": patch_file,
        "GET /api/rag/files/<document_id>/download": download_file,
        "GET /api/rag/files/<document_id>/preview": preview_file,
        "GET /api/rag/jobs": get_jobs,
        "GET /api/rag/stats": get_stats,
        "GET /api/settings": get_settings,
        "POST /api/settings": post_settings,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8601)
    args = parser.parse_args()
    init_db()
    run_server(RagApiHandler, args.port, "RAG")


if __name__ == "__main__":
    main()
