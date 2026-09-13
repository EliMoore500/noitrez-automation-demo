# Noitrez AI Lead Automation Demo

## What it does

1. Accepts a website lead.
2. Sends the lead to OpenAI for classification.
3. Classifies the lead as Hot, Warm, or Cold.
4. Determines urgency and service type.
5. Generates a one-sentence business summary.
6. Generates a professional customer reply.
7. Stores the lead in a local SQLite database.
8. Optionally emails the business automatically through SMTP.

## Windows setup

Open PowerShell in this folder.

```powershell
py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

`.env.example` is reference-only and is not loaded by the application. Create the actual runtime file first:

```powershell
Copy-Item .env.example .env
```

Then edit `.env` and replace:

`PASTE_YOUR_OPENAI_API_KEY_HERE`

with your OpenAI API key.

The local app loads settings from `.env`. Keep `.env` private and never commit it; deployment platforms such as Render should receive these same values through their environment-variable settings.

Start the app:

```powershell
python app.py
```

Open:

http://127.0.0.1:5000

## Email

The demo works without SMTP. It stores the lead and displays the generated response.

To turn on automatic business notification emails, set `SMTP_ENABLED=true` and fill in the SMTP settings in `.env`.

For a Gmail alias, set `SMTP_USERNAME` to the owning Google account, such as `elijah@noitrez.com`, and use an App Password generated for that account. Set `SMTP_FROM` to the alias, such as `hello@noitrez.com`, after adding and verifying it as a Send mail as address in Gmail. Set `CUSTOMER_REPLY_ENABLED=true` to email the AI-generated reply to the customer after the staff notification succeeds.

If the hosting service reports `Network is unreachable` while connecting to Gmail on port 587, use Gmail SSL instead: set `SMTP_PORT=465`, `SMTP_USE_TLS=false`, and `SMTP_USE_SSL=true` in the deployment environment.

Do not put `.env` in GitHub. It is already listed in `.gitignore`.

## GitHub

After testing:

```powershell
git init
git add .
git commit -m "Create Noitrez AI lead automation demo"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/noitrez-automation-demo.git
git push -u origin main
```

Create the GitHub repository first, with the exact name `noitrez-automation-demo`, and do NOT initialize it with a README, .gitignore, or license because those files already exist locally.
