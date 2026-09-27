import chromadb
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

client = chromadb.PersistentClient(path="./vectorstore")

collection = client.get_collection(name="trent_experience")

print("Records in DB:")
print(collection.count())

query = """
AI Engineer

RAG
Prompt Engineering
AI Agents
"""

embedding = model.encode(query).tolist()

results = collection.query(query_embeddings=[embedding], n_results=5)

print("\nResults:\n")

for doc, meta, dist in zip(
    results["documents"][0], results["metadatas"][0], results["distances"][0]
):
    print("=" * 60)
    print(f"[{meta['company']} — {meta['project']}] (distance: {dist:.4f})")
    print(doc)
