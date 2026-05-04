# Business Rule AI Agent

An AI Agent system specialized for validating business documents against business rules, with citation tracking and corrected file export capabilities.

---

## Problem Statement

In enterprises, business rules are often scattered across multiple documents: policy manuals, SOPs, guidelines, and regulatory documents. When employees need to verify whether a file, contract, or form complies with these rules, they typically must:

1. Manually search through multiple documents
2. Read and cross-reference each rule
3. Easily miss important rules
4. Struggle to identify the source of each rule (citation)
5. Lack automated methods to fix errors and export corrected files

**Business Rule AI Agent** solves this problem by:
- Automatically retrieving relevant rules from the selected domain
- Comparing uploaded files against active business rules
- Clearly separating direct rules, interpretations, and evidence gaps
- Providing citations for every conclusion
- Exporting corrected files in multiple formats (JSON, CSV, Excel, PDF, etc.)

---

## System Architecture & Workflow

### Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Frontend (React)                                    │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐           │
│  │   RAG Knowledge  │  │   Review Chat    │  │     Settings     │           │
│  │      Page        │  │      Page        │  │      Page        │           │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘           │
└───────────┼────────────────────┼────────────────────┼───────────────────────┘
            │                    │                    │
            │ HTTP REST API      │ HTTP REST API      │ HTTP REST API
            │                    │                    │
┌───────────┼────────────────────┼────────────────────┼───────────────────────┐
│           ▼                    ▼                    ▼                       │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐           │
│  │  RAG API Server  │  │ Review API Server│  │  Shared Storage  │           │
│  │   (port 8601)    │  │   (port 8602)    │  │    (SQLite)     │           │
│  └────────┬─────────┘  └────────┬─────────┘  └──────────────────┘           │
│           │                    │                                            │
│  ┌────────▼─────────┐  ┌──────▼──────────┐                                  │
│  │ Vector Store     │  │ Review Service │                                  │
│  │ (ChromaDB)       │  │                 │                                  │
│  └────────┬─────────┘  └──────┬──────────┘                                  │
│           │                    │                                            │
│  ┌────────▼────────────────────▼────────────────┐                           │
│  │              LLM Provider                     │                           │
│  │         (Groq / OpenAI)                       │                           │
│  └───────────────────────────────────────────────┘ 
                          │
                          │
                          │
                          ──────▼──────────┐                                  │
│                       │ Synthesis Service │                                  │
│                       │                 │                                    │
│                       └──────┬──────────┘ 
                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Workflow 1: Knowledge Ingestion (RAG App)

```
Business rule file → RAG App → Parser → Chunks + metadata → Vector Store + Document Registry
```

1. **File Upload**: User uploads business rule documents (PDF, DOCX, CSV, etc.)
2. **Parsing**: Business Rule Parser extracts text and creates chunks
3. **Metadata Generation**: Each chunk gets metadata (source file, section, page, etc.)
4. **Embedding**: Chunks are converted to vectors using sentence-transformers
5. **Storage**: Vectors stored in ChromaDB, document metadata in SQLite
6. **Status Management**: Files marked as active/archived based on filename

### Workflow 2: Query & Review (Review App)

```
User query/file → Review App → Review Service → Retrieve/Rerank Evidence → LLM → Answer + Sources
```

1. **Input Processing**: User selects domain, uploads file (optional), asks question
2. **Query Analysis**: Parser determines intent (validation, Q&A, summary, analysis)
3. **Evidence Retrieval**: 
   - Adaptive top-k based on domain size
   - Vector search in ChromaDB for relevant chunks
   - Reranking by relevance score
4. **Context Enrichment**: Domain context added to queries for better understanding
5. **LLM Processing**: 
   - Prompt building with evidence and domain context
   - LLM generates analysis/response
   - Clean plain text output (no markdown)
6. **Result Assembly**: 
   - Confidence scoring
   - Citation generation
   - Export artifacts (if applicable)

---

## Component Architecture

### RAG App (Knowledge Management)
**rag_app/**
- `api_server.py`: HTTP API for domain management and ingestion (port 8601)
- `vector_store.py`: ChromaDB wrapper for semantic search
- `parsers/business_rule_parser.py`: Parse rule documents into chunks

### Review App (Query & Validation)
**review_app/**
- `api_server.py`: HTTP API for review operations (port 8602)
- `review_service.py`: Core validation workflow
- `orchestrator.py`: Workflow coordination (NEW)
- `synthesis.py`: Final result synthesis (NEW)
- `review_service_enhanced.py`: Enhanced service with orchestrator
- `retrieval.py`: Adaptive top-k, reranking, deduplication
- `prompts.py`: Prompt building with domain context
- `confidence.py`: Confidence scoring
- `parsers/`: Input file and query parsing
- `exports.py`: Export artifact generation

### Shared Components
**shared/**
- `storage.py`: SQLite persistence (domains, documents, settings)
- `llm.py`: LLM factory (Groq, OpenAI)
- `config.py`: Configuration management
- `simple_http.py`: HTTP helpers

### Frontend
**frontend/**
- React + Vite + TailwindCSS v4
- Pages: RAG Knowledge, Review Chat, Settings

---

## Key Features

1. **Adaptive Top-K**: Automatically adjusts retrieval count based on domain size
2. **Domain Context Awareness**: Understands domain references in queries
3. **Clean Output**: Plain text responses without markdown formatting
4. **Citation Tracking**: Every conclusion has source citations
5. **Confidence Scoring**: Reliability assessment based on evidence
6. **Orchestrator Pattern**: Clean workflow management
7. **Multiple Export Formats**: JSON, CSV, Excel, PDF, etc.
8. **Chat-like Interface**: Enter to send, Shift+Enter for newline

---

## How to Run

### 1. Install Dependencies

```bash
# Python dependencies
pip install -r requirements.txt

# Frontend dependencies
cd frontend
npm install
```

### 2. Configure API Key

Set at least one API key in environment variables:

```powershell
# Windows PowerShell
$env:GROQ_API_KEY="your-groq-api-key"
# Or
$env:OPENAI_API_KEY="your-openai-api-key"
```

Or configure in Settings page after startup.

### 3. Start Services

**Option 1: Run all at once (Windows)**

```powershell
.\scripts\start_all.ps1
```

**Option 2: Run each service separately**

```bash
# Terminal 1: RAG API
python -m rag_app.api_server --port 8601

# Terminal 2: Review API
python -m review_app.api_server --port 8602

# Terminal 3: Frontend
cd frontend
npm run dev
```

### 4. Access the Application

Open browser at:
- `http://localhost:3000/rag` - Manage domains and ingest rule files
- `http://localhost:3000/review` - Chat interface for validation
- `http://localhost:3000/settings` - Configure provider/model/API key

### 5. Usage Workflow

**Step 1: Ingest Knowledge (RAG App)**
1. Go to RAG Knowledge page
2. Create a new domain (e.g., "test3")
3. Upload business rule documents
4. Wait for ingestion completion
5. Check file statuses (active/archived)

**Step 2: Query & Review (Review App)**
1. Go to Review page
2. Select domain
3. Upload file (optional) or ask direct question
4. Examples:
   - "What business rules are in this domain?"
   - "Is this file compliant with rules?"
   - "Check field validity"
5. View results with citations and confidence

---

## Supported File Formats

**Knowledge Ingestion (RAG):**
- PDF, DOCX, TXT, MD, CSV, JSON

**Review Uploads:**
- PDF, DOCX, TXT, MD, CSV, JSON, XLSX, XLS, PNG, JPG, JPEG, WEBP, GIF, BMP, SVG, AVIF, TIF, TIFF

**Export Formats:**
- JSON, TXT, CSV, XLSX, MD, DOCX, PDF

---

## Important Notes

- Files with "ARCHIVED" or "DEPRECATED" in filename are auto-archived
- "This file" in Review refers only to current chat uploads
- Agent uses only evidence from selected domain
- 100% confidence for simple rule listing queries
- Adaptive top-k ensures comprehensive evidence retrieval
- Clean plain text output for better readability
