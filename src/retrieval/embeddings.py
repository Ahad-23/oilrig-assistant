"""
Embedding generation and pgvector synchronization using FastEmbed.
Uses BAAI/bge-small-en-v1.5 (384 dimensions) for local, fast vector embeddings.
"""

from typing import List, Optional
import time
import asyncpg
from fastembed import TextEmbedding

class DocumentEmbedder:
    """Manages the FastEmbed embedding model with cached instances."""

    _instance: Optional["DocumentEmbedder"] = None
    _model: Optional[TextEmbedding] = None

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.model_name = model_name
        if DocumentEmbedder._model is None:
            DocumentEmbedder._model = TextEmbedding(model_name=self.model_name)
        self.model = DocumentEmbedder._model

    @classmethod
    def get_instance(cls, model_name: str = "BAAI/bge-small-en-v1.5") -> "DocumentEmbedder":
        if cls._instance is None:
            cls._instance = DocumentEmbedder(model_name=model_name)
        return cls._instance

    def embed_texts(self, texts: List[str], batch_size: int = 64) -> List[List[float]]:
        """Generates 384-dimensional dense embeddings for a batch of text strings."""
        if not texts:
            return []
        generator = self.model.embed(texts, batch_size=batch_size)
        return [list(vector) for vector in generator]

    def embed_query(self, query: str) -> List[float]:
        """Generates embedding vector for a single search query."""
        results = self.embed_texts([query])
        return results[0] if results else []


async def populate_document_embeddings(
    conn: asyncpg.Connection,
    batch_size: int = 64,
    limit: Optional[int] = None
) -> int:
    """
    Finds document_sections with null embeddings, computes vectors, and writes them back.
    Processes records in batches to optimize memory and connection throughput.
    """
    embedder = DocumentEmbedder.get_instance()

    query = """
        SELECT section_id, section_title, content
        FROM document_sections
        WHERE embedding IS NULL
        ORDER BY section_id
    """
    if limit:
        query += f" LIMIT {limit}"

    rows = await conn.fetch(query)
    total_to_embed = len(rows)
    if total_to_embed == 0:
        return 0

    print(f"Generating embeddings for {total_to_embed} document sections...")
    start_time = time.time()
    updated_count = 0

    for i in range(0, total_to_embed, batch_size):
        batch_rows = rows[i:i + batch_size]
        # Compose descriptive string combining section title and content snippet
        texts = [
            f"{r['section_title'] or ''}\n{r['content'][:1200]}".strip()
            for r in batch_rows
        ]
        vectors = embedder.embed_texts(texts, batch_size=batch_size)

        # Batch update in a transaction
        async with conn.transaction():
            for row, vector in zip(batch_rows, vectors):
                # Format vector literal string for PostgreSQL pgvector: '[v1,v2,...]'
                vec_str = "[" + ",".join(str(round(v, 6)) for v in vector) + "]"
                await conn.execute(
                    "UPDATE document_sections SET embedding = $1::vector WHERE section_id = $2",
                    vec_str,
                    row["section_id"]
                )
        updated_count += len(batch_rows)

    elapsed = round(time.time() - start_time, 2)
    print(f"Successfully generated and stored {updated_count} embeddings in {elapsed}s.")
    return updated_count
