import json
import chromadb
from sentence_transformers import SentenceTransformer

# Load embedding model
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

# Create persistent database
client = chromadb.PersistentClient(path="./vectorstore")

collection = client.get_or_create_collection(name="trent_experience")

import os

path = "./data/experience.json"

print("Current directory:")
print(os.getcwd())

print("\nFile exists:")
print(os.path.exists(path))

with open(path, "r", encoding="utf-8") as f:
    raw = f.read()

print("\nLength:")
print(len(raw))

print("\nFirst 200 chars:")
print(repr(raw[:200]))

# Parse JSON
data = json.loads(raw)

# Add chunks
for chunk in data["experience_chunks"]:
    text = f"""
    Company: {chunk.get("company", "")}
    Project: {chunk.get("project", "")}
    Description: {chunk.get("description", "")}
    Skills: {" ".join(chunk.get("skills", []))}
    Keywords: {" ".join(chunk.get("keywords", []))}
    Outcomes: {" ".join(chunk.get("outcomes", []))}
    """

    embedding = model.encode(text).tolist()

    collection.add(
        ids=[chunk["id"]],
        embeddings=[embedding],
        documents=[text],
        metadatas=[
            {"company": chunk.get("company", ""), "project": chunk.get("project", "")}
        ],
    )

print("Vector database created successfully.")
