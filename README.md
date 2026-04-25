# Business Rule AI Platform

Streamlit prototype for building a business-rule knowledge base and reviewing
input files or user questions against those rules.

## Architecture

```text
business_rule_ai/
|-- rag_app/                         # Knowledge-base builder, port 8501
|   |-- parsers/
|   |   `-- business_rule_parser.py  # Parse policy/rule documents
|   |-- vector_store.py              # ChromaDB wrapper
|   `-- main.py                      # Streamlit app
|-- review_app/                      # Runtime review app, port 8502
|   |-- parsers/
|   |   |-- input_file_parser.py     # Review upload parser
|   |   `-- query_parser.py          # Intent/entity parsing
|   |-- orchestrator.py              # Query workflow coordinator
|   |-- review_service.py            # Testable review workflow
|   |-- synthesis.py                 # Final answer synthesis
|   |-- workflow.py                  # Optional LangGraph wrapper
|   `-- main.py                      # Streamlit app
|-- shared/
|   |-- config.py                    # Provider/model/env config
|   |-- llm.py                       # LLM provider factory
|   |-- models.py                    # Shared Pydantic models
|   |-- retrieval.py                 # Retrieval planning, reranking, dedupe
|   |-- review_prompts.py            # Validation prompts and taxonomy
|   `-- storage.py                   # SQLite persistence
`-- data/                            # Local runtime data, not for git
```

## Workflow

```text
Business rule file -> RAG App -> Parser -> Chunks + metadata -> Vector Store + document registry
User query/file    -> Review App -> review_service -> retrieve/rerank evidence -> LLM answer + sources
```

The Review App can run through `review_app.workflow.run_review_workflow`. If
LangGraph is installed, that wrapper uses a small graph. If LangGraph is not
available, it falls back to the same tested service function.

Supported business-rule upload formats:

```text
pdf, docx, txt, md, csv, json
```

Supported review input formats:

```text
pdf, docx, txt, md, csv, json
```

## Quick Start

```bash
pip install -r requirements.txt

# Prefer environment variables for API keys.
export GROQ_API_KEY="your-key"
# or
export OPENAI_API_KEY="your-key"

# Terminal 1 - build knowledge
streamlit run rag_app/main.py --server.port 8501

# Terminal 2 - query and validate
streamlit run review_app/main.py --server.port 8502
```

On Windows PowerShell:

```powershell
$env:GROQ_API_KEY="your-key"
streamlit run rag_app/main.py --server.port 8501
```

## Configuration

Provider and model preferences can be saved from the Streamlit sidebar. API keys
are intentionally not saved to SQLite. Use environment variables for corporate
or shared deployments:

```text
GROQ_API_KEY
OPENAI_API_KEY
APP_DB_PATH       optional, defaults to ./data/app.db
CHROMA_DB_PATH    optional, defaults to ./data/chroma
```

Copy `.env.example` for local development notes, but do not commit real keys.

## Development

```bash
pip install -e ".[dev]"
python -m compileall rag_app review_app shared
pytest
ruff check .
```

The first tests focus on:

```text
retrieval planning and reranking
evidence deduplication
business-rule JSON/table parsing
validation prompt grounding requirements
review service workflow
```

## Validation Behavior

Validation prompts require the model to distinguish:

```text
missing_input
invalid_or_unsupported_input
evidence_gap
hard_restriction
approval_path
rule_violation
conditional_resolution
```

The prompt also asks for evidence-strength labels:

```text
direct_rule
derived_from_rule
evidence_gap
```

## Docker

The Dockerfile defaults to the Review App on port 8502:

```bash
docker build -t business-rule-ai .
docker run --rm -p 8502:8502 -e GROQ_API_KEY="your-key" business-rule-ai
```

To run the RAG App in the same image:

```bash
docker run --rm -p 8501:8501 -e GROQ_API_KEY="your-key" business-rule-ai \
  streamlit run rag_app/main.py --server.address=0.0.0.0 --server.port=8501
```
