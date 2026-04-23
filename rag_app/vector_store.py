"""RAG App - Vector Store for knowledge base."""
import uuid
from typing import Dict, List
from pathlib import Path

try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False


class VectorStore:
    """ChromaDB vector store for business rules."""
    
    def __init__(self, db_path: str = "./data/chroma"):
        if not CHROMADB_AVAILABLE:
            raise ImportError("Install chromadb and sentence-transformers")
        
        self.db_path = Path(db_path)
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
    
    def add_rules(self, texts: List[str], metadata: List[Dict]) -> List[str]:
        """Add rule chunks to store."""
        ids = [str(uuid.uuid4()) for _ in texts]
        vectors = [self._embed(text) for text in texts]
        
        self._collection.add(
            embeddings=vectors,
            ids=ids,
            metadatas=metadata,
            documents=texts
        )
        return ids
    
    def search(self, query: str, domain_id: str, top_k: int = 8) -> List[Dict]:
        """Search for relevant rules."""
        query_vector = self._embed(query)
        
        results = self._collection.query(
            query_embeddings=[query_vector],
            n_results=top_k,
            where={"domain_id": domain_id}
        )
        
        matches = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                matches.append({
                    "chunk_id": chunk_id,
                    "content": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "score": 1 - results["distances"][0][i]
                })
        return matches
    
    def get_stats(self) -> Dict:
        return {"total_chunks": self._collection.count() if self._collection else 0}
