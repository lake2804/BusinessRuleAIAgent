from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shared.simple_http import (  # noqa: E402
    JsonApiHandler,
    file_response,
    json_response,
    parse_multipart,
    read_json_body,
    read_display_content,
    run_server,
    safe_file_name,
)
from shared.config import get_api_key, get_default_model, normalize_model, normalize_provider  # noqa: E402
from shared.llm import LLMFactory  # noqa: E402
from shared.storage import get_provider_config, list_documents, list_review_runs  # noqa: E402
from rag_app.vector_store import VectorStore  # noqa: E402
from review_app.parsers.input_file_parser import UserInputFileParser  # noqa: E402
from review_app.review_service import run_review as run_review_service  # noqa: E402


UPLOAD_DIR = ROOT / "data" / "review_uploads"
INDEX_PATH = UPLOAD_DIR / ".frontend_uploads.json"


def _load_index() -> list[dict]:
    if not INDEX_PATH.exists():
        return []
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _save_index(records: list[dict]):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def _record_path(record: dict) -> Path:
    path = Path(record.get("stored_path", ""))
    return path if path.is_absolute() else ROOT / path


def list_uploads(handler):
    records = sorted(_load_index(), key=lambda item: item.get("uploaded_at", ""), reverse=True)
    json_response(handler, {"uploads": records})


def create_upload(handler):
    _fields, files = parse_multipart(handler)
    if not files:
        json_response(handler, {"error": "No file was uploaded"}, 400)
        return
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    records = _load_index()
    created = []
    for item in files:
        upload_id = str(uuid.uuid4())
        file_name = safe_file_name(item["filename"])
        stored_path = UPLOAD_DIR / f"{upload_id}_{file_name}"
        stored_path.write_bytes(item["content"])
        record = {
            "upload_id": upload_id,
            "source_file": file_name,
            "content_type": item.get("content_type", "application/octet-stream"),
            "size_bytes": len(item["content"]),
            "stored_path": str(stored_path.relative_to(ROOT)).replace("\\", "/"),
            "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        records.append(record)
        created.append(record)
    _save_index(records)
    json_response(handler, {"uploads": created}, 201)


def get_upload(handler):
    upload_id = handler.path_params["upload_id"]
    record = next((item for item in _load_index() if item.get("upload_id") == upload_id), None)
    if not record:
        json_response(handler, {"error": "Upload not found"}, 404)
        return
    json_response(handler, {"upload": record, "content": read_display_content(_record_path(record), record["source_file"])})


def download_upload(handler):
    upload_id = handler.path_params["upload_id"]
    record = next((item for item in _load_index() if item.get("upload_id") == upload_id), None)
    if not record:
        json_response(handler, {"error": "Upload not found"}, 404)
        return
    file_response(handler, _record_path(record), record["source_file"], record.get("content_type"))


def preview_upload(handler):
    upload_id = handler.path_params["upload_id"]
    record = next((item for item in _load_index() if item.get("upload_id") == upload_id), None)
    if not record:
        json_response(handler, {"error": "Upload not found"}, 404)
        return
    file_response(handler, _record_path(record), record["source_file"], record.get("content_type"), inline=True)


def _combined_parsed_uploads(records: list[dict], domain_id: str) -> dict | None:
    if not records:
        return None

    parser = UserInputFileParser()
    parsed_items = []
    for record in records:
        path = _record_path(record)
        
        # Check if file exists
        if not path.exists():
            print(f"Warning: File not found: {path}")
            continue
            
        try:
            # Try to get the current event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is running, create a task
                    parsed = loop.run_until_complete(parser.parse(path))
                else:
                    # If no loop is running, use asyncio.run
                    parsed = asyncio.run(parser.parse(path))
            except RuntimeError:
                # Fallback: use asyncio.run if no loop exists
                parsed = asyncio.run(parser.parse(path))
        except Exception as e:
            print(f"Error parsing file {path}: {str(e)}")
            continue
        
        if not parsed:
            continue
        parsed.setdefault("metadata", {})
        parsed["metadata"]["source"] = "review_upload"
        parsed["metadata"]["review_upload_id"] = record.get("upload_id", "")
        parsed["metadata"]["domain_matches"] = _find_domain_matches(domain_id, record, path)
        parsed_items.append(parsed)

    parsed_items = [item for item in parsed_items if item]
    if len(parsed_items) == 1:
        return parsed_items[0]

    content = []
    metadata = {"files": [], "records": [], "sources": [], "domain_matches": []}
    for parsed in parsed_items:
        content.append(f"### {parsed.get('file_name', 'uploaded file')}\n{parsed.get('content', '')}")
        metadata["files"].append(parsed.get("file_name", "uploaded file"))
        metadata["sources"].append(parsed.get("metadata", {}).get("source", "review_upload"))
        metadata["domain_matches"].extend(parsed.get("metadata", {}).get("domain_matches", []))
        records = parsed.get("metadata", {}).get("records") or []
        if isinstance(records, list):
            metadata["records"].extend(records)
    return {
        "file_name": f"{len(parsed_items)} uploaded files",
        "content": "\n\n".join(content),
        "metadata": metadata,
    }


def _find_domain_matches(domain_id: str, upload_record: dict, path: Path) -> list[dict]:
    if not domain_id or not path.exists():
        return []

    upload_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    upload_name = str(upload_record.get("source_file", ""))
    upload_stem = Path(upload_name).stem.lower()
    matches = []

    for document in list_documents(domain_id):
        if document.get("status") != "active":
            continue
        source_file = str(document.get("source_file", ""))
        source_stem = Path(source_file).stem.lower()
        match_type = ""
        if document.get("content_hash") == upload_hash:
            match_type = "exact_content_hash"
        elif upload_name and source_file.lower() == upload_name.lower():
            match_type = "same_file_name"
        elif upload_stem and upload_stem == source_stem:
            match_type = "same_file_stem"
        if not match_type:
            continue
        matches.append(
            {
                "match_type": match_type,
                "document_id": document.get("document_id"),
                "source_file": source_file,
                "ruleset_id": document.get("ruleset_id"),
                "version": document.get("version"),
                "status": document.get("status"),
                "chunk_count": document.get("chunk_count", 0),
            }
        )

    exact_matches = [item for item in matches if item["match_type"] == "exact_content_hash"]
    return exact_matches or matches[:5]


def run_review(handler):
    payload = read_json_body(handler)
    query = (payload.get("query") or "").strip()
    domain_id = (payload.get("domainId") or payload.get("domain_id") or "").strip()
    upload_ids = payload.get("uploadIds") or []
    if not query:
        json_response(handler, {"error": "Query is required"}, 400)
        return
    if not domain_id:
        json_response(handler, {"error": "Domain is required"}, 400)
        return

    # Validate domain exists
    from shared.storage import get_domain
    domain_row = get_domain(domain_id)
    if not domain_row:
        json_response(handler, {"error": f"Domain '{domain_id}' not found"}, 400)
        return
    domain_name = domain_row.get("name", "")

    index = _load_index()
    upload_records = [item for item in index if item.get("upload_id") in upload_ids]
    parsed_file = _combined_parsed_uploads(upload_records, domain_id)

    saved_config = get_provider_config() or {}
    provider = normalize_provider(payload.get("provider") or saved_config.get("provider"))
    model = normalize_model(
        provider,
        payload.get("model") or saved_config.get("model") or get_default_model(provider),
    )
    api_key = payload.get("apiKey") or get_api_key(provider)
    if not api_key:
        json_response(handler, {"error": f"API key is required for {provider}. Configure it in Settings or environment."}, 400)
        return

    vector_store = VectorStore()
    try:
        vector_store.initialize()
    except Exception as e:
        json_response(handler, {"error": f"Vector store initialization failed: {str(e)}"}, 500)
        return
    llm = LLMFactory.create(provider, api_key, model)

    try:
        result = asyncio.run(
            run_review_service(
                query=query,
                domain_id=domain_id,
                parsed_file=parsed_file,
                llm=llm,
                vector_store=vector_store,
                domain_name=domain_name,
            )
        )
        json_response(handler, {"result": result.to_session_dict()})
    except ValueError as e:
        json_response(handler, {"error": str(e)}, 400)
    except Exception as e:
        import traceback
        json_response(handler, {"error": f"Internal error: {str(e)}", "traceback": traceback.format_exc()}, 500)


def review_history(handler):
    json_response(handler, {"runs": list_review_runs(limit=20)})


class ReviewApiHandler(JsonApiHandler):
    routes = {
        "GET /api/review/uploads": list_uploads,
        "POST /api/review/uploads": create_upload,
        "GET /api/review/uploads/<upload_id>": get_upload,
        "GET /api/review/uploads/<upload_id>/download": download_upload,
        "GET /api/review/uploads/<upload_id>/preview": preview_upload,
        "POST /api/review/run": run_review,
        "GET /api/review/history": review_history,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8602)
    args = parser.parse_args()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    run_server(ReviewApiHandler, args.port, "Review")


if __name__ == "__main__":
    main()
