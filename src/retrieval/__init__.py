"""
Retrieval and vector search module for the Asset Intelligence Copilot.
Provides embedding generation, semantic vector indexing, and hybrid search.
"""

from src.retrieval.embeddings import DocumentEmbedder, populate_document_embeddings
from src.retrieval.hybrid_search import search_documents

__all__ = [
    "DocumentEmbedder",
    "populate_document_embeddings",
    "search_documents",
]
