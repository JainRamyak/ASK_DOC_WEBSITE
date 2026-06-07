import chromadb
from chromadb.config import Settings

class ChromaStore:
    def __init__(self, persist_dir: str = "outputs/chroma"):
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False)
        )

    def get_or_create_collection(self, session_id: str):
        # Each session gets its own collection — total isolation
        return self.client.get_or_create_collection(
            name=f"session_{session_id}",
            metadata={"hnsw:space": "cosine"}
        )

    def add(self, session_id: str, chunks: list, embeddings: list, metadatas: list):
        collection = self.get_or_create_collection(session_id)
        ids = [f"{session_id}_{i}" for i in range(len(chunks))]
        collection.add(
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )

    def query(self, session_id: str, query_embedding: list, top_k: int = 5):
        collection = self.get_or_create_collection(session_id)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )
        return results

    def delete_session(self, session_id: str):
        try:
            self.client.delete_collection(f"session_{session_id}")
        except Exception:
            pass