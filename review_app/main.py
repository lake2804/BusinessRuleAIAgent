"""Review App - Main Entry Point (Port 8502).

Queries the shared business-rule vector store and optionally validates an
uploaded input file against retrieved evidence.
"""
import asyncio
import sys
import uuid
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_app.vector_store import VectorStore
from review_app.parsers.input_file_parser import UserInputFileParser
from review_app.workflow import run_review_workflow
from shared.config import (
    get_api_key,
    get_api_key_env_var,
    get_default_model,
    get_models,
    get_providers,
    normalize_model,
    normalize_provider,
)
from shared.llm import LLMError, LLMFactory
from shared.review_prompts import (
    GROUNDING_CHECKLIST,
    ISSUE_TAXONOMY,
)
from shared.storage import get_provider_config, list_domains, save_provider_config


st.set_page_config(page_title="Review App", page_icon=":zap:", layout="wide")
st.title("Review App")
st.caption("Uses the RAG vector store and review input parser")


@st.cache_resource
def get_vector_store():
    store = VectorStore()
    store.initialize()
    return store


vector_store = get_vector_store()

st.sidebar.title("Review App")
st.sidebar.markdown("---")

st.sidebar.subheader("Provider Settings")
saved_config = get_provider_config()
provider_options = get_providers()
saved_provider = normalize_provider(saved_config.get("provider") if saved_config else None)

provider = st.sidebar.selectbox(
    "Provider",
    provider_options,
    index=provider_options.index(saved_provider),
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

manual_api_key = st.sidebar.text_input(
    "API Key (session only)",
    type="password",
    value="",
    help=f"Prefer setting {get_api_key_env_var(provider)}. This field is not saved to SQLite.",
)
api_key = manual_api_key or get_api_key(provider)

if st.sidebar.button("Save Settings"):
    save_provider_config(provider, model)
    st.sidebar.success("Provider and model saved. API keys are not stored.")

st.sidebar.markdown("---")
st.sidebar.caption("Port: 8502 | Query business rules here")

if not api_key:
    st.error(f"Please configure an API key or set {get_api_key_env_var(provider)}")
    st.stop()

llm = LLMFactory.create(provider, api_key, model)
file_parser = UserInputFileParser()

domains = list_domains()
if not domains:
    st.warning("No domains found. Use RAG App (port 8501) to create domains first.")
    st.stop()

col1, col2 = st.columns([1, 2])

with col1:
    st.header("Query Configuration")

    domain_options = {d["name"]: d["domain_id"] for d in domains}
    selected_domain = st.selectbox("Domain", list(domain_options.keys()))
    domain_id = domain_options[selected_domain]

    query = st.text_area(
        "Your Query",
        height=100,
        placeholder="e.g., Validate this invoice against approval rules",
    )

    st.subheader("Input File (Optional)")
    input_file = st.file_uploader(
        "Upload file to validate",
        type=["pdf", "docx", "txt", "md", "csv", "json"],
    )

    parsed_file = None
    if input_file:
        with st.spinner("Parsing input file..."):
            upload_dir = Path("./data/review_uploads")
            upload_dir.mkdir(parents=True, exist_ok=True)
            file_path = upload_dir / f"{uuid.uuid4()}_{input_file.name}"

            with open(file_path, "wb") as f:
                f.write(input_file.getbuffer())

            parsed_file = asyncio.run(file_parser.parse(file_path))
            st.success(f"Parsed: {parsed_file['file_name']}")

    if st.button("Run Review", type="primary"):
        if not query:
            st.warning("Please enter a query")
        else:
            with st.spinner("Processing..."):
                try:
                    result = asyncio.run(
                        run_review_workflow(
                            query=query,
                            domain_id=domain_id,
                            parsed_file=parsed_file,
                            llm=llm,
                            vector_store=vector_store,
                        )
                    )
                    st.session_state["review_result"] = result.to_session_dict()
                    st.rerun()
                except LLMError as exc:
                    st.error(f"LLM request failed: {exc}")
                except ValueError as exc:
                    st.warning(str(exc))
                except Exception as exc:
                    st.error(f"Review failed: {exc}")

with col2:
    st.header("Results")

    if "review_result" in st.session_state:
        result = st.session_state["review_result"]

        st.markdown("### Answer")
        st.markdown(result["answer"])

        st.markdown("---")
        st.caption(f"Evidence: {result['evidence_count']} chunks")

        coverage = result.get("coverage")
        if coverage:
            st.markdown("### Retrieval Coverage")
            st.write(
                {
                    "mode": coverage["mode"],
                    "documents": coverage["document_count"],
                    "sections": coverage["section_count"],
                    "deduped_chunks": coverage["deduped_evidence_count"],
                    "final_chunks": coverage["final_evidence_count"],
                    "duplicates_removed": coverage["duplicates_removed"],
                    "budget_trimmed": coverage["budget_trimmed_count"],
                    "versions": coverage["versions"],
                    "best_score": round(coverage["best_score"], 3),
                    "average_score": round(coverage["average_score"], 3),
                }
            )
            if coverage["low_confidence"]:
                st.warning(
                    "Evidence confidence is low. Treat this answer as incomplete unless the cited sources look right."
                )
            if coverage["mode"] == "validation":
                with st.expander("Validation issue taxonomy"):
                    for issue_type, description in ISSUE_TAXONOMY.items():
                        st.markdown(f"**{issue_type}**: {description}")
                    st.markdown("**Grounding checklist**")
                    for item in GROUNDING_CHECKLIST:
                        st.markdown(f"- {item}")

        if result["evidence"]:
            with st.expander("Evidence used"):
                citations = result.get("citations") or []
                if citations:
                    st.markdown("**Cited Sources**")
                    for citation in citations:
                        st.caption(citation)
                for match in result["evidence"]:
                    metadata = match["metadata"]
                    st.markdown(
                        f"**{metadata.get('source_file', 'unknown')}** "
                        f"- {metadata.get('section_path', 'unknown')} "
                        f"- v{metadata.get('version', 'unknown')} "
                        f"- score {match['score']:.3f} "
                        f"- rerank {match.get('rerank_score', match['score']):.3f}"
                    )
                    st.text(match["content"][:700])

        if result["parsed_file"]:
            st.markdown(f"**Parsed File:** {result['parsed_file']['file_name']}")
            with st.expander("View parsed content"):
                st.text(result["parsed_file"]["content"][:500] + "...")
    else:
        st.info("Configure query and click 'Run Review'")

st.markdown("---")
stats = vector_store.get_stats()
st.caption(f"Connected to RAG Vector Store: {stats['total_chunks']} chunks")
