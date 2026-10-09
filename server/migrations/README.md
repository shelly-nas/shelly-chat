# Migraties

Leeg zolang shelly-chat nog niet op 1.0.0 staat: tot dan wijzigt het schema rechtstreeks in
`database/init.sql`, en begin je lokaal schoon met `docker compose down -v && docker compose up --build`.

Vanaf het moment dat er ergens data staat, wordt elke schemawijziging een bestand
`NNN_omschrijving.sql` in deze map (opeenvolgend genummerd, idempotent en additief), en wordt
`init.sql` in dezelfde commit bijgewerkt. De server past openstaande migraties toe bij het opstarten
(`app/migrations.py`, `run_migrations()`), voordat hij verzoeken aanneemt.
