from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"
TEMPLATES = ROOT / "templates"
VECTORSTORE = ROOT / "vectorstore"

PROFILE = DATA / "profile.json"
JOB_DESCRIPTION = DATA / "job_description.txt"

RESUME_TEMPLATE = TEMPLATES / "resume_template.docx"
COVER_TEMPLATE = TEMPLATES / "TrentRice_CoverLetter_Template.docx"

RESUME_DOCX = OUTPUT / "tailored_resume.docx"
RESUME_JSON = OUTPUT / "resume.json"
RESUME_REPORT = OUTPUT / "resume_report.json"
COVER_DOCX = OUTPUT / "tailored_cover_letter.docx"
COVER_JSON = OUTPUT / "cover_letter.json"
