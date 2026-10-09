# Document Indexering

Verwerkt documenten tot een hiërarchische vectorindex voor de RAG-pipeline. Haalt content op uit GitLab (wiki-pagina's of repository-bestanden) via de GitLab REST API. Binaire bestandsformaten (PDF, DOCX) worden omgezet naar platte tekst via `document_parser.py`.

Opnieuw uitvoeren werkt **incrementeel**: alleen nieuwe en gewijzigde documenten worden opnieuw geëmbed. Ongewijzigde documenten worden overgeslagen (geen embedding-aanroepen). Verwijderde documenten worden automatisch opgeruimd uit Qdrant en de docstore.

## Ophaalstrategie: Hiërarchisch Auto-Merging

Bij elke gebruikersvraag doorloopt de pipeline vier stappen:

1. **Embedding** — de vraag wordt omgezet naar een vector via `EMBED_MODEL`.
2. **Similarity search** — Qdrant zoekt de `RETRIEVAL_TOP_K` meest gelijkende child nodes op.
3. **Auto-merging** — voor elke groep child nodes die van dezelfde parent afkomstig zijn, controleert `AutoMergingRetriever` of de verhouding opgehaalde children / totaal aantal children de `AUTOMERGE_THRESHOLD` overschrijdt. Zo ja, worden de children vervangen door de volledige parent node uit `docstore.json`. Dit geeft de LLM meer context zonder de zoekprecisie te verliezen.
4. **Reranking** — de gecombineerde set nodes (parents + niet-gemergde children) wordt door de reranker gesorteerd op relevantie. Alleen de top `RERANKER_TOP_N` nodes gaan als context naar het LLM.

Documenten zijn bij het indexeren opgesplitst in twee niveaus:

- **Child Nodes (`CHILD_CHUNK_SIZE` tokens)** — opgeslagen als vectoren in Qdrant; worden gebruikt voor de similarity search.
- **Parent Nodes (`PARENT_CHUNK_SIZE` tokens)** — opgeslagen in `docstore.json`; worden alleen opgehaald als de merge-drempel bereikt is.

`CHILD_CHUNK_SIZE` staat standaard op `PARENT_CHUNK_SIZE // 4`. Afwijken van deze verhouding geeft een waarschuwing bij het starten van de indexer.

```mermaid
flowchart
    Q[Gebruikersvraag] -->|embed via EMBED_MODEL| V[Query Vector]
    V -->|similarity search<br>top RETRIEVAL_TOP_K| QDRANT[(Qdrant<br>chunks_child)]
    QDRANT --> NODES[Child Nodes]
    NODES -->|per parent-groep| AM{AutoMerging<br>AUTOMERGE_THRESHOLD?}
    AM -->|ja| P[Parent Node<br>uit docstore.json]
    AM -->|nee| C[Child Node<br>blijft individueel]
    P & C -->|reranking<br>top RERANKER_TOP_N| RR[Reranker]
    RR -->|context| LLM[LLM]
```

## Embeddingmodel: qwen3-embedding

`qwen3-embedding:latest` is een dense embeddingmodel, gekozen vanwege:

- **Meertalige kwaliteit**: Sterke prestaties op Nederlands en andere niet-Engelse tekst
- **4096-dimensionale vectoren**: Hoger dimensionale ruimte maakt expressievere similariteitsonderscheidingen mogelijk
- **MTEB-benchmarkresultaten**: Behoort consistent tot de beste ophaalmodellen ([MTEB multilingual leaderboard](https://github.com/QwenLM/Qwen3-Embedding))

## Indexeringspipeline

Alle geconfigureerde bronnen worden in één pass verwerkt: eerst worden alle documenten opgehaald van WikiLab wiki's en repositories, daarna worden ze in één keer geëmbed en geüpsert. Dit voorkomt dat het embeddingmodel meerdere keren geladen en ontladen wordt.

Na het embedden ontlaadt de indexer het embeddingmodel automatisch via de Ollama HTTP API (`keep_alive=0`), vóórdat de indexeringslock wordt vrijgegeven.

Tijdens de hele run houdt de indexer een exclusieve `flock` op `vector-db/.indexing.lock`, zodat een gelijktijdige CLI-run of een docstore-herlaad door de `generating`-service nooit met dezelfde bestanden kan racen.

```mermaid
flowchart
    GL_W[GitLab Wiki<br>/-/wikis] -->|gitlab_wiki_fetcher| B[Ruwe documenten]
    GL_R[GitLab Repository<br>.md .adoc .pdf .docx .doc] -->|gitlab_repo_fetcher| B
    B -->|document_parser<br>voor PDF / DOCX| B
    QDRANT_H[(Qdrant chunks_child<br>content_hash payloads)] -->|scroll + classify_documents| B
    B -->|nieuw of gewijzigd| C
    B -->|ongewijzigd| SKIP[Overgeslagen]
    C[Te indexeren documenten] -->|HierarchicalNodeParser| PAR[Parent Nodes<br>PARENT_CHUNK_SIZE tokens]
    PAR --> D[Child Nodes<br>CHILD_CHUNK_SIZE tokens]
    D -->|EMBED_MODEL| E[4096-dim vectoren]
    E -->|VectorStoreIndex upsert<br>incl. content_hash payload| F[(Qdrant<br>QDRANT_CHILD_COLLECTION)]
    PAR -->|SimpleDocumentStore, atomair| G[(docstore.json)]
    E -->|keep_alive=0| UNL[Model ontladen]
    D -->|_extract_abbreviations| ABR[(abbreviations.json)]
```

Zie [`vector-db/README.md`](../vector-db/README.md) voor opslagdetails.

## Gebruik

### 1. Stel de bronnen in via `.env`

Voeg per bron een URL toe, komma-gescheiden:

```bash
GITLAB_WIKI_URLS='
https://gitlab.example.com/group/project-a/-/wikis,
https://gitlab.example.com/group/project-b/-/wikis
'

GITLAB_REPO_URLS='
https://gitlab.example.com/group/project-a,
https://gitlab.example.com/group/project-b/-/tree/main/docs
'

GITLAB_PAT=glpat-xxxxxxxxxxxxxxxxxxxx
```

Repository-URLs kunnen een tree-pad bevatten (`/-/tree/<branch>/<pad>`). De branch en het pad worden automatisch uitgelezen — de `branch`- en `path_filter`-parameters zijn dan niet meer nodig.

Ondersteunde bestandstypen:

| Extensie | Verwerking |
|----------|------------|
| `.md`    | Directe tekst, markdown bewaard |
| `.adoc`  | Directe tekst, AsciiDoc bewaard |
| `.pdf`   | Tekst extractie via `pdfminer.six` (`document_parser.parse_pdf_bytes`) |
| `.docx`  | Tekst extractie via `python-docx` (`document_parser.parse_docx_bytes`) |
| `.doc`   | Tekst extractie via `python-docx` (best-effort voor legacy formaat) |

### 2. Start de indexer

Indexeren gaat via de **Instellingen** (⚙) in de chat-interface. Er zijn drie acties beschikbaar:

| Knop | Beschrijving |
|------|-------------|
| **Herindexeer** | Incrementele sync — alleen nieuwe en gewijzigde documenten worden geëmbed |
| **Volledig** | Verwijdert de bestaande index volledig en indexeert alles opnieuw; wijzigingen aan `PARENT_CHUNK_SIZE`, `CHILD_CHUNK_SIZE` of `EMBED_MODEL` worden ook automatisch gedetecteerd via de versiestempel |
| **Afkortingen** | Herbouwt alleen `abbreviations.json` vanuit de bestaande docstore, zonder opnieuw te indexeren |

## GitLab-authenticatie

GitLab-bronnen worden beveiligd via een **Personal Access Token (PAT)**. Voor private projecten is een PAT verplicht; publieke projecten kunnen zonder worden benaderd.

Maak een PAT aan via **GitLab → User Settings → Access Tokens** met de volgende scopes:

| Bron | Vereiste scope |
|------|----------------|
| Wiki | `read_wiki` |
| Repository | `read_repository` |

Sla het token op als `GITLAB_PAT` in `.env`. **Commit het token nooit naar versiebeheer.**

## source_url metadata

Elk document dat via GitLab wordt geïndexeerd, krijgt een `source_url` in de metadata:

| Bron | URL-formaat |
|------|-------------|
| Wiki-pagina | `https://gitlab.example.com/group/project/-/wikis/<slug>` |
| Repository-bestand | `https://gitlab.example.com/group/project/-/blob/<branch>/<pad>` |

De chatbot-frontend gebruikt `source_url` om de "Document openen"-knop direct naar het originele GitLab-bestand te laten linken. Als er geen `source_url` aanwezig is (lokale bestanden), opent de knop via het bestandssysteem.

## Configuratie

Alle instellingen komen uit het `.env`-bestand in de projectroot:

### Indexeringsparameters

| Variabele                 | Standaard                 | Beschrijving                                                             |
| ------------------------- | ------------------------- | ------------------------------------------------------------------------ |
| `EMBED_MODEL`             | `qwen3-embedding:latest`  | Ollama-embeddingmodel                                                    |
| `OLLAMA_BASE_URL`         | `http://localhost:11434`  | URL van de Ollama-server                                                 |
| `QDRANT_URL`              | `http://localhost:6333`   | URL van de Qdrant-server                                                 |
| `QDRANT_CHILD_COLLECTION` | `chunks_child`            | Qdrant-collectie voor child node vectoren                                |
| `DOCSTORE_PATH`           | `vector-db/docstore.json` | Uitvoerpad voor de LlamaIndex-documentopslag; de indexeringslock staat in dezelfde map als `.indexing.lock` |
| `PARENT_CHUNK_SIZE`       | `1500`                    | Tokengrootte van parent chunks                                           |
| `CHILD_CHUNK_SIZE`        | `375` (`PARENT // 4`)     | Tokengrootte van child chunks; afwijken van 1/4 geeft een waarschuwing  |
| `PARENT_CHUNK_OVERLAP`    | `300`                     | Overlapping in tokens tussen opeenvolgende parent chunks                 |
| `AUTOMERGE_THRESHOLD`     | `0.5`                     | Minimale verhouding (0.0–1.0) child nodes per parent om te mergen naar parent node |

### GitLab-parameters

| Variabele                 | Standaard               | Beschrijving                                                             |
| ------------------------- | ----------------------- | ------------------------------------------------------------------------ |
| `GITLAB_BASE_URL`         | `https://gitlab.com`    | Base URL van de GitLab-instantie (self-hosted of gitlab.com)            |
| `GITLAB_PAT`              | *(leeg)*                | Personal Access Token; verplicht voor private projecten                  |
| `GITLAB_WIKI_URLS`        | *(leeg)*                | Komma-gescheiden lijst van wiki-URLs om automatisch te indexeren         |
| `GITLAB_REPO_URLS`        | *(leeg)*                | Komma-gescheiden lijst van repository-URLs om automatisch te indexeren   |

### Effect van numerieke waarden

**`PARENT_CHUNK_SIZE`**
- **Hoger** — grotere parent chunks geven de LLM meer context per antwoord, maar verhogen de kans op irrelevante tekst.
- **Lager** — precisere zoekresultaten, maar risico op afgekapte zinnen of onvolledige antwoorden.
- Na aanpassing is een volledige herindexering vereist.

**`CHILD_CHUNK_SIZE`**
- **Hoger** — minder precieze similarity search maar meer context per opgehaald fragment.
- **Lager** — preciezere zoekresultaten, maar meer kans dat een antwoord over meerdere losse fragments verspreid is.
- Aanbevolen: houd de verhouding op `PARENT_CHUNK_SIZE // 4`. Bij afwijking geeft de indexer een waarschuwing.

**`PARENT_CHUNK_OVERLAP`**
- **Hoger** — minder kans dat relevante informatie op een chunk-grens valt. Vergroot de index.
- **Lager** — kleinere index, maar informatie op chunk-grenzen kan gemist worden.
- Aanbevolen: ~20% van `PARENT_CHUNK_SIZE`.

**`AUTOMERGE_THRESHOLD`**
- **Hoger** (richting `1.0`) — strenger: LLM krijgt vaker losse child nodes (preciezer, minder context).
- **Lager** (richting `0.0`) — soepeler: LLM krijgt vaker de volledige parent node (meer context, meer kans op irrelevante tekst).

## Opnieuw indexeren

| Situatie | Actie | Resultaat |
| -------- | ----- | --------- |
| Nieuwe documenten toegevoegd | **Herindexeer** | Alleen nieuwe documenten worden geëmbed en geüpsert |
| Bestaand document gewijzigd | **Herindexeer** | Oude vectoren en docstore-nodes worden verwijderd; document wordt opnieuw geëmbed |
| Document verwijderd | **Herindexeer** | Qdrant-punten en docstore-nodes worden automatisch opgeruimd |
| Document ongewijzigd | **Herindexeer** | Overgeslagen — geen embedding-aanroepen |
| `PARENT_CHUNK_SIZE`, `CHILD_CHUNK_SIZE`, `PARENT_CHUNK_OVERLAP` of `EMBED_MODEL` gewijzigd | Automatisch (versiestempel) of **Volledig** | Zie hieronder |

### Incrementele sync (standaard)

Bij elke run leest de indexer met één scroll-pass de `file_path`- en `content_hash`-payloads terug uit de Qdrant-collectie — **er is geen manifest-bestand**. Elke Qdrant-punt draagt een SHA-256-hash van de brondocumenttekst in zijn payload. Documenten worden geclassificeerd als:

- **Nieuw** — niet in Qdrant → geëmbed en toegevoegd
- **Gewijzigd** — hash verschilt → oud opgeruimd, opnieuw geëmbed
- **Verwijderd** — in Qdrant maar niet meer opgehaald → oud opgeruimd
- **Ongewijzigd** — hash identiek → overgeslagen

Omdat Qdrant de enige bron van waarheid is, hervat een onderbroken run bij de volgende poging correct — er is geen apart manifest dat uit sync kan raken. De docstore wordt per document atomair weggeschreven (tempbestand + rename).

### Volledige herindexering

Wordt **automatisch** getriggerd wanneer de versiestempel (`EMBED_MODEL`, `PARENT_CHUNK_SIZE`, `CHILD_CHUNK_SIZE`, `PARENT_CHUNK_OVERLAP`) in de Qdrant-collectie `index_meta` niet meer overeenkomt met de huidige `.env`-configuratie, of handmatig via de **Volledig**-knop / `--full-reindex`. Dit doet automatisch:

1. De Qdrant-collecties `chunks_child` en `index_meta` verwijderen
2. `docstore.json` verwijderen
3. `abbreviations.json` verwijderen
4. De nieuwe versiestempel direct wegschrijven (zodat een onderbroken rebuild incrementeel hervat in plaats van opnieuw te wissen)
5. Alle documenten opnieuw indexeren

## Probleemoplossing

| Probleem                       | Controleer                                                                |
| ------------------------------ | ------------------------------------------------------------------------- |
| Geen documenten gevonden       | Controleer of bestandsextensies in de ondersteunde lijst staan            |
| Embedden mislukt               | `ollama ps` — controleer of het model geladen is op de host               |
| Qdrant-verbindingsfout         | `curl http://localhost:6333/healthz`                                      |
| GitLab 401 Unauthorized        | Controleer `GITLAB_PAT` in `.env`                                         |
| GitLab 403 Forbidden           | PAT mist `read_wiki` of `read_repository` scope                           |
| GitLab 404 Not Found           | Controleer de wiki/repo-URL en of het project bestaat                     |
| Indexering start niet          | Bekijk de logs via `docker compose logs -f generating`                    |
