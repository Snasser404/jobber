"""Jobber — Streamlit UI. Run with:  streamlit run app.py"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import streamlit as st

from jobber import config, profile as profile_mod, store, analyze, auth, llm
from jobber.sources import fetch_all
from jobber.models import Job, RankedJob, TailoredApplication
from jobber import rank as rank_mod
from jobber import tailor as tailor_mod

st.set_page_config(page_title="Jobber", page_icon="🎯", layout="wide")
auth.require_auth()   # password gate — only active when JOBBER_PASSWORD is set (e.g. shared online)
store.init()

BASE_CFG = config.load_config()
PROFILE_DIR = config.abspath("data/profile")


# ---------------------------------------------------------------- helpers
@st.cache_data(show_spinner=False)
def _resume_text(path: str, mtime: float) -> str:
    return profile_mod.read_resume_text(path)


def resume_text_for(path: str) -> str:
    ap = config.abspath(path)
    if not ap.exists():
        return ""               # no résumé yet (e.g. fresh cloud deploy → upload first)
    return _resume_text(str(ap), ap.stat().st_mtime)


def _score_badge(score: int) -> str:
    if score >= 85:
        return f"🟢 **{score}**"
    if score >= 70:
        return f"🟡 **{score}**"
    if score > 0:
        return f"🟠 **{score}**"
    return "⚪️ —"


def _file_bytes(path: str) -> bytes:
    p = Path(path)
    return p.read_bytes() if p.exists() else b""


def _open_application(job: Job, tailored: TailoredApplication, prof: dict, cover_text: str) -> str:
    resume = tailored.resume_docx_path or prof["resume_path"]
    payload = {
        "apply_url": job.best_apply_url,
        "applicant": prof.get("applicant", {}),
        "resume_path": str(config.abspath(resume)),
        "cover_letter": cover_text,
        "cover_letter_path": tailored.cover_letter_path,
    }
    tmp = config.ROOT / "data" / f"_apply_{job.id}.json"
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    log_path = config.ROOT / "data" / f"_apply_{job.id}.log"
    logf = open(log_path, "w", encoding="utf-8")
    # Force the child process to emit UTF-8 so the log stays valid (Windows defaults to cp1252).
    child_env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    subprocess.Popen([sys.executable, "-X", "utf8", "-m", "jobber.apply", str(tmp)],
                     cwd=str(config.ROOT), stdout=logf, stderr=logf, env=child_env)
    logf.close()
    return str(log_path)


def _apply_derived(resume_path: str):
    """Read the resume, ask Claude for search terms, seed the sidebar widgets."""
    d = analyze.derive_search_profile(resume_text_for(resume_path))
    if d["keywords"]:
        st.session_state["kw_text"] = "\n".join(d["keywords"])
    if d["location"]:
        st.session_state["loc_text"] = d["location"]
    st.session_state["remote_chk"] = bool(d["remote_ok"])
    st.session_state["derived_focus"] = d["focus"]


# ---------------------------------------------------------------- state
st.session_state.setdefault("ranked", [])     # list[RankedJob]
st.session_state.setdefault("tailored", {})    # job_id -> TailoredApplication
st.session_state.setdefault("stats", {})

has_ai = llm.is_configured()
find = False

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🎯 Jobber")
    st.caption("Find → rank → tailor → review → apply")

    st.write(f"AI engine ({llm.label()}):", "✅ ready" if has_ai else "❌ no key")
    st.write("Adzuna jobs:", "✅ on" if config.has_adzuna_keys() else "➖ off (optional)")

    # ---- résumé (drives everything: search, ranking, tailoring) ----
    st.subheader("📄 Your résumé")
    up = st.file_uploader("Upload a résumé (.docx)", type=["docx"],
                          help="The search, fit-scoring, and tailoring all follow this résumé.")
    if up is not None and st.session_state.get("uploaded_name") != up.name:
        dest = PROFILE_DIR / up.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(up.getbuffer())
        st.session_state["resume_path"] = str(dest)
        st.session_state["uploaded_name"] = up.name
        st.session_state["ranked"] = []          # new résumé → clear old results
        st.session_state["tailored"] = {}
        if has_ai:
            st.session_state["_pending_analyze"] = True   # auto-retarget the search
        st.rerun()

    active_resume = st.session_state.get("resume_path") or BASE_CFG.get("resume_path")
    has_resume = config.abspath(active_resume).exists()
    if has_resume:
        st.caption(f"Active: **{Path(active_resume).name}**")
    else:
        st.warning("⬆️ Upload your résumé to begin.")

    if st.button("🔁 Suggest search terms from this résumé",
                 disabled=not has_ai or not has_resume, use_container_width=True):
        st.session_state["_pending_analyze"] = True

    # Run analysis (must happen BEFORE the keyword widgets are created).
    if st.session_state.pop("_pending_analyze", False) and has_ai:
        with st.spinner("Reading your résumé and retargeting the search…"):
            try:
                _apply_derived(active_resume)
            except Exception as e:
                st.warning(f"Couldn't analyze résumé: {e}")

    # ---- search settings (seeded from config, overridable) ----
    st.session_state.setdefault("kw_text", "\n".join(BASE_CFG.get("search", {}).get("keywords", [])))
    st.session_state.setdefault("loc_text", BASE_CFG.get("search", {}).get("location", ""))
    st.session_state.setdefault("remote_chk", bool(BASE_CFG.get("search", {}).get("remote_ok", True)))

    st.subheader("🎯 Search")
    if st.session_state.get("derived_focus"):
        st.info("🧭 " + st.session_state["derived_focus"])
    st.text_area("Keywords (one per line)", key="kw_text", height=150)
    st.text_input("Location", key="loc_text")
    st.checkbox("Include remote roles", key="remote_chk")

    find = st.button("🔎 Find & rank jobs", type="primary", use_container_width=True,
                     disabled=not has_resume)
    if st.session_state["stats"]:
        st.caption("Last pull: " + ", ".join(f"{k}:{v}" for k, v in st.session_state["stats"].items() if v))

    if not has_ai:
        st.warning(
            "No AI key set — needed for ranking, tailoring & résumé analysis. Use Claude, or a "
            "cheaper/free model (OpenRouter free DeepSeek, DeepSeek, Gemini, Groq). "
            "See `.env.example` for one-line setups, then restart."
        )


# ---------------------------------------------------------------- effective config + profile
keywords = [ln.strip() for ln in st.session_state["kw_text"].splitlines() if ln.strip()]
eff_cfg = copy.deepcopy(BASE_CFG)
eff_cfg["search"]["keywords"] = keywords
eff_cfg["search"]["location"] = st.session_state["loc_text"].strip()
eff_cfg["search"]["remote_ok"] = st.session_state["remote_chk"]
eff_cfg["resume_path"] = active_resume

profile = {
    "resume_text": resume_text_for(active_resume),
    "applicant": BASE_CFG.get("applicant", {}),
    "search": eff_cfg["search"],
    "resume_path": active_resume,
}


# ---------------------------------------------------------------- find + rank
if find:
    min_score = int(BASE_CFG.get("filters", {}).get("min_score", 0)) if has_ai else 0
    with st.status("Searching job sources…", expanded=True) as status:
        def on_src(name, n):
            st.write(f"• {name}: {n} jobs")
        jobs, stats = fetch_all(eff_cfg, on_progress=on_src)
        st.session_state["stats"] = stats
        st.write(f"**{len(jobs)} unique jobs found** for: {', '.join(keywords) or '(no keywords)'}")

        if has_ai and jobs:
            status.update(label="Scoring fit with Claude…")
            bar = st.progress(0.0)
            def on_rank(i, total, rj):
                bar.progress(i / total, text=f"Scored {i}/{total}: {rj.job.title[:40]} → {rj.score}")
            ranked = rank_mod.rank_jobs(jobs, profile, min_score=min_score, on_progress=on_rank)
            st.session_state["ranked"] = ranked
            status.update(label=f"Done — {len(ranked)} jobs scored ≥ {min_score}.", state="complete")
        else:
            st.session_state["ranked"] = [RankedJob(job=j, score=0, summary="") for j in jobs]
            status.update(label="Done (ranking disabled).", state="complete")


# ---------------------------------------------------------------- main
tab_find, tab_track = st.tabs(["🔎 Find & apply", "📋 Tracked applications"])

with tab_find:
    ranked: list[RankedJob] = st.session_state["ranked"]
    statuses = store.status_map()

    if not ranked:
        st.info("Upload a résumé (or keep the default), then click **Find & rank jobs** in the sidebar. "
                "Uploading a new résumé automatically retargets the search to match it.")
    else:
        st.subheader(f"{len(ranked)} matches")
        for rj in ranked:
            job = rj.job
            jid = job.id
            done = statuses.get(jid)
            tag = f" · ✅ {done}" if done else ""
            header = f"{_score_badge(rj.score)} — **{job.title}** · {job.company}{tag}"
            with st.expander(header, expanded=False):
                meta = [job.location or "—", f"source: {job.source}"]
                if job.remote:
                    meta.append("🌐 remote")
                if job.salary:
                    meta.append(f"💰 {job.salary}")
                st.caption(" · ".join(meta))
                if rj.summary:
                    st.write(rj.summary)

                cols = st.columns(2)
                if rj.reasons:
                    cols[0].markdown("**Why it fits**")
                    for r in rj.reasons:
                        cols[0].markdown(f"- ✅ {r}")
                if rj.concerns:
                    cols[1].markdown("**Watch-outs**")
                    for c in rj.concerns:
                        cols[1].markdown(f"- ⚠️ {c}")

                if st.toggle("📄 Show full job description", key=f"desc_{jid}"):
                    st.text_area("job description", job.description[:6000] or "(no description)",
                                 height=240, disabled=True, key=f"descbox_{jid}",
                                 label_visibility="collapsed")
                st.markdown(f"🔗 [View original posting]({job.url})")

                st.divider()
                # ---- tailoring ----
                tailored = st.session_state["tailored"].get(jid)
                if st.button("✍️ Tailor résumé & write cover letter", key=f"tailor_{jid}",
                             disabled=not has_ai):
                    with st.spinner("Claude is tailoring your application…"):
                        tailored = tailor_mod.generate(rj, profile, eff_cfg)
                        st.session_state["tailored"][jid] = tailored
                        store.save_prepared(rj, tailored)
                    st.rerun()

                if tailored:
                    st.success("Tailored materials ready — preview below, then apply.")
                    st.markdown("**Tailored summary (new ‘About Me’):**")
                    st.info(tailored.tailored_summary)
                    if tailored.resume_changes:
                        st.markdown("**What changed in the résumé (and why):**")
                        for ch in tailored.resume_changes:
                            st.markdown(f"- {ch}")

                    st.markdown("**Cover letter** (edit freely — your edits are used when applying):")
                    cover_text = st.text_area("cover letter", value=tailored.cover_letter,
                                              height=280, key=f"cover_{jid}",
                                              label_visibility="collapsed")

                    dl1, dl2 = st.columns(2)
                    dl1.download_button("⬇️ Tailored résumé (.docx)",
                                        _file_bytes(tailored.resume_docx_path),
                                        file_name=Path(tailored.resume_docx_path).name,
                                        key=f"dlr_{jid}", use_container_width=True)
                    dl2.download_button("⬇️ Cover letter (.docx)",
                                        _file_bytes(tailored.cover_letter_path),
                                        file_name=Path(tailored.cover_letter_path).name,
                                        key=f"dlc_{jid}", use_container_width=True)

                    st.markdown(f"**Where it will apply:** [{job.best_apply_url}]({job.best_apply_url})")
                    if config.is_cloud():
                        st.link_button("🌐 Open application page", job.best_apply_url,
                                       type="primary", use_container_width=True)
                        st.caption("On this hosted version you fill & submit on the site yourself — "
                                   "download your tailored résumé + cover letter above. "
                                   "For automatic form-filling, run Jobber on your PC.")
                        cc1, cc2 = st.columns(2)
                        if cc1.button("✅ Mark as applied", key=f"applied_{jid}", use_container_width=True):
                            store.set_status(jid, "applied")
                            st.rerun()
                        if cc2.button("🚫 Skip", key=f"skip_{jid}", use_container_width=True):
                            store.set_status(jid, "skipped")
                            st.rerun()
                    else:
                        b1, b2, b3 = st.columns(3)
                        if b1.button("🌐 Open & pre-fill application", key=f"apply_{jid}",
                                     type="primary", use_container_width=True):
                            st.session_state[f"applog_{jid}"] = _open_application(job, tailored, profile, cover_text)
                            st.toast("Opening browser → navigating to the form → pre-filling. Watch the new window.")
                        if b2.button("✅ Mark as applied", key=f"applied_{jid}", use_container_width=True):
                            store.set_status(jid, "applied")
                            st.rerun()
                        if b3.button("🚫 Skip", key=f"skip_{jid}", use_container_width=True):
                            store.set_status(jid, "skipped")
                            st.rerun()
                        st.caption(
                            "ℹ️ Direct company forms (Greenhouse/Lever) fill completely. "
                            "Listing/aggregator links (Adzuna, LinkedIn) open the posting and the assistant "
                            "clicks **Apply** to reach the real form — some sites require you to log in first, "
                            "then it fills what it can. It never submits; you do the final review."
                        )
                        if st.session_state.get(f"applog_{jid}"):
                            if st.toggle("🪵 Show assistant log", key=f"showlog_{jid}"):
                                lp = Path(st.session_state[f"applog_{jid}"])
                                st.code(lp.read_text(encoding="utf-8", errors="replace").strip()
                                        if lp.exists() else "(starting…)")
                                if st.button("↻ Refresh log", key=f"reflog_{jid}"):
                                    st.rerun()


with tab_track:
    apps = store.list_applications()
    if not apps:
        st.info("Nothing tracked yet. Tailor and apply to a job to see it here.")
    else:
        st.subheader(f"{len(apps)} tracked")
        for a in apps:
            st.markdown(
                f"**{a['title']}** · {a['company']} — `{a['status']}` "
                f"(fit {a['score']}) · [posting]({a['url']})"
            )
