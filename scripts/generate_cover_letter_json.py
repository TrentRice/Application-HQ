import json
import chromadb
from sentence_transformers import SentenceTransformer

# Gemini API Key
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()  # reads .env and puts its values into os.environ

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found — check your .env file")

client = genai.Client(api_key=API_KEY)

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

db = chromadb.PersistentClient(path="./vectorstore")

collection = db.get_collection("trent_experience")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "output")
with open(os.path.join(DATA_DIR, "job_description.txt"), "r", encoding="utf-8") as f:
    job_description = f.read()

embedding = model.encode(job_description).tolist()

results = collection.query(query_embeddings=[embedding], n_results=15)

context = "\n\n".join(results["documents"][0])

prompt = f"""
Write a professional cover letter.

Use ONLY experience provided.

Job Description:

{job_description}

Experience:

{context}

Return ONLY JSON:

{{
    "intro":"",
    "body":"",
    "why_company":"",
    "closing":""
}}
"""

response = client.models.generate_content(model="gemini-flash-latest", contents=prompt)

response_text = response.text.strip()

with open(os.path.join(OUTPUT_DIR, "cover_letter.json"), "w", encoding="utf-8") as f:
    f.write(response_text)

print("Cover letter JSON created")
