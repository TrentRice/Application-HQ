import json
import os
from docx import Document

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "output")
TEMPLATE_DIR = os.path.join(SCRIPT_DIR, "..", "templates")

with open(os.path.join(OUTPUT_DIR, "cover_letter.json"), "r", encoding="utf-8") as f:
    letter = json.load(f)

doc = Document(os.path.join(TEMPLATE_DIR, "TrentRice_CoverLetter_Template.docx"))

replacements = {
    "{{INTRO}}": letter.get("intro", ""),
    "{{BODY}}": letter.get("body", ""),
    "{{WHY_COMPANY}}": letter.get("why_company", ""),
    "{{CLOSING}}": letter.get("closing", ""),
}

for paragraph in doc.paragraphs:
    for key, value in replacements.items():
        if key in paragraph.text:
            paragraph.text = paragraph.text.replace(key, value)

doc.save(os.path.join(OUTPUT_DIR, "tailored_cover_letter.docx"))

print("Cover letter created.")
