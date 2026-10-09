# Vector Database

Qdrant slaat child (leaf) node vectors op voor similarity search. Parent nodes worden opgeslagen in `docstore.json`, een lokaal bestand beheerd door LlamaIndex dat wordt gemount in de `generating` container.

Zie [`indexing/README.md`](../indexing/README.md) voor hoe de data hier terechtkomt.

## Opslag Structuur

Child nodes worden geëmbedded met `qwen3-embedding` (4096-dimensionale dense vectors) en opgeslagen in Qdrant voor similarity search. Parent nodes worden opgeslagen als JSON de `AutoMergingRetriever` gebruikt deze om opgehaalde child chunks uit te breiden naar bredere context vóór de generatiefase. Zie [`indexing/README.md`](../indexing/README.md) voor een volledige uitleg van deze strategie.

```mermaid
flowchart TD
    subgraph Indexer["Indexing Service (Docker)"]
flowchart TD
    subgraph Indexer["Indexing Service (Docker)"]
        A[Documents] --> B[Child Nodes<br>PARENT_CHUNK_SIZE÷4]
        A --> C[Parent Nodes<br>PARENT_CHUNK_SIZE]
    end

    subgraph Storage
        B -->|vectors + content_hash payload| D[(Qdrant<br>chunks_child)]
        C -->|JSON| E[(docstore.json)]
        F[(Qdrant<br>index_meta<br>versiestempel)]
    end

    subgraph Query["generating service"]
        D -->|Similarity search top-K| H[Child Nodes]
        H -->|Parent lookup als genoeg siblings| E
        E -->|Automerge tot parent node| G[Retrieved Context]
    end
```

## Inhoud van de Map

```
vector-db/
├── README.md               # Dit bestand
├── docstore.json           # Gegenereerd door de indexer — niet handmatig aanpassen
├── abbreviations.json      # Afkortingenwoordenboek, gebouwd tijdens indexering
└── .indexing.lock          # flock-bestand: indexer (exclusief) / generating-herlaad (gedeeld)
```

Er is bewust **geen** manifest-bestand (zoals `index-manifest.json`): wijzigingsdetectie leeft volledig in de Qdrant-punt-payloads. Elke punt in `chunks_child` draagt `file_path` en `content_hash` (SHA-256 van de brondocumenttekst) in zijn payload — Qdrant is de enige bron van waarheid voor wat er geïndexeerd is.

## Qdrant Collections

| Collection     | Doel                                            | Vectors                          |
| -------------- | ----------------------------------------------- | -------------------------------- |
| `chunks_child` | Vector index voor similarity search             | bepaald door `EMBED_MODEL`       |
| `index_meta`   | Eén punt met de versiestempel (configuratie)    | dummy 1-dim, niet voor zoeken    |

> Alleen `chunks_child` wordt gebruikt voor retrieval. Parent nodes staan in `docstore.json`, niet in Qdrant. `index_meta` bevat één punt met het embeddingmodel en de chunk-groottes waarmee de index gebouwd is; bij een configuratiewijziging wordt automatisch een volledige herindexering getriggerd — zie [`indexing/README.md`](../indexing/README.md#volledige-herindexering).

## Configuratie

| Variabele                 | Standaard               | Beschrijving                                   |
| ------------------------- | ----------------------- | ---------------------------------------------- |
| `QDRANT_URL`              | `http://localhost:6333` | URL van de Qdrant server                       |
| `QDRANT_CHILD_COLLECTION` | `chunks_child`          | Naam van de collection voor child node vectors |

`EMBED_MODEL`, `DOCSTORE_PATH`, `PARENT_CHUNK_SIZE` en `PARENT_CHUNK_OVERLAP` worden beheerd door de indexing module — zie [`indexing/README.md`](../indexing/README.md#configuratie).

> `qwen3-embedding` produceert 4096-dimensionale vectors. De vector dimensie wordt automatisch bepaald door het model en hoeft niet apart geconfigureerd te worden.

## Database Inspecteren

Qdrant biedt drie interfaces: een **REST API** (poort 6333), een **gRPC API** (poort 6334) en een ingebouwd **web dashboard**. Voor dagelijks gebruik is het dashboard het meest praktisch; de REST API is handig voor scripting en debugging. Zie de [Qdrant documentatie](https://qdrant.tech/documentation/) voor een volledig overzicht.

### Dashboard

| URL                                                          | Beschrijving                                               |
| ------------------------------------------------------------ | ---------------------------------------------------------- |
| `http://localhost:6333/dashboard`                            | Web UI collections, vectors en query's visueel inspecteren |
| `http://localhost:6333/dashboard/#/collections/chunks_child` | Directe link naar de `chunks_child` collection             |

### REST API

| URL                                              | Beschrijving                                        |
| ------------------------------------------------ | --------------------------------------------------- |
| `http://localhost:6333/collections`              | Overzicht van alle collections                      |
| `http://localhost:6333/collections/chunks_child` | Details van `chunks_child` (aantal vectors, config) |
| `http://localhost:6333/healthz`                  | Health check                                        |

## Database Resetten

```bash
docker compose down -v
rm -f vector-db/docstore.json vector-db/abbreviations.json vector-db/.indexing.lock
docker compose up -d
```

Start daarna een volledige herindexering via de **Instellingen** in de chat-interface (knop 'Volledig').
