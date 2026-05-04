"""RAG App - Vector Store for knowledge base."""
from datetime import datetime, timezone
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

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
        
        try:
            self._collection = self._client.get_collection(
                name="rules",
            )
        except Exception:
            self._collection = self._client.create_collection(
                name="rules",
                metadata={"hnsw:space": "cosine"}
            )
    
    def _embed(self, text: str) -> List[float]:
        return self._embedder.encode(text, convert_to_numpy=True).tolist()

    def _embed_many(self, texts: List[str]) -> List[List[float]]:
        return self._embedder.encode(
            texts,
            convert_to_numpy=True,
            batch_size=32,
            show_progress_bar=False,
        ).tolist()
    
    def _clean_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Clean new-ingest metadata and add audit defaults."""
        cleaned = self._scrub_metadata(metadata)
        cleaned.setdefault("ingested_at", datetime.now(timezone.utc).isoformat())
        cleaned.setdefault("active", True)
        return cleaned

    def _scrub_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Chroma metadata values must be scalar and not None."""
        cleaned = {}
        for key, value in metadata.items():
            if value is None:
                cleaned[key] = ""
            elif isinstance(value, (str, int, float, bool)):
                cleaned[key] = value
            else:
                cleaned[key] = str(value)
        return cleaned

    def add_rules(self, texts: List[str], metadata: List[Dict]) -> List[str]:
        """Add rule chunks to store."""
        if len(texts) != len(metadata):
            raise ValueError("texts and metadata must have the same length")
        if not texts:
            return []

        ids = [str(uuid.uuid4()) for _ in texts]
        vectors = self._embed_many(texts)
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
        if self._collection is None:
            raise ValueError("Vector store not initialized. Call initialize() first.")
        
        # Check if collection has any data
        try:
            count = self._collection.count()
            if count == 0:
                return []
        except Exception:
            pass  # Continue with the query
        
        query_vector = self._embed(query)
        filters = [{"domain_id": domain_id}]
        if active_only:
            filters.append({"active": True})
        if ruleset_id:
            filters.append({"ruleset_id": ruleset_id})
        if version:
            filters.append({"version": version})
        where = filters[0] if len(filters) == 1 else {"$and": filters}
        
        try:
            results = self._collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                where=where
            )
        except Exception as e:
            # If where filter fails, try without it and filter manually
            try:
                all_results = self._collection.query(
                    query_embeddings=[query_vector],
                    n_results=top_k * 2,  # Get more to filter down
                )
                # Manual filtering
                filtered_ids = []
                filtered_docs = []
                filtered_metas = []
                filtered_dists = []
                
                for i, chunk_id in enumerate(all_results["ids"][0]):
                    metadata = all_results["metadatas"][0][i]
                    if metadata.get("domain_id") != domain_id:
                        continue
                    if active_only and not metadata.get("active", True):
                        continue
                    if ruleset_id and metadata.get("ruleset_id") != ruleset_id:
                        continue
                    if version and metadata.get("version") != version:
                        continue
                    filtered_ids.append(chunk_id)
                    filtered_docs.append(all_results["documents"][0][i])
                    filtered_metas.append(metadata)
                    filtered_dists.append(all_results["distances"][0][i])
                
                results = {
                    "ids": [filtered_ids[:top_k]],
                    "documents": [filtered_docs[:top_k]],
                    "metadatas": [filtered_metas[:top_k]],
                    "distances": [filtered_dists[:top_k]]
                }
            except Exception as e2:
                raise ValueError(f"ChromaDB query error for domain '{domain_id}': {str(e2)}")
        
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
        if self._collection is None:
            raise ValueError("Vector store not initialized. Call initialize() first.")
        
        # First, check if collection has any data
        try:
            count = self._collection.count()
            if count == 0:
                return []
        except Exception:
            pass  # Continue with the query
        
        # Try with where filter first
        filters = [{"domain_id": domain_id}]
        if active_only:
            filters.append({"active": True})
        if ruleset_id:
            filters.append({"ruleset_id": ruleset_id})
        if version:
            filters.append({"version": version})

        where = filters[0] if len(filters) == 1 else {"$and": filters}
        get_kwargs = {
            "where": where,
            "include": ["documents", "metadatas"],
        }
        if limit is not None:
            get_kwargs["limit"] = limit
        
        try:
            results = self._collection.get(**get_kwargs)
        except Exception as e:
            # If where filter fails, try without it and filter manually
            try:
                results = self._collection.get(include=["documents", "metadatas"])
            except Exception as e2:
                raise ValueError(f"ChromaDB get error for domain '{domain_id}': {str(e2)}")

        matches = []
        for chunk_id, content, metadata in zip(
            results.get("ids", []),
            results.get("documents", []),
            results.get("metadatas", []),
        ):
            # Manual filtering if where clause failed
            if metadata.get("domain_id") != domain_id:
                continue
            if active_only and not metadata.get("active", True):
                continue
            if ruleset_id and metadata.get("ruleset_id") != ruleset_id:
                continue
            if version and metadata.get("version") != version:
                continue
            
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
        exclude_ids: Optional[Set[str]] = None,
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

        excluded = exclude_ids or set()
        updated_metadata = []
        ids_to_update = []
        deactivated_at = datetime.now(timezone.utc).isoformat()
        for chunk_id, item in zip(ids, metadatas):
            if chunk_id in excluded:
                continue
            metadata = dict(item)
            metadata["active"] = False
            metadata["deactivated_at"] = deactivated_at
            ids_to_update.append(chunk_id)
            updated_metadata.append(self._scrub_metadata(metadata))

        if not ids_to_update:
            return 0

        self._collection.update(ids=ids_to_update, metadatas=updated_metadata)
        return len(ids_to_update)

    def set_rules_active(
        self,
        domain_id: str,
        document_id: str,
        active: bool,
    ) -> int:
        """Set active status for a specific document's chunks."""
        results = self._collection.get(
            where={"$and": [{"domain_id": domain_id}, {"document_id": document_id}]},
            include=["metadatas"],
        )
        ids = results.get("ids", [])
        metadatas = results.get("metadatas", [])
        if not ids:
            return 0

        updated_metadata = []
        timestamp = datetime.now(timezone.utc).isoformat()
        for item in metadatas:
            metadata = dict(item)
            metadata["active"] = active
            metadata["status"] = "active" if active else "archived"
            if active:
                metadata["reactivated_at"] = timestamp
            else:
                metadata["deactivated_at"] = timestamp
            updated_metadata.append(self._scrub_metadata(metadata))

        self._collection.update(ids=ids, metadatas=updated_metadata)
        return len(ids)
    
    def get_stats(self) -> Dict:
        return {"total_chunks": self._collection.count() if self._collection else 0}
