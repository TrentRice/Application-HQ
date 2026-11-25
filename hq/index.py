"""Vector index over profile facts (ChromaDB + sentence-transformers).

The index rebuilds itself whenever data/profile.json changes, so there is no
manual "delete vectorstore and rerun" step.

    python -m hq.index            # rebuild now and print a sample search
    python -m hq.index "query"    # search for a query
"""

from __future__ import annotations

import sys

import chromadb

from .paths import VECTORSTORE
from .profile import Profile, load_profile

COLLECTION = "profile_facts"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
HASH_FILE = VECTORSTORE / "profile_fingerprint.txt"

_model = None


def _embedder():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBED_MODEL)
    return _model


def _db():
    return chromadb.PersistentClient(path=str(VECTORSTORE))


def build(profile: Profile) -> None:
    db = _db()
    for name in (COLLECTION, "trent_experience"):  # trent_experience = old pre-profile index
        try:
            db.delete_collection(name)
        except Exception:
            pass
    collection = db.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    pairs = profile.all_facts()
    texts = [fact.embed_text(section) for section, fact in pairs]
    embeddings = _embedder().encode(texts).tolist()
    collection.add(
        ids=[fact.id for _, fact in pairs],
        embeddings=embeddings,
        documents=texts,
        metadatas=[{"section": section.id} for section, _ in pairs],
    )
    HASH_FILE.write_text(profile.fingerprint())


def ensure_current(profile: Profile) -> None:
    current = HASH_FILE.read_text().strip() if HASH_FILE.exists() else ""
    if current != profile.fingerprint():
        build(profile)


def rank(profile: Profile, query: str) -> dict[str, float]:
    """Relevance of every fact to the query, as {fact_id: similarity 0..1}."""
    ensure_current(profile)
    collection = _db().get_collection(COLLECTION)
    embedding = _embedder().encode(query).tolist()
    n = collection.count()
    result = collection.query(query_embeddings=[embedding], n_results=n)
    return {
        fact_id: round(1 - distance, 4)
        for fact_id, distance in zip(result["ids"][0], result["distances"][0])
    }


if __name__ == "__main__":
    profile = load_profile()
    build(profile)
    print(f"Indexed {len(profile.all_facts())} facts.")
    query = " ".join(sys.argv[1:]) or "AI engineer, RAG, prompt engineering, agents"
    scores = rank(profile, query)
    print(f"\nTop matches for: {query}\n")
    for fact_id, score in sorted(scores.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {score:.3f}  {fact_id}")
