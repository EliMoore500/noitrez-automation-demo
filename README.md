# Noitrez HVAC Workflow Preview

## What it does

The public demo uses three fictional HVAC scenarios to show an example lead priority, recommended next action, business summary, and draft customer reply. The sample buttons make no network request and collect no visitor information.

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

## Contact form

The form uses a `mailto:` draft addressed to `sales@noitrez.com`. Visitors must review and send it in their own email app. No email service credentials or server-side contact endpoint are required.

## Privacy and old demo data

The public demo uses fictional sample scenarios. Contact information remains in the visitor's email app until they choose to send it. If `data/leads.db` contains old demo submissions, the app no longer exposes them; review and remove that file manually only after confirming you no longer need its contents.

## Checks

Run the contact endpoint regression tests with:

```powershell
python -m unittest discover -s tests -v
```
