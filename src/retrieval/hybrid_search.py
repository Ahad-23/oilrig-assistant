"""
Hybrid semantic and metadata search engine for the Asset Intelligence Copilot.
Combines pgvector cosine similarity ranking with relational filters (asset_id, doc_type).
"""

from typing import List, Dict, Any, Optional
import asyncpg
from src.retrieval.embeddings import DocumentEmbedder

async def search_documents(
    conn: asyncpg.Connection,
    query: str,
    asset_id: Optional[str] = None,
    doc_type: Optional[str] = None,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Executes a hybrid search querying PostgreSQL document_sections.
    Calculates cosine similarity: 1 - (embedding <=> query_vector).
    Applies optional metadata filters for asset_id and doc_type.
    """
    embedder = DocumentEmbedder.get_instance()
    query_vector = embedder.embed_query(query)
    if not query_vector:
        return []

    vec_str = "[" + ",".join(str(round(v, 6)) for v in query_vector) + "]"

    conditions = ["embedding IS NOT NULL"]
    params: List[Any] = [vec_str]
    param_idx = 2

    if asset_id is not None:
        conditions.append(f"(asset_id = ${param_idx} OR asset_id IS NULL)")
        params.append(asset_id)
        param_idx += 1

    if doc_type is not None:
        conditions.append(f"doc_type = ${param_idx}")
        params.append(doc_type)
        param_idx += 1

    params.append(limit)
    limit_param = f"${param_idx}"

    where_clause = " AND ".join(conditions)

    sql = f"""
        SELECT 
            section_id,
            doc_type,
            doc_path,
            asset_id,
            section_title,
            content,
            metadata,
            ROUND((1 - (embedding <=> $1::vector))::numeric, 4)::float AS similarity
        FROM document_sections
        WHERE {where_clause}
        ORDER BY embedding <=> $1::vector ASC
        LIMIT {limit_param};
    """

    rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]
