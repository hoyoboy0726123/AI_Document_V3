from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, List, Tuple

import faiss
import numpy as np

from ..core.config import settings

_INDEX_LOCK = threading.Lock()
_INDEX: faiss.Index | None = None
_INDEX_DIMENSION: int | None = None
_INDEX_PATH = Path(settings.FAISS_INDEX_PATH)
_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)


def _ensure_index(dimension: int) -> faiss.Index:
    global _INDEX, _INDEX_DIMENSION
    if _INDEX is not None:
        return _INDEX

    if _INDEX_PATH.exists():
        _INDEX = faiss.read_index(str(_INDEX_PATH))
        _INDEX_DIMENSION = _INDEX.d
        return _INDEX

    index_flat = faiss.IndexFlatIP(dimension)
    _INDEX = faiss.IndexIDMap2(index_flat)
    _INDEX_DIMENSION = dimension
    return _INDEX


def add_embeddings(embeddings: Dict[int, List[float]]) -> None:
    if not embeddings:
        return

    ids = np.array(list(embeddings.keys()), dtype="int64")
    vectors = np.array(list(embeddings.values()), dtype="float32")
    dimension = vectors.shape[1]

    with _INDEX_LOCK:
        index = _ensure_index(dimension)
        index.add_with_ids(vectors, ids)
        faiss.write_index(index, str(_INDEX_PATH))


def remove_embeddings(faiss_ids: List[int]) -> None:
    if not faiss_ids:
        return

    with _INDEX_LOCK:
        global _INDEX, _INDEX_DIMENSION
        if _INDEX is None:
            if not _INDEX_PATH.exists():
                return
            _INDEX = faiss.read_index(str(_INDEX_PATH))
            _INDEX_DIMENSION = _INDEX.d
        id_array = np.array(faiss_ids, dtype="int64")
        _INDEX.remove_ids(id_array)
        faiss.write_index(_INDEX, str(_INDEX_PATH))


def search(embedding: List[float], top_k: int = 5) -> List[Tuple[int, float]]:
    if not embedding:
        return []

    vector = np.array([embedding], dtype="float32")

    with _INDEX_LOCK:
        global _INDEX, _INDEX_DIMENSION
        if _INDEX is None:
            if not _INDEX_PATH.exists():
                return []
            _INDEX = faiss.read_index(str(_INDEX_PATH))
            _INDEX_DIMENSION = _INDEX.d
        index = _INDEX

        if index.ntotal == 0:
            return []

        if index.d != vector.shape[1]:
            raise ValueError(
                f"Embedding dimension mismatch: index expects {index.d} dimensions, "
                f"but got {vector.shape[1]} dimensions"
            )

        scores, ids = index.search(vector, top_k)

    results: List[Tuple[int, float]] = []
    for chunk_id, score in zip(ids[0], scores[0]):
        if int(chunk_id) == -1:
            continue
        results.append((int(chunk_id), float(score)))
    return results
