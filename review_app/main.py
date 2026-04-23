"""Review App - Main Entry Point (Port 8502).

Uses its own input file parser (separate from RAG).
Connects to RAG's vector store for evidence retrieval.
"""
import streamlit as st
import sys
import uuid
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.storage import list_domains, get_provider_config, save_provider_config
from shared.llm import LLMFactory
from rag_app.vector_store import VectorStore
from review_app.parsers.input_file_parser import UserInputFileParser

st.set_page_config(page_title="Review App", page_icon="⚡", layout="wide")
st.title("⚡ Review App")
st.caption("Uses RAG Vector Store + Own Input File Parser")

# Initialize vector store (shared with RAG)
@st.cache_resource
def get_vector_store():
    store = VectorStore()
    store.initialize()
    return store

vector_store = get_vector_store()

# Sidebar
st.sidebar.title("⚡ Review App")
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
# Default to llama-3.3-70b-versatile for groq (decommissioned llama-3.1-70b-versatile)
default_model = "llama-3.3-70b-versatile" if provider == "groq" else "gpt-4o-mini"
if saved_config:
    saved_model = saved_config.get("model", default_model)
    # If saved model is the old decommissioned one, use new default
    if saved_model == "llama-3.1-70b-versatile" and provider == "groq":
        default_model = "llama-3.3-70b-versatile"
    else:
        default_model = saved_model

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
st.sidebar.caption("Port: 8502 | Query business rules here")

# Check API key
if not api_key:
    st.error("⚠️ Please configure API key")
    st.stop()

# Initialize components
llm = LLMFactory.create(provider, api_key, model)
file_parser = UserInputFileParser()  # Review App's own parser

# Main interface
domains = list_domains()
if not domains:
    st.warning("⚠️ No domains found. Use RAG App (port 8501) to create domains first.")
    st.stop()

col1, col2 = st.columns([1, 2])

with col1:
    st.header("Query Configuration")
    
    domain_options = {d['name']: d['domain_id'] for d in domains}
    selected_domain = st.selectbox("Domain", list(domain_options.keys()))
    domain_id = domain_options[selected_domain]
    
    query = st.text_area("Your Query", height=100,
        placeholder="e.g., Validate this invoice against approval rules")
    
    # Review App's own input file parser
    st.subheader("Input File (Optional)")
    input_file = st.file_uploader("Upload file to validate", type=["pdf", "docx", "txt"])
    
    parsed_file = None
    if input_file:
        with st.spinner("Parsing with Review App's parser..."):
            upload_dir = Path("./data/review_uploads")
            upload_dir.mkdir(parents=True, exist_ok=True)
            file_path = upload_dir / f"{uuid.uuid4()}_{input_file.name}"
            
            with open(file_path, "wb") as f:
                f.write(input_file.getbuffer())
            
            parsed_file = asyncio.run(file_parser.parse(file_path))
            st.success(f"✅ Parsed: {parsed_file['file_name']}")
    
    if st.button("▶️ Run Review", type="primary"):
        if not query:
            st.warning("Please enter a query")
        else:
            with st.spinner("Processing..."):
                try:
                    # Step 1: Retrieve evidence from RAG's vector store
                    matches = vector_store.search(query, domain_id, top_k=8)
                    
                    evidence_text = "\n\n---\n\n".join([
                        f"[Source: {m['metadata'].get('source_file', 'unknown')}]\n{m['content']}"
                        for m in matches
                    ])
                    
                    # Step 2: Analyze
                    if parsed_file:
                        system = "You are a validator. Check input against rules."
                        user = f"Rules:\n{evidence_text}\n\n---\n\nInput:\n{parsed_file['content']}\n\nQuery: {query}"
                    else:
                        system = "You are a business rule expert. Answer based on rules."
                        user = f"Rules:\n{evidence_text}\n\n---\n\nQuery: {query}"
                    
                    messages = llm.format_messages(system, user)
                    response = asyncio.run(llm.complete(messages, temperature=0.1))
                    
                    # Store result
                    st.session_state["review_result"] = {
                        "query": query,
                        "evidence_count": len(matches),
                        "parsed_file": parsed_file,
                        "answer": response.content
                    }
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

with col2:
    st.header("Results")
    
    if "review_result" in st.session_state:
        result = st.session_state["review_result"]
        
        st.markdown("### Answer")
        st.markdown(result["answer"])
        
        st.markdown("---")
        st.caption(f"Evidence: {result['evidence_count']} chunks")
        
        if result["parsed_file"]:
            st.markdown(f"**Parsed File:** {result['parsed_file']['file_name']}")
            with st.expander("View parsed content"):
                st.text(result["parsed_file"]['content'][:500] + "...")
    else:
        st.info("Configure query and click 'Run Review'")

st.markdown("---")
stats = vector_store.get_stats()
st.caption(f"Connected to RAG Vector Store: {stats['total_chunks']} chunks")
