# Application HQ

Paste a job description, get a tailored **one-page** resume and a cover letter as Word documents.

Application HQ keeps your work history as structured facts, finds the ones most relevant to a job posting, and has Claude rewrite them into bullets that follow one formula:

> **[action verb] [what you did] [with what tools or methods], [impact, ideally quantified]**

Every bullet is checked before it reaches the page. Numbers can only come from your stored facts, and the layout is measured so the resume always fits on one page.

## How it works

```
Word bullet bank (data/*.docx) ──sync──► data/profile.json  (new/edited bullets split into formula parts)
                                                │
data/profile.json ──► vector index (ChromaDB, auto-rebuilt when the profile changes)
                              │
job description ──► embed ──► rank every fact by relevance
                              │
                              ▼
                 Claude writes bullets in formula parts
                 (action / what / how / impact + fact_ids)
                              │
                              ▼
         checks: strong verb · tools present · no invented numbers ·
         stored metric used · ≤ 2 lines   ──fail──► revise (up to 2×) ──► fall back to stored wording
                              │
                              ▼
        one-page fitter: trims lowest-relevance bullets until it fits
                              │
                              ▼
        templates/resume_template.docx ──► output/tailored_resume.docx
```

1. **Your Word bullet bank is the source of truth.** Edit `data/<your bullet bank>.docx` in Word. Before every Generate, `hq/bullet_bank.py` checks whether the document changed. If it did, it reads the structure (jobs, dates, projects, sub-headings, bullets) and sends only new or edited bullets to Claude, which splits each one into formula parts. Every number in those parts must appear in your original bullet. The result goes into the `experience` and `projects` sections of [`data/profile.json`](data/profile.json), which you don't edit by hand. A stored fact looks like this:
   ```json
   {
     "id": "j-d-irving-ltd-1a2b3c4d",
     "action": "Developed",
     "what": "HR Pathfinder, a retrieval-augmented (RAG) AI agent ... giving 123 HR users cited answers",
     "tools": ["RAG", "Copilot Studio", "SharePoint"],
     "impact": "saving an estimated 650 hours ($23.8K net benefit) per year",
     "metrics": ["123 HR users", "650 hours", "$23.8K net benefit"],
     "keywords": ["LLM", "Generative AI"],
     "source": "Developed HR Pathfinder, ... per year.",
     "group": "HR Pathfinder (AI knowledge agent)"
   }
   ```
   The `id` is a fingerprint of the bullet's text, so unchanged bullets are never reprocessed.
2. **Facts are ranked against the job.** Each fact is embedded with `all-MiniLM-L6-v2` and stored in ChromaDB (`vectorstore/`). The job description is embedded the same way, and every fact gets a relevance score. This is retrieval-augmented generation (RAG). The index rebuilds itself whenever `profile.json` changes.
3. **Claude picks and writes.** For each job it chooses the most relevant facts, up to that job's `max_bullets`. It picks the `projects_to_show` best projects from the pool and chooses skills from each skill pool, all as schema-validated JSON. Bullets come back in formula parts, and the code assembles them.
4. **Every bullet is checked.** It must start with a strong past-tense verb, name tools or methods, use only numbers that appear in its source facts, use a stored metric if one exists, and fit in two lines. Failures are sent back to Claude for up to two revisions. Anything still failing falls back to your stored wording for that fact.
5. **It's fitted to one page.** The template uses exact line spacing, and line wrapping is measured with real Arial font metrics, so page height can be calculated without Word. If the content is too long, the lowest-relevance bullets are trimmed first. Every job keeps at least one bullet.
6. **It's rendered.** [`templates/resume_template.docx`](templates/resume_template.docx) is a [docxtpl](https://docxtpl.readthedocs.io) template that loops over jobs, projects, bullets and skills. The layout matches the November 2026 resume: contact | name | links header, Education, Technical Skills, Work Experience, Projects.
7. **A report shows what could be stronger.** `output/resume_report.json` and the app list bullets with no quantified impact and anything trimmed to fit. Add a number to that bullet in your bullet bank and the warning goes away.

The cover letter uses the same profile and ranking, and fills `{{INTRO}}`, `{{BODY}}`, `{{WHY_COMPANY}}` and `{{CLOSING}}` in `templates/cover_letter_template.docx`, along with `{{NAME}}`, `{{LOCATION}}`, `{{PHONE}}` and `{{EMAIL}}` from your profile header (`letter_location` overrides the location line).

## Project structure

```
Application-HQ/
├── app.py                    Streamlit app: Generate tab + "What's stored" tab (with Sync button)
├── requirements.txt
├── .env                      Optional CLAUDE_MODEL / CLAUDE_EFFORT / CLAUDE_BIN, not committed
├── data/                     Personal, git-ignored
│   ├── <bullet bank>.docx    Your experience and projects (edit this in Word)
│   ├── profile.json          Header, education, skills, settings (edit) + synced facts (generated)
│   └── job_description.txt   Latest pasted job posting (written by the app)
├── examples/                 Fictional profile and bullet bank to copy into data/
├── hq/
│   ├── profile.py            Profile data model
│   ├── bullet_bank.py        Syncs the Word bullet bank into profile.json
│   ├── index.py              Vector index + relevance ranking
│   ├── bullets.py            Bullet formula and checks
│   ├── layout.py             Page geometry and one-page measurement
│   ├── build_template.py     Generates templates/resume_template.docx
│   ├── resume.py             Resume pipeline
│   ├── cover_letter.py       Cover letter pipeline
│   └── llm.py                Calls Claude via the Claude Code CLI (structured output)
├── templates/
│   ├── resume_template.docx
│   └── cover_letter_template.docx
├── vectorstore/              Generated index (not committed)
└── output/                   Generated .docx, JSON and report (git-ignored)
```

## Setup

You need Python 3.10 or newer, and Claude Code signed in with your Claude Pro or Max account.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m hq.llm                   # should print "ready"

cp examples/profile.example.json data/profile.json   # then edit header, education, skills
cp examples/bullet_bank.example.docx data/           # or put your own bullet bank .docx in data/
```

No API key is needed. The app finds the `claude` command on your PATH, or the copy that ships with the Claude Code VS Code extension. If it can't find either, install Claude Code (https://claude.com/claude-code) or set `CLAUDE_BIN=/path/to/claude` in `.env`. The first run downloads the embedding model, which takes about a minute.

### Private files (not in this repo)

This repo is the working tool I use for my own job applications. Some of the files it reads and produces contain my personal details, so they're kept on my machine and excluded from GitHub by `.gitignore`:

| File | What it is |
|---|---|
| `data/profile.json` | My contact details, education, skill pools and the facts synced from my bullet bank |
| `data/<bullet bank>.docx` | My full experience bullet bank: every job and project |
| `data/job_description.txt` | The job posting I'm currently applying to |
| `output/` | The resumes, cover letters and reports the app generates |

They're missing here on purpose, not by accident. To see how they're structured, or to run the app yourself, start from the fictional versions in [`examples/`](examples/) (copied into `data/` in the setup steps above). The templates contain only placeholders: name, location, phone and email are filled in from `data/profile.json` when a document is generated, so no personal details are stored in the committed files.

## Usage

```bash
source .venv/bin/activate
streamlit run app.py
```

Open http://localhost:8501. This isn't a public website: `localhost` means the app is running on your own computer, so the link only works on the machine that ran the command, and only while that command is running. [`.streamlit/config.toml`](.streamlit/config.toml) also restricts the app to this computer, so other devices on the same Wi-Fi can't open it either. For me, that link is my private copy of the tool running on my laptop. There's no hosted version to visit.

- **Generate tab:** paste a job description and click **Generate**. Then download the resume and cover letter, and review the resume check (page fill, trimmed items, bullets that could be stronger).
- **What's stored tab:** shows every job, project, fact, metric and skill pool the generator can use. Facts without a metric are flagged ⚠.

Without the UI, from the repo root:

```bash
python -m hq.bullet_bank     # sync the Word bullet bank (add --force to re-read it)
python -m hq.resume          # → output/tailored_resume.docx
python -m hq.cover_letter    # → output/tailored_cover_letter.docx
python -m hq.index "query"   # rebuild the index and test a search
python -m hq.llm             # check that Claude Code is reachable and signed in
```

## Updating your experience

**Edit your Word bullet bank** in `data/` and save it. The next Generate syncs it automatically, or click **Sync bullet bank now** on the What's stored tab. Only new or edited bullets are processed, so small edits take seconds.

Keep the document's structure so the importer can read it:
- **Jobs:** a Heading 2 of the form `Company – Job Title`, then a line with the dates (e.g. `May 2026 – Aug 2026 · Halifax, NS`).
- **Project groups:** a Heading 2 containing "Projects" (e.g. `Personal Projects`). Each project is a Heading 3 followed by a `dates · tools` line.
- **Sub-headings:** Heading 3 inside a job, or Heading 4 inside a project, group related bullets. A bold "Resume one-liners" line marks a project's preferred summary bullets.
- **Bullets:** any bulleted list item. Start each with a past-tense verb and include numbers where you have them. Numbers in your bullets are the only numbers the generator can use.

Other settings live in [`data/profile.json`](data/profile.json) and are edited by hand:
- **`header`, `education`:** printed as-is on every resume.
- **`skills`:** each group has a `pool` and `max_items`. The most relevant items are chosen per job, and each group always fits on one line.
- **`section_settings`:** per-job overrides keyed by section id, e.g. `{"ns-health": {"max_bullets": 2}}`. Jobs default to 2 bullets and projects to 1. You can also override a printed `title`.
- **`projects_to_show`:** how many projects appear on each resume.

## Changing the resume design

The template is generated by `python -m hq.build_template` from the sizes and spacing in [`hq/layout.py`](hq/layout.py). To change the design, edit those constants and rebuild. That keeps the one-page measurement accurate.

You can also restyle `templates/resume_template.docx` in Word directly, for example colors or bold. Keep every `{{ }}` and `{%p %}` tag intact. If you change font, size, margins or spacing, mirror the change in `layout.py`, or the one-page check will drift.

## Model

Claude runs through the Claude Code CLI in headless mode (`claude -p`), using your Claude subscription instead of a paid API key, so usage counts against your plan's limits. A resume plus a cover letter takes about 3–4 requests and roughly a minute. This is meant for personal use on your own machine. To share the tool with other people, switch `hq/llm.py` to the Claude API with an API key.

Each request runs with no tools, no MCP servers, no settings or hooks, and no saved session. The answer is constrained with `--json-schema` and validated against the pydantic schemas in `hq/`.

Optional `.env` settings:
- `CLAUDE_MODEL=...` picks a model (default: your Claude Code default), for example `sonnet` to save plan usage.
- `CLAUDE_EFFORT=low|medium|high` sets thinking depth (default: `medium`).
- `CLAUDE_BIN=...` gives the path to the `claude` executable.
