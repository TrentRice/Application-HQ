"""
Application-HQ front end.

Place this file in the repo root (Application-HQ/app.py) and run:
    streamlit run app.py

It saves the pasted job description to data/job_description.txt, runs your
existing generation scripts in order, then shows/download any files they produced.
"""

import subprocess
import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
JD_PATH = ROOT / "data" / "job_description.txt"

# ---- CONFIG: edit these to match your project -------------------------------
# Scripts run in this order, from the repo root, using the current venv's Python.
# Add your template-rendering script(s) (JSON -> .docx/.pdf) after the two below.
STEPS = [
    ("Generating resume content", "scripts/generate_resume_json.py"),
    ("Generating cover letter content", "scripts/generate_cover_letter_json.py"),
    ("Building resume document", "scripts/fill_template.py"),
    ("Building cover letter document", "scripts/fill_cover_template.py"),
]

# Folders where your scripts write results. Any file created/updated during a
# run and matching these extensions is shown with a download button.
OUTPUT_DIRS = [ROOT / "reports", ROOT / "output"]
SHOW_EXTENSIONS = {".docx"}
# ------------------------------------------------------------------------------

MIME = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".json": "application/json",
    ".md": "text/markdown",
    ".txt": "text/plain",
}


def run_step(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, script],
        cwd=ROOT,  # your scripts use ./vectorstore etc., so run from repo root
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def new_outputs(since: float) -> list[Path]:
    found = []
    for folder in OUTPUT_DIRS:
        if folder.exists():
            for p in folder.rglob("*"):
                if (
                    p.is_file()
                    and p.suffix.lower() in SHOW_EXTENSIONS
                    and p.stat().st_mtime >= since
                ):
                    found.append(p)
    return sorted(found)


st.set_page_config(page_title="Application HQ", page_icon="📄", layout="centered")
st.title("📄 Application HQ")
st.caption("Paste a job description to generate a tailored resume and cover letter.")

job_description = st.text_area(
    "Job description",
    height=350,
    placeholder="Paste the full job posting here...",
)

if st.button("Generate", type="primary", disabled=not job_description.strip()):
    JD_PATH.parent.mkdir(parents=True, exist_ok=True)
    JD_PATH.write_text(job_description.strip(), encoding="utf-8")

    started = time.time()
    failed = False

    with st.status("Working...", expanded=True) as status:
        for label, script in STEPS:
            st.write(f"⏳ {label}...")
            result = run_step(script)
            if result.returncode != 0:
                st.write(f"❌ {label} failed")
                st.code(result.stderr[-3000:] or result.stdout[-3000:], language="text")
                status.update(label="Failed", state="error")
                failed = True
                break
            st.write(f"✅ {label}")
        if not failed:
            status.update(label="Done", state="complete", expanded=False)

    if not failed:
        files = new_outputs(started)
        if not files:
            st.warning(
                "Scripts finished but no new files were found in the output folders. "
                "Check OUTPUT_DIRS at the top of app.py."
            )
        for f in files:
            st.download_button(
                label=f"Download {f.name}",
                data=f.read_bytes(),
                file_name=f.name,
                mime=MIME.get(f.suffix.lower(), "application/octet-stream"),
                key=str(f),
            )
