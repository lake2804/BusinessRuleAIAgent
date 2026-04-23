# Business Rule AI Platform

## Architecture

Based on your 3rd drawing (whiteboard):

```
┌─────────────────────────────────────────────────────────────────┐
│                    RAG App (Port 8501)                          │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  4 COMPONENTS                           │   │
│  │                                                         │   │
│  │  1. User Query Parser     → Parse Query                 │   │
│  │  2. User Input File Parser→ Parse Input File            │   │
│  │  3. Orchestrator          → Coordinate + Retrieve       │   │
│  │  4. Final Synthesis       → Combine → Final Output      │   │
│  │                                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↑                                  │
│  ┌───────────────────────────┴─────────────────────────────┐   │
│  │       Business Rule File Parser (Build Knowledge)       │   │
│  │                  ↓                                      │   │
│  │         Vector Store (ChromaDB)                         │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Shared SQLite + ChromaDB
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Review App (Port 8502)                        │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │         User Input File Parser (Review's own)           │   │
│  │                      ↓                                  │   │
│  │         Query → Retrieve from RAG Vector Store          │   │
│  │                      ↓                                  │   │
│  │                   Generate Answer                       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
business_rule_ai/
├── rag_app/                          # RAG System (Port 8501)
│   ├── parsers/
│   │   ├── query_parser.py          # Component 1: User Query Parser
│   │   ├── input_file_parser.py     # Component 2: User Input File Parser
│   │   └── business_rule_parser.py  # Build Knowledge (separate!)
│   ├── vector_store.py              # ChromaDB storage
│   ├── orchestrator.py              # Component 3: Orchestrator
│   ├── synthesis.py                 # Component 4: Final Synthesis
│   └── main.py                      # Streamlit UI
│
├── review_app/                       # Review System (Port 8502)
│   ├── parsers/
│   │   └── input_file_parser.py     # OWN parser (separate from RAG!)
│   └── main.py                      # Streamlit UI
│
├── shared/                           # Shared components
│   ├── storage.py                   # SQLite persistence
│   ├── models.py                    # Pydantic models
│   └── llm.py                       # LLM factory
│
└── data/                            # Storage
    ├── app.db                       # SQLite
    ├── chroma/                      # Vector DB
    ├── uploads/                     # Business rules
    └── user_uploads/                # User input files
```

## Key Separation

| Component | Location | Purpose |
|-----------|----------|---------|
| **Business Rule Parser** | `rag_app/parsers/business_rule_parser.py` | Parses business rule PDFs/DOCXs to build knowledge |
| **User Query Parser** | `rag_app/parsers/query_parser.py` | Parses user queries (intent detection) |
| **User Input File Parser (RAG)** | `rag_app/parsers/input_file_parser.py` | Parses user files in RAG app |
| **User Input File Parser (Review)** | `review_app/parsers/input_file_parser.py` | **SEPARATE** parser for Review app |

## Installation

```bash
pip install -r requirements.txt
```

## Running

### Terminal 1: RAG App
```bash
streamlit run rag_app/main.py --server.port 8501
```

### Terminal 2: Review App
```bash
streamlit run review_app/main.py --server.port 8502
```

## Usage Flow

### RAG App (Port 8501)

1. **Configure API Key** in sidebar → Save
2. **Build Knowledge:**
   - Create domain
   - Upload business rule files (PDF/DOCX)
   - Files parsed by `business_rule_parser.py`
   - Stored in ChromaDB
3. **Query with 4 Components:**
   - Enter query → **Query Parser** detects intent
   - Upload file (optional) → **Input File Parser** extracts content
   - **Orchestrator** retrieves evidence + analyzes
   - **Final Synthesis** generates polished output

### Review App (Port 8502)

1. Configure same API key
2. Select domain (from RAG)
3. Enter query
4. Upload input file → uses **OWN parser** (`review_app/parsers/`)
5. Retrieve evidence from RAG's vector store
6. Generate answer

## Data Flow

**Building Knowledge:**
```
Business Rule PDF → Business Rule Parser → Chunks → Vector Store
```

**RAG Query (4 Components):**
```
User Query → Query Parser → Orchestrator → Final Synthesis → Output
User File  → Input File Parser ──┘              ↑
Vector Store Evidence ←─────────────────────────┘
```

**Review Query:**
```
User Query ────────────────────────────┐
User File → Review's Input File Parser → Retrieve from RAG Vector Store → Answer
```

## Code Files by Role

### RAG App - 4 Components

| File | Component | Role |
|------|-----------|------|
| `parsers/query_parser.py` | 1 | Detects intent: Q&A / Validation / Analysis |
| `parsers/input_file_parser.py` | 2 | Parses user files (PDF/DOCX/TXT) |
| `orchestrator.py` | 3 | Coordinates workflow, retrieves evidence |
| `synthesis.py` | 4 | Combines results into final output |

### Plus: Knowledge Building

| File | Role |
|------|------|
| `parsers/business_rule_parser.py` | Parses business rules to build knowledge base |
| `vector_store.py` | ChromaDB for embeddings |

### Review App

| File | Role |
|------|------|
| `parsers/input_file_parser.py` | **Separate** parser for user files |
| `main.py` | UI + retrieval + answer generation |
