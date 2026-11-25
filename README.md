# Application HQ

Paste a job description, get a tailored **one-page** resume and a cover letter as Word documents.

Application HQ keeps your work history as structured facts, finds the ones most relevant to a job posting, and has Claude rewrite them into bullets that follow one formula:

> **[action verb] [what you did] [with what tools or methods], [impact, ideally quantified]**

Every bullet is checked before it reaches the page. Numbers can only come from your stored facts, and the layout is measured so the resume always fits on one page.

## How it works

```
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

1. **Your profile is the single source of truth.** [`data/profile.json`](data/profile.json) holds your header, education, skill pools, jobs and a project pool. Each job contains *facts*: one piece of work each, stored already split into the formula. For example:
   ```json
   {
     "id": "hr_pathfinder",
     "action": "Developed",
     "what": "HR Pathfinder, a RAG-powered AI assistant for knowledge retrieval over HR process documentation",
     "tools": ["RAG", "Prompt Engineering", "SharePoint"],
     "impact": "saving 650 hours annually",
     "metrics": ["650 hours saved annually", "123 potential users", "$23.8K annual benefit"],
     "keywords": ["LLM", "Generative AI"]
   }
   ```
2. **Facts are ranked against the job.** Each fact is embedded with `all-MiniLM-L6-v2` and stored in ChromaDB (`vectorstore/`). The job description is embedded the same way, and every fact gets a relevance score. This is retrieval-augmented generation (RAG). The index rebuilds itself whenever `profile.json` changes.
3. **Claude picks and writes.** For each job it chooses the most relevant facts, up to that job's `max_bullets`. It picks the `projects_to_show` best projects from the pool and chooses skills from each skill pool, all as schema-validated JSON. Bullets come back in formula parts, and the code assembles them.
4. **Every bullet is checked.** It must start with a strong past-tense verb, name tools or methods, use only numbers that appear in its source facts, use a stored metric if one exists, and fit in two lines. Failures are sent back to Claude for up to two revisions. Anything still failing falls back to your stored wording for that fact.
5. **It's fitted to one page.** The template uses exact line spacing, and line wrapping is measured with real Arial font metrics, so page height can be calculated without Word. If the content is too long, the lowest-relevance bullets are trimmed first. Every job keeps at least one bullet.
6. **It's rendered.** [`templates/resume_template.docx`](templates/resume_template.docx) is a [docxtpl](https://docxtpl.readthedocs.io) template that loops over jobs, projects, bullets and skills. The layout matches the November 2026 resume: contact | name | links header, Education, Technical Skills, Work Experience, Projects.
7. **A report shows what could be stronger.** `output/resume_report.json` and the app list bullets with no quantified impact and anything trimmed to fit. Add a metric to that fact in `profile.json` and the warning goes away.

The cover letter uses the same profile and ranking, and fills `{{INTRO}}`, `{{BODY}}`, `{{WHY_COMPANY}}` and `{{CLOSING}}` in `templates/TrentRice_CoverLetter_Template.docx`.

## Project structure

```
Application-HQ/
├── app.py                    Streamlit app: Generate tab + "What's stored" tab
├── requirements.txt
├── .env                      Optional CLAUDE_MODEL / CLAUDE_EFFORT / CLAUDE_BIN, not committed
├── data/
│   ├── profile.json          Your profile and experience facts (edit this)
│   └── job_description.txt   Latest pasted job posting (written by the app)
├── hq/
│   ├── profile.py            Profile data model
│   ├── index.py              Vector index + relevance ranking
│   ├── bullets.py            Bullet formula and checks
│   ├── layout.py             Page geometry and one-page measurement
│   ├── build_template.py     Generates templates/resume_template.docx
│   ├── resume.py             Resume pipeline
│   ├── cover_letter.py       Cover letter pipeline
│   └── llm.py                Calls Claude via the Claude Code CLI (structured output)
├── templates/
│   ├── resume_template.docx
│   └── TrentRice_CoverLetter_Template.docx
├── vectorstore/              Generated index (not committed)
└── output/                   Generated .docx, JSON and report
```

## Setup

You need Python 3.10 or newer, and Claude Code signed in with your Claude Pro or Max account.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m hq.llm                   # should print "ready"
```

No API key is needed. The app finds the `claude` command on your PATH, or the copy that ships with the Claude Code VS Code extension. If it can't find either, install Claude Code (https://claude.com/claude-code) or set `CLAUDE_BIN=/path/to/claude` in `.env`. The first run downloads the embedding model, which takes about a minute.

## Usage

```bash
source .venv/bin/activate
streamlit run app.py
```

Open http://localhost:8501. The page is only available while this command runs.

- **Generate tab:** paste a job description and click **Generate**. Then download the resume and cover letter, and review the resume check (page fill, trimmed items, bullets that could be stronger).
- **What's stored tab:** shows every job, project, fact, metric and skill pool the generator can use. Facts without a metric are flagged ⚠.

Without the UI, from the repo root:

```bash
python -m hq.resume          # → output/tailored_resume.docx
python -m hq.cover_letter    # → output/tailored_cover_letter.docx
python -m hq.index "query"   # rebuild the index and test a search
python -m hq.llm             # check that Claude Code is reachable and signed in
```

## Updating your experience

Edit [`data/profile.json`](data/profile.json). The index rebuilds automatically on the next run.

- **Add a job:** add an entry to `experience` with `id`, `title`, `org`, `dates`, `max_bullets` and `facts`. No template or code changes are needed.
- **Add a project:** add it to `projects`. The `projects_to_show` best matches appear on each resume.
- **Add a fact:** give it a unique `id` and fill in `action`, `what`, `tools`, `impact` and `metrics`. **Metrics matter.** Numbers in `metrics` are the only numbers the generator is allowed to use.
- **Skills:** each group has a `pool` and `max_items`. The most relevant items are chosen per job, and each group always fits on one line.

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
