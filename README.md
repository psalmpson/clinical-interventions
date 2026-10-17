# Clinical interventions

A small self-hosted app for recording pharmacy clinical interventions and looking them up later.

## Run

    docker compose up -d --build

Open http://localhost:8080 (or http://<server-ip>:8080 from a phone or tablet on the same network).

## Where the data lives

`./data/interventions.db` (SQLite). Back up that folder. Each intervention is one row; the full form is stored as JSON in
the `data` column, and date, pharmacy, ward, MRN, initials, drug, condition, pharmacist and hours are also copied into columns.

## Admin PIN

Set `ADMIN_PIN` in the compose file's `environment:` block (for example `ADMIN_PIN: "change-me"`) and restart.
Deleting a record, and everything under **Settings** (backup/restore, rename a pharmacy, bulk delete), asks for the PIN.
Editing a record never does. Five wrong PINs lock the admin tools for five minutes.

## Monthly report

The **Monthly report** tab counts interventions by month and pharmacy using the layout of the official
Clinical Intervention Monthly Report. **Download Excel** fills `app/templates/clinical_intervention_monthly_report.xlsx`.

## Notes

- There is no login. This holds patient-related information, so put it behind a reverse proxy with authentication, or keep it on a trusted network.
- Edit `app/static/schema.js` to rename, add or remove any question. Then run `docker compose up -d --build` to apply the change.
- Records view: search, filter by pharmacy and date, open a record to edit, print or delete, and export the filtered list as CSV.
- Pharmacy, pharmacist and team leader names are remembered in the browser to save retyping.
