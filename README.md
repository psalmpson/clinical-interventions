# Clinical interventions

A small self-hosted app for recording pharmacy clinical interventions and looking them up later.

## Run

    docker compose up -d --build

Open http://localhost:3400 (or http://<server-ip>:3400 from a phone or tablet on the same network).

## Where the data lives

`./data/interventions.db` (SQLite). Back up that folder. Each intervention is one row; the full form is stored as JSON in
the `data` column, and date, pharmacy, ward, MRN, initials, drug, condition, pharmacist and hours are also copied into columns.

## Notes

- There is no login. This holds patient-related information, so put it behind a reverse proxy with authentication, or keep it on a trusted network.
- Edit `app/static/schema.js` to rename, add or remove any question. Then run `docker compose up -d --build` to apply the change.
- Records view: search, filter by pharmacy and date, open a record to edit, print or delete, and export the filtered list as CSV.
- Pharmacy, pharmacist and team leader names are remembered in the browser to save retyping.
