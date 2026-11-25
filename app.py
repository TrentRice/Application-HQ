"""
Application HQ front end.

    streamlit run app.py

Generate tab: paste a job description, get a one-page tailored resume and a cover letter.
What's stored tab: see exactly which experience, metrics and skills the generator can draw on.
"""

import json
import subprocess
import sys

import streamlit as st

from hq.paths import COVER_DOCX, JOB_DESCRIPTION, RESUME_DOCX, RESUME_REPORT, ROOT
from hq.profile import load_profile

STEPS = [
    ("Writing tailored resume", "hq.resume"),
    ("Writing cover letter", "hq.cover_letter"),
]
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def run_step(module: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", module],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


st.set_page_config(page_title="Application HQ", page_icon="📄", layout="centered")
st.title("📄 Application HQ")

generate_tab, stored_tab = st.tabs(["Generate", "What's stored"])

# ---- Generate ---------------------------------------------------------------------
with generate_tab:
    st.caption("Paste a job description to generate a tailored one-page resume and cover letter.")
    job_description = st.text_area(
        "Job description", height=350, placeholder="Paste the full job posting here..."
    )

    if st.button("Generate", type="primary", disabled=not job_description.strip()):
        JOB_DESCRIPTION.parent.mkdir(parents=True, exist_ok=True)
        JOB_DESCRIPTION.write_text(job_description.strip(), encoding="utf-8")
        st.session_state.pop("results", None)

        failed = False
        with st.status("Working...", expanded=True) as status:
            for label, module in STEPS:
                st.write(f"⏳ {label}...")
                result = run_step(module)
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
            st.session_state["results"] = {
                "files": [(p.name, p.read_bytes()) for p in (RESUME_DOCX, COVER_DOCX) if p.exists()],
                "report": json.loads(RESUME_REPORT.read_text()) if RESUME_REPORT.exists() else None,
            }

    # Kept in session state so results survive the rerun a download click triggers.
    results = st.session_state.get("results")
    if results:
        cols = st.columns(len(results["files"]) or 1)
        for col, (name, data) in zip(cols, results["files"]):
            col.download_button(f"Download {name}", data=data, file_name=name, mime=DOCX_MIME, key=name)

        report = results["report"]
        if report:
            st.subheader("Resume check")
            fill = report["page_fill"]
            st.progress(min(fill, 1.0), text=f"One page: {fill:.0%} full ({report['lines_free']} lines free)")
            if report["trimmed_to_fit"]:
                with st.expander(f"✂️ {len(report['trimmed_to_fit'])} item(s) trimmed to stay on one page"):
                    for t in report["trimmed_to_fit"]:
                        st.write(f"- {t}")
            if report["notes"]:
                st.caption("Bullets that could be stronger. Add a metric in data/profile.json to fix these:")
                for n in report["notes"]:
                    st.warning(f"**{n['section']}**: {n['bullet']}\n\n⚠ {n['note']}")
            else:
                st.success("Every bullet follows the formula with a quantified impact.")

# ---- What's stored ----------------------------------------------------------------
with stored_tab:
    try:
        profile = load_profile()
    except Exception as e:  # malformed profile.json
        st.error(f"Could not read data/profile.json: {e}")
        st.stop()

    facts = profile.all_facts()
    missing = sum(1 for _, f in facts if not f.metrics)
    st.caption(
        f"{len(profile.experience)} jobs · {len(profile.projects)} projects in the pool "
        f"({profile.projects_to_show} shown per resume) · {len(facts)} facts · "
        f"{missing} without a metric. Source: data/profile.json"
    )
    st.markdown("Bullet formula: **[action verb] [what you did] [with what tools or methods], [impact]**")

    h = profile.header
    with st.expander(f"Header & education: {h.name}, {h.title}"):
        st.write(f"{h.location} · {h.phone} · {h.email}")
        st.write(" · ".join(f"[{l.label}]({l.url})" for l in h.links))
        for e in profile.education:
            st.write(f"- **{e.degree}**, {e.school}, {e.detail} ({e.date})")

    with st.expander("Skill pools (the generator picks the most relevant from each)"):
        for g in profile.skills:
            st.write(f"**{g.name}** (up to {g.max_items}): {', '.join(g.pool)}")

    def show(section, kind):
        label = f"{section.title}" + (f" · {section.org}" if section.org else "") + f" · {section.dates}"
        with st.expander(f"{kind} {label}  ({len(section.facts)} facts, max {section.max_bullets} bullets)"):
            for f in section.facts:
                badge = "📊 " + "; ".join(f.metrics) if f.metrics else "⚠ no metric stored"
                st.markdown(
                    f"**{f.action}** {f.what} · _{', '.join(f.tools) or 'no tools'}_ · "
                    f"{f.impact or '(no impact)'}  \n<small>{badge}</small>",
                    unsafe_allow_html=True,
                )

    st.markdown("#### Experience")
    for s in profile.experience:
        show(s, "💼")
    st.markdown("#### Project pool")
    for s in profile.projects:
        show(s, "🛠")
