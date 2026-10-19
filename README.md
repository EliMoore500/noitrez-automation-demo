# Noitrez HVAC Workflow Preview

## What it does

The public demo uses three fictional HVAC scenarios to show an example lead priority, recommended next action, business summary, and draft customer reply. The sample buttons make no network request and collect no visitor information.

The marketing site's audit form posts to `/api/contact`. The service validates the request and emails it to `sales@noitrez.com` by default; after submission, the visitor also gets a prefilled optional email draft. The form submission is not stored in the application database. Public lead-analysis, listing, update, and delete routes are disabled.

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

## Contact email configuration

The homepage form requires SMTP configuration in the Render dashboard or local `.env` for the automatic notification. The recipient defaults to `sales@noitrez.com`:

- `SMTP_ENABLED=true`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`
- `SMTP_FROM` (optional; defaults to `SMTP_USERNAME`)
- `CONTACT_NOTIFICATION_EMAIL=sales@noitrez.com`
- `CONTACT_ALLOWED_ORIGINS=https://noitrez.com,https://www.noitrez.com`

For a Gmail alias, use the owning Google account as `SMTP_USERNAME` and an App Password generated for that account. Set `SMTP_FROM` to a verified "Send mail as" alias. If SMTP is unavailable, the form reports the failure and keeps the prefilled email draft available as a fallback.

If SMTP on port 587 is unreachable, use Gmail SSL with `SMTP_PORT=465`, `SMTP_USE_TLS=false`, and `SMTP_USE_SSL=true`.

The contact endpoint allows five attempts per IP per 15-minute window. This limiter is in memory and assumes the Render service's configured single worker; use a shared rate-limit store before scaling to multiple workers or instances. Never commit `.env` or SMTP credentials; `.env` is listed in `.gitignore`.

## Privacy and old demo data

The public demo no longer accepts visitor inquiries. The marketing contact form is emailed and is not stored by the application. If `data/leads.db` contains old demo submissions, the app no longer exposes them; review and remove that file manually only after confirming you no longer need its contents.

## Checks

Run the contact endpoint regression tests with:

```powershell
python -m unittest discover -s tests -v
```
