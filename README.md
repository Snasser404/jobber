# 🎯 Jobber

Your personal job-application co-pilot. It **finds** jobs from reliable sources,
**ranks** them against your resume with Claude, **tailors** a resume + cover letter
for each one, shows you a **preview**, and pre-fills the application form — then
**stops so you do the final review and click submit**. You stay in control; nothing
is ever sent without you.

## What it does

1. **Find** — pulls listings from Remotive, RemoteOK, Arbeitnow, optional Adzuna
   (Canada), and any company Greenhouse/Lever boards you list. No scraping, no ban risk.
2. **Rank** — Claude scores each job 0–100 against *your* resume, with reasons + gaps.
3. **Tailor** — Claude rewrites your summary for the role and drafts a specific cover
   letter, using only your real experience. Saves both as `.docx`.
4. **Preview** — see the job, the fit reasoning, what changed in the resume, and the
   editable cover letter, all in one place.
5. **Apply** — opens the real application page in a browser and fills in your details +
   resume + cover letter. **You review and submit.**

## One-time setup

```powershell
# 1. Install dependencies
pip install -r requirements.txt
python -m playwright install chromium

# 2. Add your Claude API key
copy .env.example .env
#    then open .env and paste your key after ANTHROPIC_API_KEY=
#    (get one at https://console.anthropic.com -> API Keys)

# 3. (optional) free Adzuna key for lots more Canadian jobs:
#    sign up at https://developer.adzuna.com and add the IDs to .env
```

Your resume lives at `data/profile/master_resume.docx`. The app **never edits the
original** — every tailored version is a fresh copy in `data/output/`.

## Run it

```powershell
streamlit run app.py
```

Your browser opens to the app. Click **Find & rank jobs**, open a match, click
**Tailor**, review, then **Open & pre-fill application**.

## Use it on your other devices (online)

Reach Jobber from your phone or another laptop, anywhere, while it keeps running on
your PC (so the auto-fill browser still works and your data stays on your machine).

1. Make sure `JOBBER_PASSWORD=` in `.env` has a password (protects the link).
2. Right-click **`serve_online.ps1`** → **Run with PowerShell**.
3. In the window, copy the link that looks like `https://<words>.trycloudflare.com`.
4. Open that link on any device, enter your password, and use the app normally.
5. Keep the window open while you use it; press **Ctrl+C** to stop sharing.

Notes:
- Your PC must stay on. The link changes each time you start it.
- Only someone with **both** the link and your password can get in.
- **Open & pre-fill application** opens the browser **on your PC** (that's where the
  automation lives). From your phone you can still find, rank, tailor, preview, and
  download everything; the live form-fill happens on the host PC.

## The search follows your résumé

Drop a `.docx` into **Upload a résumé** in the sidebar and the app reads it and
**auto-retargets the search keywords to match that résumé** — a marketing résumé
finds marketing roles, an AI-engineering résumé finds ML roles. Keep several résumé
variants for different fields and switch between them anytime. The keyword box stays
editable, so you can always tweak what it searches for. (Use **Suggest search terms
from this résumé** to re-derive them for the current résumé.)

## Tune your search

The keywords/location/remote toggle live in the sidebar. Deeper settings are in
**`config.yaml`**: the minimum fit score to show, exclude filters, your contact
details for forms, and which company career boards to pull from.

## Applying (the browser step)

When you click **Open & pre-fill application**, a browser opens and the assistant:
- navigates from the listing to the real application form (following "Apply" and new tabs),
- uses **Claude to read the page** and fill standard fields, dropdowns, and eligibility
  questions (work authorization, sponsorship, relocation…) from your profile,
- pastes your cover letter into "why/message" boxes and uploads your résumé,
- advances multi-step forms, and pauses on logins,
- **stops before the final submit** — you review and click submit yourself.

Open **🪵 Show assistant log** on a job to watch exactly what it did and where it paused.

**Optional auto sign-in:** copy `data/credentials.example.json` to `data/credentials.json`
and add site logins (matched by domain). The assistant fills them on a login page but still
pauses for 2FA/CAPTCHA and never submits the application. `credentials.json` is git-ignored.

## Notes

- **Honesty:** tailoring and form-answers only use your real experience — they never invent
  jobs, dates, metrics, or skills, and never accept terms/consent for you.
- **Cost:** ranking uses the cheap, fast Claude Haiku model (pennies for dozens of jobs);
  cover letters and form-reading use Claude Sonnet. Resume text is cached to keep costs low.
- **Submitting:** the browser step fills fields and uploads your files but **does not click
  submit** — that's your job, on purpose.
