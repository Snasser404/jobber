# Deploy Jobber online (Streamlit Community Cloud)

This gives you a permanent link (`https://<name>.streamlit.app`) you can open on any
device, with your PC off. It's free.

> Reminder: the cloud version does **find → rank → tailor → preview → download** and an
> **Open application page** link. The automatic form-filling browser only runs on your PC.

## 1. Get the code on GitHub
Already done if I pushed it for you — your repo is **github.com/Snasser404/jobber** (private).
If you ever need to do it yourself:
```powershell
git add -A
git commit -m "update"
git push
```

## 2. Create the app on Streamlit Cloud
1. Go to **https://share.streamlit.io** and **Sign in with GitHub** (authorize it).
2. Click **Create app → Deploy a public app from GitHub** (works for private repos too).
3. Fill in:
   - **Repository:** `Snasser404/jobber`
   - **Branch:** `main`
   - **Main file path:** `app.py`

## 3. Add your secrets (this is what keeps your keys safe)
Click **Advanced settings → Secrets**, and paste the following — but replace each value
with the **real one from your local `.env` file**:

```toml
# AI engine — either keep Claude...
ANTHROPIC_API_KEY = "sk-ant-...    (copy from your .env)"
# ...or use a free/cheap model instead (then you can drop the Claude key):
# LLM_PROVIDER = "openai"
# LLM_BASE_URL = "https://openrouter.ai/api/v1"
# LLM_API_KEY  = "..."
# LLM_MODEL    = "deepseek/deepseek-chat-v3-0324:free"

# Job sources
ADZUNA_APP_ID  = "4ebd280d"
ADZUNA_APP_KEY = "...              (copy from your .env)"
RAPIDAPI_KEY   = "...              (JSearch key — LinkedIn/Indeed/Glassdoor)"

# Online access
JOBBER_PASSWORD = "737591274@jobber  (or change it)"
JOBBER_CLOUD    = "1"
```

## 4. Deploy
Click **Deploy** and wait ~2–5 minutes for the first build.

## 5. Use it
1. Open your `https://<name>.streamlit.app` link on any device.
2. Enter your **JOBBER_PASSWORD**.
3. **Upload your résumé** in the sidebar (the cloud app starts empty for privacy).
4. Find → rank → tailor → preview → download. Use **Open application page** to apply.

## Good to know
- **Updating:** any `git push` to `main` auto-redeploys. Editing `config.yaml` then pushing
  changes your default search.
- **Storage is temporary:** an uploaded résumé and tracked applications reset if the app
  reboots (after inactivity or a redeploy) — just re-upload your résumé when needed.
- **Changing secrets** reboots the app automatically.
- **Privacy:** the repo is private and your `.env`, résumé, and credentials are git-ignored,
  so they're never uploaded. Your keys live only in Streamlit's Secrets box.
