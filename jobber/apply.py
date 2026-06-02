"""Open a job's application page, navigate to the real form, and let Claude fill it.

Runs as its own process:   python -m jobber.apply <payload.json>

Flow:
  1. open the apply URL,
  2. if it's a listing/aggregator page, click "Apply" and follow it (incl. new tabs),
  3. read the form with Claude and fill standard fields, eligibility questions,
     dropdowns, and the cover-letter box; advance multi-step forms,
  4. on a login/sign-up page, fill the email (and saved password if you set one),
     then PAUSE for you to finish (password / 2FA / CAPTCHA),
  5. STOP before the final submit — you review and submit yourself.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from urllib.parse import urlparse

from . import config

ATS_HOSTS = (
    "greenhouse.io", "lever.co", "ashbyhq.com", "workable.com", "myworkdayjobs.com",
    "icims.com", "bamboohr.com", "jobvite.com", "smartrecruiters.com", "breezy.hr",
    "recruitee.com", "teamtailor.com", "applytojob.com", "jazzhr.com", "workday.com",
    "taleo.net", "successfactors.com", "dayforcehcm.com", "paylocity.com",
)

# JS that tags every fillable control with data-jb=<index> and returns its metadata.
_EXTRACT_JS = r"""
() => {
  const out = [];
  let i = 0;
  document.querySelectorAll('input, textarea, select').forEach(el => {
    const type = (el.type || '').toLowerCase();
    if (['hidden', 'submit', 'button', 'image', 'reset'].includes(type)) return;
    if (el.offsetParent === null && type !== 'file') return;   // skip invisible (keep file inputs)
    el.setAttribute('data-jb', i);
    let label = '';
    if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) label = l.innerText; }
    if (!label) { const p = el.closest('label'); if (p) label = p.innerText; }
    if (!label) label = el.getAttribute('aria-label') || el.placeholder || '';
    let options;
    if (el.tagName === 'SELECT') options = Array.from(el.options).map(o => o.text.trim()).slice(0, 40);
    let group = '';
    if (type === 'radio' || type === 'checkbox') {
      const fs = el.closest('fieldset'); if (fs) { const lg = fs.querySelector('legend'); if (lg) group = lg.innerText; }
    }
    out.push({ i, tag: el.tagName.toLowerCase(), type, name: el.name || '', id: el.id || '',
               label: (label || '').trim().slice(0, 140), value: (el.value || '').slice(0, 60),
               required: !!el.required, options, group: group.trim().slice(0, 180) });
    i++;
  });
  return { fields: out, passwordFields: document.querySelectorAll('input[type=password]').length,
           url: location.href, title: document.title, textSample: (document.body.innerText || '').slice(0, 3000) };
}
"""

PLAN_SYSTEM = """You fill out job-application web forms on behalf of a real candidate.
Use ONLY truthful values from the candidate profile. Never fabricate experience, dates, or answers.
For required questions you cannot answer truthfully from the profile, leave them for the user.
You never submit the final application and never accept terms/consent on the user's behalf."""

PLAN_PROMPT = """Map this candidate to the form fields on the current page.

CANDIDATE PROFILE (truthful values you may use):
{answers}

COVER LETTER (use for long 'why us' / 'message' / 'additional information' boxes):
{cover}

CURRENT PAGE: title={title!r}  url={url!r}  password_fields={pwd}
PAGE TEXT (sample):
{text}

FORM FIELDS (each: i, tag, type, name, id, label, options, group, required):
{fields}

Return ONLY JSON:
{{
  "page_type": "application_form" | "login" | "signup" | "other",
  "actions": [ {{"i": <int>, "op": "fill"|"select"|"check"|"upload_resume", "value": <string|true>}} ],
  "click_next": "<exact visible text of a Next/Continue button to advance a MULTI-STEP form, else ''>",
  "needs_user": "<short note if the user must act (password, CAPTCHA, a question you can't answer), else ''>"
}}

Rules:
- Map name/email/phone/location/LinkedIn/website to the matching fields.
- Eligibility (work authorization, sponsorship, relocation, start date): use the profile booleans;
  for a <select> use op "select" with the exact option text; for radios use op "check" on the matching option's i.
- For a résumé/CV file input use op "upload_resume".
- For 'cover letter' / 'why' / 'message' / 'additional information' textareas, fill with the cover letter.
- Do NOT check consent, terms, privacy, or newsletter checkboxes — leave those for the user.
- Do NOT fill anything you have no truthful value for; mention it in needs_user instead.
- NEVER put a final Submit/Send/Apply button in click_next — only true intermediate steps.
- If it's a login or signup page, set page_type and fill the email/username; put the rest in needs_user."""


def log(msg: str) -> None:
    print(msg, flush=True)


def _split_name(full: str) -> tuple[str, str]:
    parts = (full or "").split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def build_answers(a: dict) -> dict:
    """Flatten the applicant config into truthful answer values for the planner."""
    first, last = _split_name(a.get("full_name", ""))
    yn = lambda v: "Yes" if v else "No"
    return {
        "first_name": first, "last_name": last, "full_name": a.get("full_name", ""),
        "email": a.get("email", ""), "phone": a.get("phone", ""),
        "location": a.get("location", ""), "linkedin": a.get("linkedin", ""),
        "website": a.get("website", ""),
        "authorized_to_work_in_canada": yn(a.get("authorized_to_work_canada", True)),
        "requires_visa_sponsorship": yn(a.get("requires_visa_sponsorship", False)),
        "willing_to_relocate": yn(a.get("willing_to_relocate", False)),
        "years_of_experience": str(a.get("years_experience", "")),
        "languages": a.get("languages", ""),
    }


# --------------------------------------------------------------- LLM planning
def plan_actions(extract: dict, answers: dict, cover: str):
    from . import llm
    fields = extract.get("fields", [])[:60]
    prompt = PLAN_PROMPT.format(
        answers=json.dumps(answers, ensure_ascii=False),
        cover=(cover or "")[:1500],
        title=extract.get("title", ""), url=extract.get("url", ""),
        pwd=extract.get("passwordFields", 0),
        text=(extract.get("textSample", "") or "")[:1500],
        fields=json.dumps(fields, ensure_ascii=False),
    )
    data = llm.complete_json(prompt, system=PLAN_SYSTEM, role="write",
                             max_tokens=1500, temperature=0.0)
    return data if isinstance(data, dict) else None


# --------------------------------------------------------------- execution
def _execute(scope, actions: list, resume: str) -> int:
    done = 0
    for act in actions or []:
        i, op, val = act.get("i"), act.get("op"), act.get("value")
        if i is None:
            continue
        loc = scope.locator(f'[data-jb="{i}"]')
        try:
            if op == "fill":
                loc.first.fill(str(val), timeout=2500)
            elif op == "select":
                try:
                    loc.first.select_option(label=str(val), timeout=2500)
                except Exception:
                    loc.first.select_option(value=str(val), timeout=2500)
            elif op == "check":
                loc.first.check(timeout=2500)
            elif op == "upload_resume":
                if resume and os.path.exists(resume):
                    loc.first.set_input_files(resume, timeout=3000)
                else:
                    continue
            else:
                continue
            done += 1
        except Exception as e:
            log(f"  · couldn't {op} field {i}: {repr(e)[:70]}")
    return done


def _click_next(scope, text: str) -> bool:
    if not text or re.search(r"submit|send|finish|apply now", text, re.I):
        return False
    try:
        btn = scope.get_by_role("button", name=re.compile(re.escape(text), re.I))
        if not btn.count():
            btn = scope.get_by_text(re.compile(re.escape(text), re.I))
        if btn.count():
            btn.first.click(timeout=4000)
            return True
    except Exception:
        pass
    return False


# --------------------------------------------------------------- heuristic fallback
def _fallback_fill(scope, answers: dict, resume: str, cover: str) -> int:
    def fill(value, labels=(), selectors=()):
        if not value:
            return 0
        for pat in labels:
            try:
                loc = scope.get_by_label(re.compile(pat, re.I))
                if loc.count():
                    loc.first.fill(value, timeout=2000)
                    return 1
            except Exception:
                pass
        for sel in selectors:
            try:
                loc = scope.locator(sel)
                if loc.count():
                    loc.first.fill(value, timeout=2000)
                    return 1
            except Exception:
                pass
        return 0

    n = 0
    n += fill(answers["first_name"], [r"first name"], ["input[name='first_name']", "input[autocomplete='given-name']"])
    n += fill(answers["last_name"], [r"last name"], ["input[name='last_name']", "input[autocomplete='family-name']"])
    n += fill(answers["full_name"], [r"^name$|full name|your name"], ["input[name='name']"])
    n += fill(answers["email"], [r"e-?mail"], ["input[type='email']", "input[name='email']"])
    n += fill(answers["phone"], [r"phone|mobile"], ["input[type='tel']", "input[name='phone']"])
    n += fill(answers["location"], [r"location|city"], ["input[name='location']", "input[id*='location']"])
    n += fill(answers["linkedin"], [r"linkedin"], ["input[name*='linkedin']", "input[id*='linkedin']"])
    try:
        f = scope.locator("input[type='file']")
        if f.count() and resume and os.path.exists(resume):
            f.first.set_input_files(resume, timeout=3000)
            n += 1
    except Exception:
        pass
    if cover:
        try:
            ta = scope.locator("textarea")
            if ta.count() == 1:
                ta.first.fill(cover, timeout=2500)
                n += 1
        except Exception:
            pass
    return n


# --------------------------------------------------------------- credentials (optional)
def _load_credentials() -> dict:
    p = config.ROOT / "data" / "credentials.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _creds_for(url: str, creds: dict):
    host = urlparse(url).netloc.lower()
    for domain, c in creds.items():
        if domain.lower() in host:
            return c
    return None


def _handle_login(target, creds: dict) -> None:
    c = _creds_for(target.url, creds)
    if not c:
        log("ACTION NEEDED: this site needs you to log in / sign up. I filled what I could — "
            "please enter your password and complete sign-in (and any 2FA).")
        return
    if c.get("username"):
        for sel in ["input[type=email]", "input[name*=email]", "input[name*=user]",
                    "input[id*=user]", "input[name=session_key]"]:
            try:
                loc = target.locator(sel)
                if loc.count():
                    loc.first.fill(c["username"], timeout=2000)
                    break
            except Exception:
                pass
    if c.get("password"):
        try:
            pw = target.locator("input[type=password]")
            if pw.count():
                pw.first.fill(c["password"], timeout=2000)
        except Exception:
            pass
        log("Filled your saved login. Click sign-in (and finish any 2FA/CAPTCHA) to continue.")
    else:
        log("ACTION NEEDED: enter your password and sign in to continue.")


# --------------------------------------------------------------- navigation
def _is_form(scope) -> bool:
    try:
        if scope.locator("input[type='file']").count() > 0:
            return True
        has_email = scope.locator("input[type='email'], input[name='email']").count() > 0
        has_name = scope.locator(
            "input[name='first_name'], input[name='name'], input[autocomplete='given-name']").count() > 0
        has_tel = scope.locator("input[type='tel']").count() > 0
        return has_email and (has_name or has_tel)
    except Exception:
        return False


def _host_is_ats(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(a in host for a in ATS_HOSTS)


def _find_apply(scope):
    for getter in (
        lambda: scope.get_by_role("link", name=re.compile(r"\bapply\b", re.I)),
        lambda: scope.get_by_role("button", name=re.compile(r"\bapply\b", re.I)),
    ):
        try:
            loc = getter()
            if loc.count():
                return loc.first
        except Exception:
            continue
    for sel in ("a:has-text('Apply')", "button:has-text('Apply')",
                "[data-testid*='apply']", "a.apply-button", "a#apply"):
        try:
            loc = scope.locator(sel)
            if loc.count():
                return loc.first
        except Exception:
            continue
    return None


def _best_scope(target):
    """Pick the page/iframe that actually holds the form (handles Greenhouse iframes)."""
    scopes = [target]
    try:
        scopes += [f for f in target.frames if f is not target.main_frame]
    except Exception:
        pass
    best, best_ex = None, None
    for s in scopes:
        try:
            ex = s.evaluate(_EXTRACT_JS)
        except Exception:
            continue
        if ex["fields"] and (best_ex is None or len(ex["fields"]) > len(best_ex["fields"])):
            best, best_ex = s, ex
    if best is None:
        try:
            best_ex = target.evaluate(_EXTRACT_JS)
        except Exception:
            best_ex = {"fields": [], "passwordFields": 0, "url": target.url, "title": "", "textSample": ""}
        best = target
    return best, best_ex


# --------------------------------------------------------------- main
def run(payload: dict) -> None:
    from playwright.sync_api import sync_playwright

    a = payload.get("applicant", {})
    answers = build_answers(a)
    resume = payload.get("resume_path", "")
    cover = payload.get("cover_letter", "")
    start_url = payload["apply_url"]
    creds = _load_credentials()
    have_ai = config.has_anthropic_key()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(accept_downloads=True)
        opened: list = []
        ctx.on("page", lambda pg: opened.append(pg))
        page = ctx.new_page()

        log(f"Opening: {start_url}")
        try:
            page.goto(start_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            log(f"Could not load page: {e}")
        page.wait_for_timeout(2500)
        target = page

        # Walk toward the real application form (max 3 hops).
        for hop in range(3):
            if _is_form(target) or _host_is_ats(target.url):
                log(f"Application form detected at: {target.url}")
                break
            apply_ctrl = _find_apply(target)
            if not apply_ctrl:
                log("Listing page with no obvious Apply button — opening it for you to apply manually.")
                break
            log(f"Clicking 'Apply' (step {hop + 1})…")
            before = len(opened)
            try:
                apply_ctrl.click(timeout=6000)
            except Exception as e:
                log(f"  couldn't click Apply: {e}")
                break
            page.wait_for_timeout(4000)
            target = opened[-1] if len(opened) > before else target
            try:
                target.wait_for_load_state("domcontentloaded", timeout=30000)
                target.bring_to_front()
            except Exception:
                pass
            log(f"  now at: {target.url}")

        total = 0
        # AI-driven fill loop (up to 4 steps for multi-page forms).
        for step in range(4):
            scope, extract = _best_scope(target)
            if not extract.get("fields") and not extract.get("passwordFields"):
                log("No fillable fields found on this page.")
                break

            plan = None
            if have_ai:
                try:
                    plan = plan_actions(extract, answers, cover)
                except Exception as e:
                    log(f"AI planner unavailable ({repr(e)[:60]}); using basic fill.")

            if plan:
                ptype = plan.get("page_type", "application_form")
                log(f"Read the page (type: {ptype}). Filling {len(plan.get('actions', []))} field(s)…")
                total += _execute(scope, plan.get("actions", []), resume)
                if ptype in ("login", "signup"):
                    _handle_login(target, creds)
                    break
                if plan.get("needs_user"):
                    log("ACTION NEEDED: " + plan["needs_user"])
                nxt = plan.get("click_next", "")
                if nxt and _click_next(scope, nxt):
                    log(f"Advancing to next step via '{nxt}'…")
                    target.wait_for_timeout(2500)
                    continue
                break
            else:
                total += _fallback_fill(scope, answers, resume, cover)
                break

        if total:
            log(f"Pre-filled ~{total} field(s). Review everything, complete anything missing, "
                "and click submit yourself.")
        else:
            log("Couldn't auto-fill this page — it's open for you to complete manually.")
        log("READY")

        while True:
            try:
                if not browser.is_connected() or len(ctx.pages) == 0:
                    break
            except Exception:
                break
            time.sleep(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m jobber.apply <payload.json>", file=sys.stderr)
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as fh:
        run(json.load(fh))
