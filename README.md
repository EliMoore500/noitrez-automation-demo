# Noitrez HVAC Workflow Preview

## What it does

The public demo has three fictional HVAC inquiries and a live workflow preview. Selecting a sample only prefills the form; it makes no network request until the visitor submits. The live preview sends the submitted name, service, and message to OpenAI to suggest priority and follow-up. Email and phone are validated by the demo but are not sent to the model. The app does not store submissions or send email.

The marketing site's audit form opens a prefilled email draft to `sales@noitrez.com`. The visitor reviews it and presses Send in their email app; the website does not submit or store their form details.

## Windows setup

Open PowerShell in this folder.

```powershell
py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 to preview the sample scenarios.

## Workflow preview configuration

Set `OPENAI_API_KEY` in the Render service environment (or local `.env`) to enable generated workflow previews. `OPENAI_MODEL` is optional and defaults to `gpt-4o-mini`. Never commit `.env` or API keys. The preview endpoint is limited to five requests per IP per 15-minute window.

## Contact form

The form uses a `mailto:` draft addressed to `sales@noitrez.com`. Visitors must review and send it in their own email app. No email service credentials or server-side contact endpoint are required.

## Privacy and old demo data

The public demo offers fictional sample inquiries and a generated workflow preview. For a live preview, name, service, and message are sent to OpenAI; email and phone are not sent to OpenAI. Submissions are not stored or emailed by this app. Use fictional demo details, not sensitive or actual customer information. Contact form details on the marketing site remain in the visitor's email app until they choose to send them. If `data/leads.db` contains old demo submissions, the app no longer exposes them; review and remove that file manually only after confirming you no longer need its contents.

## Checks

Run the contact endpoint regression tests with:

```powershell
python -m unittest discover -s tests -v
```
