"""RAG App - Vector Store for knowledge base."""
from datetime import datetime, timezone
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False


class VectorStore:
    """ChromaDB vector store for business rules."""
    
    def __init__(self, db_path: str | None = None):
        if not CHROMADB_AVAILABLE:
            raise ImportError("Install chromadb and sentence-transformers")
        
        self.db_path = Path(db_path or os.getenv("CHROMA_DB_PATH", "./data/chroma"))
        self._client = None
        self._collection = None
        self._embedder = None
    
    def initialize(self):
        self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
        self.db_path.mkdir(parents=True, exist_ok=True)
        
        self._client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(anonymized_telemetry=False)
        )
        self._collection = self._client.get_or_create_collection(
            name="rules",
            metadata={"hnsw:space": "cosine"}
        )
    
    def _embed(self, text: str) -> List[float]:
        return self._embedder.encode(text, convert_to_numpy=True).tolist()
    
    def _clean_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Chroma metadata values must be scalar and not None."""
        cleaned = {}
        for key, value in metadata.items():
            if value is None:
                cleaned[key] = ""
            elif isinstance(value, (str, int, float, bool)):
                cleaned[key] = value
            else:
                cleaned[key] = str(value)
        cleaned.setdefault("ingested_at", datetime.now(timezone.utc).isoformat())
        cleaned.setdefault("active", True)
        return cleaned

    def add_rules(self, texts: List[str], metadata: List[Dict]) -> List[str]:
        """Add rule chunks to store."""
        if len(texts) != len(metadata):
            raise ValueError("texts and metadata must have the same length")

        ids = [str(uuid.uuid4()) for _ in texts]
        vectors = [self._embed(text) for text in texts]
        clean_metadata = [self._clean_metadata(item) for item in metadata]
        
        self._collection.upsert(
            embeddings=vectors,
            ids=ids,
            metadatas=clean_metadata,
            documents=texts
        )
        return ids
    
    def search(
        self,
        query: str,
        domain_id: str,
        top_k: int = 8,
        active_only: bool = True,
        score_threshold: Optional[float] = None,
        ruleset_id: Optional[str] = None,
        version: Optional[str] = None,
    ) -> List[Dict]:
        """Search for relevant rules."""
        query_vector = self._embed(query)
        filters = [{"domain_id": domain_id}]
        if active_only:
            filters.append({"active": True})
        if ruleset_id:
            filters.append({"ruleset_id": ruleset_id})
        if version:
            filters.append({"version": version})
        where = filters[0] if len(filters) == 1 else {"$and": filters}
        
        results = self._collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            where=where
        )
        if active_only and (not results["ids"] or not results["ids"][0]):
            results = self._collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                where={"domain_id": domain_id}
            )
        
        matches = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                score = 1 - results["distances"][0][i]
                if score_threshold is not None and score < score_threshold:
                    continue

                matches.append({
                    "chunk_id": chunk_id,
                    "content": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "score": score
                })
        return matches

    def list_rules(
        self,
        domain_id: str,
        active_only: bool = True,
        ruleset_id: Optional[str] = None,
        version: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict]:
        """Return chunks for a domain without semantic filtering."""
        filters = [{"domain_id": domain_id}]
        if active_only:
            filters.append({"active": True})
        if ruleset_id:
            filters.append({"ruleset_id": ruleset_id})
        if version:
            filters.append({"version": version})

        where = filters[0] if len(filters) == 1 else {"$and": filters}
        results = self._collection.get(
            where=where,
            include=["documents", "metadatas"],
            limit=limit,
        )
        if active_only and not results.get("ids"):
            results = self._collection.get(
                where={"domain_id": domain_id},
                include=["documents", "metadatas"],
                limit=limit,
            )

        matches = []
        for chunk_id, content, metadata in zip(
            results.get("ids", []),
            results.get("documents", []),
            results.get("metadatas", []),
        ):
            matches.append({
                "chunk_id": chunk_id,
                "content": content,
                "metadata": metadata,
                "score": 1.0,
            })

        return sorted(
            matches,
            key=lambda item: (
                str(item["metadata"].get("source_file", "")),
                str(item["metadata"].get("section_path", "")),
            ),
        )

    def deactivate_rules(
        self,
        domain_id: str,
        ruleset_id: Optional[str] = None,
        version: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> int:
        """Mark matching chunks inactive while keeping them for traceability."""
        filters = [{"domain_id": domain_id}]
        if ruleset_id:
            filters.append({"ruleset_id": ruleset_id})
        if version:
            filters.append({"version": version})
        if document_id:
            filters.append({"document_id": document_id})

        where = filters[0] if len(filters) == 1 else {"$and": filters}
        results = self._collection.get(where=where, include=["metadatas"])
        ids = results.get("ids", [])
        metadatas = results.get("metadatas", [])
        if not ids:
            return 0

        updated_metadata = []
        deactivated_at = datetime.now(timezone.utc).isoformat()
        for item in metadatas:
            metadata = dict(item)
            metadata["active"] = False
            metadata["deactivated_at"] = deactivated_at
            updated_metadata.append(self._clean_metadata(metadata))

        self._collection.update(ids=ids, metadatas=updated_metadata)
        return len(ids)
    
    def get_stats(self) -> Dict:
        return {"total_chunks": self._collection.count() if self._collection else 0}
