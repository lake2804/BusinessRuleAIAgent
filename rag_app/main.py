"""RAG App - Main Entry Point (Port 8501).

Builds the business-rule knowledge base by creating domains and ingesting
policy/rule documents into the shared vector store.
"""
import hashlib
import sys
import uuid
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_app.parsers.business_rule_parser import BusinessRuleFileParser
from rag_app.vector_store import VectorStore
from shared.config import (
    get_api_key,
    get_api_key_env_var,
    get_default_model,
    get_models,
    normalize_model,
)
from shared.storage import (
    create_domain,
    get_provider_config,
    list_domains,
    save_document_record,
    save_provider_config,
)


st.set_page_config(page_title="RAG App", page_icon=":books:", layout="wide")
st.title("RAG Business Rule App")
st.caption("Knowledge Base Builder - Upload business rules for RAG")


@st.cache_resource
def get_components():
    vector_store = VectorStore()
    vector_store.initialize()
    return {
        "vector_store": vector_store,
        "business_parser": BusinessRuleFileParser(),
    }


components = get_components()


def infer_document_status(file_name: str) -> str:
    upper_name = file_name.upper()
    if "ARCHIVED" in upper_name or "DEPRECATED" in upper_name:
        return "archived"
    return "active"

st.sidebar.title("RAG App")
st.sidebar.markdown("Build knowledge base only")
st.sidebar.markdown("---")

st.sidebar.subheader("Provider Settings")
saved_config = get_provider_config()

provider = st.sidebar.selectbox(
    "Provider",
    ["groq", "openai"],
    index=0 if not saved_config else ["groq", "openai"].index(saved_config.get("provider", "groq")),
)

models_for_provider = get_models(provider)
default_model = normalize_model(
    provider,
    saved_config.get("model", get_default_model(provider)) if saved_config else get_default_model(provider),
)

model = st.sidebar.selectbox(
    "Model",
    models_for_provider,
    index=models_for_provider.index(default_model) if default_model in models_for_provider else 0,
    help="Provider and model preferences are saved; API keys are not saved.",
)

env_api_key = get_api_key(provider)
api_key = st.sidebar.text_input(
    "API Key (session only)",
    type="password",
    value=env_api_key,
    help=f"Prefer setting {get_api_key_env_var(provider)}. This field is not saved to SQLite.",
)

if st.sidebar.button("Save Settings"):
    save_provider_config(provider, model)
    st.sidebar.success("Provider and model saved. API keys are not stored.")

st.sidebar.markdown("---")
st.sidebar.caption("Port: 8501 | Use Review App (8502) for queries")

st.header("Build Knowledge Base")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Create Domain")
    domain_name = st.text_input("Domain Name", placeholder="e.g., Invoice Processing")
    domain_desc = st.text_area("Description", placeholder="Describe this domain...")

    if st.button("Create Domain"):
        if domain_name:
            domain_id = domain_name.lower().replace(" ", "_")
            try:
                create_domain(domain_id, domain_name, domain_desc)
                st.success(f"Created: {domain_name}")
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to create domain: {exc}")

with col2:
    st.subheader("Upload Business Rules")
    domains = list_domains()

    if not domains:
        st.info("Create a domain first")
    else:
        domain_options = {d["name"]: d["domain_id"] for d in domains}
        selected_domain = st.selectbox("Select Domain", list(domain_options.keys()))
        domain_id = domain_options[selected_domain]

        ruleset_name = st.text_input("Ruleset Name", placeholder="e.g., Approval Rules")
        version = st.text_input("Version", value="1.0.0")

        uploaded_files = st.file_uploader(
            "Upload Business Rule Files",
            type=["pdf", "docx", "txt", "md", "csv", "json"],
            accept_multiple_files=True,
        )

        if st.button("Ingest Files", type="primary"):
            if ruleset_name and uploaded_files:
                with st.spinner("Parsing business rules..."):
                    for uploaded_file in uploaded_files:
                        upload_dir = Path("./data/uploads")
                        upload_dir.mkdir(parents=True, exist_ok=True)
                        file_path = upload_dir / f"{uuid.uuid4()}_{uploaded_file.name}"
                        file_bytes = uploaded_file.getbuffer()
                        document_id = hashlib.sha256(file_bytes).hexdigest()
                        document_status = infer_document_status(uploaded_file.name)

                        with open(file_path, "wb") as f:
                            f.write(file_bytes)

                        try:
                            _text, chunks = components["business_parser"].parse(file_path)
                            components["vector_store"].deactivate_rules(
                                domain_id=domain_id,
                                document_id=document_id,
                            )

                            texts = [c["content"] for c in chunks]
                            metadata = [
                                {
                                    "domain_id": domain_id,
                                    "ruleset_id": ruleset_name.lower().replace(" ", "_"),
                                    "version": version,
                                    "document_id": document_id,
                                    "source_file": c["source_file"],
                                    "chunk_type": c["chunk_type"],
                                    "section_path": c["section_path"],
                                    "parent_id": c.get("parent_id") or "",
                                    "source_page": c.get("source_page") or "",
                                    "status": document_status,
                                    "active": document_status == "active",
                                }
                                for c in chunks
                            ]

                            ids = components["vector_store"].add_rules(texts, metadata)
                            save_document_record(
                                document_id=document_id,
                                domain_id=domain_id,
                                ruleset_id=ruleset_name.lower().replace(" ", "_"),
                                version=version,
                                source_file=uploaded_file.name,
                                status=document_status,
                                content_hash=document_id,
                                chunk_count=len(ids),
                                metadata={
                                    "stored_path": str(file_path),
                                    "uploaded_file_name": uploaded_file.name,
                                },
                            )
                            st.success(f"{uploaded_file.name}: {len(ids)} chunks ingested")
                        except Exception as exc:
                            st.error(f"Failed to ingest {uploaded_file.name}: {exc}")
            else:
                st.warning("Provide ruleset name and files")

st.markdown("---")
stats = components["vector_store"].get_stats()
st.caption(f"Vector store: {stats['total_chunks']} chunks")
