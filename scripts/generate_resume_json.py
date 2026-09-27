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

# Vector Search
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

db = chromadb.PersistentClient(path="./vectorstore")

collection = db.get_collection("trent_experience")

# Read Job Description

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")

with open(os.path.join(DATA_DIR, "job_description.txt"), "r", encoding="utf-8") as f:
    job_description = f.read()

# Search Experience
embedding = model.encode(job_description).tolist()

results = collection.query(query_embeddings=[embedding], n_results=20)

context = "\n\n".join(results["documents"][0])

prompt = f"""
You are an expert resume writer.

Create JSON only.

Do not return markdown.

Do not return explanations.

Only return valid JSON.

The candidate's experience is:

{context}

Job Description:

{job_description}

Return:

{{
  "summary": "",

  "jdi_experience": "",

  "imp_experience": "",

  "tissue_experience": "",

  "nshealth_experience": "",

  "shipbuilding_experience": "",

  "programming_skills": "",
  
  "data_science_skills": "",
  
  "communication_skills": ""
}}

Rules:

- Use only provided experience.
- Never invent accomplishments.
- Tailor for ATS.
- Max 4 bullets per employer.
- Start bullets with action verbs.
- Keep resume professional.
"""

response = client.models.generate_content(model="gemini-flash-latest", contents=prompt)

response_text = response.text.strip()

with open("./output/resume.json", "w", encoding="utf-8") as f:
    f.write(response_text)

print("Resume JSON created.")
