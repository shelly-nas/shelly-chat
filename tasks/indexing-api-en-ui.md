# Indexering via de UI triggeren

## Probleemomschrijving

De indexering is momenteel alleen te starten via de CLI op de hostmachine (`python -m indexing.indexer /pad/naar/documenten`). Dit werkt niet vanuit Docker en is ontoegankelijk voor gebruikers zonder technische achtergrond. Er is geen manier om vanuit de webinterface documenten toe te voegen of de index bij te werken.

**Gewenste situatie**: een gebruiker kan via de chat-interface een herindexering starten of nieuwe documenten aanbieden — zonder terminal toegang.

## Ontwerpkeuzes (te bepalen vóór implementatie)

### Interface-optie A — Sync-knop (eenvoudig)

Een knop die de indexering van de vaste documentenmap (`/app/data`) opnieuw triggert. Geen bestandsupload, de gebruiker plaatst documenten zelf in de map.

- **Pro**: minimale implementatie, geen opslagcomplexiteit
- **Con**: gebruiker heeft nog steeds directe toegang tot de container of een gemount volume nodig om bestanden toe te voegen

### Interface-optie B — Uploadinterface

Drag-and-drop of bestandskiezer waarmee de gebruiker PDFs of tekstbestanden uploadt. De backend slaat ze op in `/app/data` en start de indexering.

- **Pro**: volledig zelfbedienend, geen terminaltoegang nodig
- **Con**: meer implementatiewerk, bestandsbeheer (overschrijven, opruimen) moet worden uitgedacht

### Interface-optie C — Beide (aanbevolen)

Uploadinterface + aparte "Herindexeer alles"-knop voor een volledige re-sync. Combineert flexibiliteit met eenvoud.

**Aanbeveling**: begin met optie A (sync-knop) als losse taak; voeg optie B toe als vervolgstap.

---

## Ontwikkeltaken

### [ ] Taak 1: Indexering blootleggen als API-endpoint

**Beschrijving**: Voeg een `/api/index` endpoint toe aan de generating-service dat de indexeringspipeline als achtergrondtaak uitvoert. De indexering draait als een subprocess of via een directe import van `indexing.indexer`.

**Acceptatiecriteria**:
- `POST /api/index` start een indexeringstaak en geeft direct een taak-ID terug
- `GET /api/index/status` geeft de huidige status terug: `idle`, `running`, `done`, `error` — inclusief een voortgangsbericht
- Slechts één indexeringtaak tegelijk (concurrent verzoek geeft 409 terug)
- Logregels van de indexer zijn opvraagbaar via de statusendpoint (laatste N regels)
- De documentenmap is configureerbaar via de bestaande `DOCSTORE_PATH`-omgevingsvariabele of een aparte `DATA_DIR`

**Te maken/bewerken bestanden**:
- `generating/app.py` — voeg `/api/index` en `/api/index/status` toe
- `generating/indexing_runner.py` — nieuw: wrapper die `indexing.indexer` aanroept als subprocess en de uitvoer buffert

**Technische noot**: gebruik `asyncio.create_subprocess_exec` of `threading.Thread` zodat de FastAPI event loop niet blokkeert. Houd de processtatus bij in een module-level variabele (vergelijkbaar met de sessie-opslag in `app.py`).

---

### [ ] Taak 2: Voeg een sync-knop toe aan de frontend (optie A)

**Beschrijving**: Voeg een knop toe aan de chat-interface (bijvoorbeeld in het instellingenpaneel of in de header naast "Nieuw gesprek") waarmee de gebruiker een herindexering kan starten. Toon voortgang en uitkomst.

**Acceptatiecriteria**:
- Knop is zichtbaar en toegankelijk vanuit de hoofdinterface
- Na klikken: knop toont een laadstatus en is uitgeschakeld zolang de indexering loopt
- Pollt `GET /api/index/status` elke 2 seconden totdat de taak klaar is
- Toont het laatste voortgangsbericht uit de statusrespons
- Bij afronden: groene bevestiging of rode foutmelding — na 5 seconden verdwijnt de melding
- Werkt niet als er tegelijkertijd een chatverzoek loopt (knoppen zijn van elkaar onafhankelijk maar de statusmelding maakt de situatie duidelijk)

**Te maken/bewerken bestanden**:
- `chat-app/src/components/SettingsPanel.tsx` — voeg sync-knop en statusweergave toe aan het instellingenpaneel
- `chat-app/src/app/api/index/route.ts` — nieuw: Next.js proxy naar `POST /api/index`
- `chat-app/src/app/api/index/status/route.ts` — nieuw: Next.js proxy naar `GET /api/index/status`

**UX-noot**: de meest logische plek is het instellingenpaneel (tandwiel-icoon), onder de systeemstatus. Zo blijft de hoofdinterface opgeruimd en is de functie toch bereikbaar voor beheerders.

---

### [ ] Taak 3: Uploadinterface (optie B — vervolgstap)

**Beschrijving**: Voeg een bestandsuploadflow toe waarmee de gebruiker één of meerdere PDFs of tekstbestanden uploadt. De backend slaat ze op in de documentenmap en start automatisch een herindexering.

**Acceptatiecriteria**:
- Upload via drag-and-drop of bestandskiezer (maximaal N MB per bestand, configureerbaar)
- Toegestane bestandstypen: `.pdf`, `.txt`, `.md` (zelfde als wat de indexer ondersteunt)
- Na upload: direct doorsturen naar `POST /api/upload` en daarna `POST /api/index` triggeren
- Voortgang per bestand tonen (geüpload / aan het indexeren / klaar / fout)
- Bestandsnamen die al bestaan: overschrijven met bevestigingsdialoog
- Geüploade bestanden blijven beschikbaar na herstart (volume-mount in `docker-compose.yml`)

**Te maken/bewerken bestanden**:
- `generating/app.py` — voeg `POST /api/upload` toe (multipart form-data, slaat op in `DATA_DIR`)
- `chat-app/src/components/UploadPanel.tsx` — nieuw: uploadcomponent met drag-and-drop
- `chat-app/src/app/api/upload/route.ts` — nieuw: Next.js proxy naar `POST /api/upload`
- `docker-compose.yml` — zorg dat de `data/`-map als volume is gemount in de generating-container

---

## Kwaliteitseisen

- [ ] Een lopende indexering blokkeert geen chatverzoeken (asynchroon)
- [ ] Meerdere gelijktijdige index-verzoeken worden netjes geweigerd (409)
- [ ] De frontend toont altijd duidelijk of de indexering loopt, geslaagd is, of mislukt is
- [ ] De bestaande CLI (`python -m indexing.indexer`) blijft gewoon werken
- [ ] Geen extra Python-dependencies — gebruik `asyncio` en de bestaande `indexing`-module
- [ ] Geüploade bestanden worden opgeslagen buiten de container (volume) zodat ze niet verloren gaan bij een herstart

## Technische aantekeningen

**Integratiepunten**:
- `indexing/indexer.py` — `run_indexing_pipeline()` is het startpunt voor taak 1
- `generating/app.py` — sessie- en statuspatroon als referentie voor de taakvariabele
- `chat-app/src/components/SettingsPanel.tsx` — bestaand instellingenpaneel als plek voor de sync-knop
- `docker-compose.yml` — `volumes`-sectie voor de `data/`-map (taak 3)

**Volgorde**: implementeer taak 1 eerst — zonder werkende API heeft de frontend niets om aan te koppelen. Taak 2 en 3 kunnen daarna onafhankelijk van elkaar worden opgepakt.
