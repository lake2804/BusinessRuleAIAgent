"""RAG App - Main Entry Point (Port 8501).

Architecture (4 components):
1. User Query Parser (parsers/query_parser.py)
2. User Input File Parser (parsers/input_file_parser.py)  
3. Orchestrator (orchestrator.py)
4. Final Synthesis (synthesis.py)

Plus: Business Rule File Parser for building knowledge (parsers/business_rule_parser.py)
"""
import streamlit as st
import sys
import uuid
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.storage import create_domain, list_domains, save_provider_config, get_provider_config
from shared.llm import LLMFactory
from shared.models import FinalResult
from rag_app.vector_store import VectorStore
from rag_app.parsers.business_rule_parser import BusinessRuleFileParser

st.set_page_config(page_title="RAG App", page_icon="📚", layout="wide")
st.title("📚 RAG Business Rule App")
st.caption("Knowledge Base Builder - Upload business rules for RAG")

# Initialize components
@st.cache_resource
def get_components():
    """Initialize all 4 components."""
    vector_store = VectorStore()
    vector_store.initialize()
    return {
        "vector_store": vector_store,
        "business_parser": BusinessRuleFileParser()
    }

components = get_components()

# Sidebar
st.sidebar.title("📚 RAG App")
st.sidebar.markdown("Build knowledge base only")
st.sidebar.markdown("---")

# Provider settings
st.sidebar.subheader("Provider Settings")
saved_config = get_provider_config()

# Available models per provider (from Groq official docs)
AVAILABLE_MODELS = {
    "groq": [
        # Production Models
        "llama-3.3-70b-versatile",           # Meta Llama 3.3 70B - Main production model
        "llama-3.1-8b-instant",              # Meta Llama 3.1 8B - Fast, cheap
        "openai/gpt-oss-120b",               # OpenAI GPT-OSS 120B - Flagship
        "openai/gpt-oss-20b",                # OpenAI GPT-OSS 20B - Fast, efficient
        # Production Systems
        "groq/compound",                     # Groq Compound with tools
        "groq/compound-mini",                # Groq Compound Mini
        # Preview Models
        "meta-llama/llama-4-scout-17b-16e-instruct",  # Llama 4 Scout
        "qwen/qwen3-32b",                    # Qwen3 32B
    ],
    "openai": [
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4-turbo",
        "gpt-3.5-turbo"
    ]
}

provider = st.sidebar.selectbox("Provider", ["groq", "openai"],
    index=0 if not saved_config else ["groq", "openai"].index(saved_config.get("provider", "groq")))

# Model dropdown based on provider
models_for_provider = AVAILABLE_MODELS.get(provider, [])
default_model = saved_config.get("model", models_for_provider[0]) if saved_config else models_for_provider[0]
# Ensure default is in the list
if default_model not in models_for_provider:
    default_model = models_for_provider[0]

model = st.sidebar.selectbox(
    "Model",
    models_for_provider,
    index=models_for_provider.index(default_model) if default_model in models_for_provider else 0,
    help="Select from Groq production models, systems, and preview models"
)

api_key = st.sidebar.text_input("API Key", type="password",
    value=saved_config.get("api_key", "") if saved_config else "")

if st.sidebar.button("💾 Save Settings"):
    if api_key:
        save_provider_config(provider, api_key, model)
        st.sidebar.success("Settings saved!")

st.sidebar.markdown("---")
st.sidebar.caption("Port: 8501 | Use Review App (8502) for queries")

# Note: LLM not needed for RAG app - only for Review app (port 8502)

# Main content - only for building knowledge
st.header("Build Knowledge Base")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Create Domain")
    domain_name = st.text_input("Domain Name", placeholder="e.g., Invoice Processing")
    domain_desc = st.text_area("Description", placeholder="Describe this domain...")
    
    if st.button("➕ Create Domain"):
        if domain_name:
            domain_id = domain_name.lower().replace(" ", "_")
            create_domain(domain_id, domain_name, domain_desc)
            st.success(f"Created: {domain_name}")
            st.rerun()

with col2:
    st.subheader("Upload Business Rules")
    domains = list_domains()
    
    if not domains:
        st.info("Create a domain first")
    else:
        domain_options = {d['name']: d['domain_id'] for d in domains}
        selected_domain = st.selectbox("Select Domain", list(domain_options.keys()))
        domain_id = domain_options[selected_domain]
        
        ruleset_name = st.text_input("Ruleset Name", placeholder="e.g., Approval Rules")
        version = st.text_input("Version", value="1.0.0")
        
        uploaded_files = st.file_uploader(
            "Upload Business Rule Files",
            type=["pdf", "docx", "txt", "md"],
            accept_multiple_files=True
        )
        
        if st.button("🚀 Ingest Files", type="primary"):
            if ruleset_name and uploaded_files:
                with st.spinner("Parsing business rules..."):
                    for uploaded_file in uploaded_files:
                        # Save
                        upload_dir = Path("./data/uploads")
                        upload_dir.mkdir(parents=True, exist_ok=True)
                        file_path = upload_dir / f"{uuid.uuid4()}_{uploaded_file.name}"
                        
                        with open(file_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                        
                        # Parse with Business Rule File Parser
                        text, chunks = components["business_parser"].parse(file_path)
                        
                        # Add to vector store
                        texts = [c["content"] for c in chunks]
                        metadata = [{
                            "domain_id": domain_id,
                            "ruleset_id": ruleset_name.lower().replace(" ", "_"),
                            "version": version,
                            "source_file": c["source_file"],
                            "chunk_type": c["chunk_type"],
                            "section_path": c["section_path"]
                        } for c in chunks]
                        
                        ids = components["vector_store"].add_rules(texts, metadata)
                        st.success(f"✅ {uploaded_file.name}: {len(chunks)} chunks")
            else:
                st.warning("Provide ruleset name and files")

st.markdown("---")
stats = components["vector_store"].get_stats()
st.caption(f"Vector store: {stats['total_chunks']} chunks")
