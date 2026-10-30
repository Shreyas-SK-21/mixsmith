# Mixsmith Architecture

Mixsmith is designed as a modular, platform-independent music curation engine. The architecture decouples domain algorithms (sequencing, deduplication, de-clumping, filtering) from music streaming service APIs (Spotify).

---

## High-Level Architecture Diagram

```
+-------------------------------------------------------------------+
|                        CLI / Interface                            |
|             (curate, dedup, export, analyze, compare)             |
+---------------------------------+---------------------------------+
                                  |
         +------------------------+------------------------+
         |                                                 |
         v                                                 v
+-------------------------------+         +-------------------------------+
|      AI & Natural Language    |         |        Core Curation Engine   |
|  - Schema Validation          |         |  - Spacing Engine (De-clumper)|
|  - Heuristic Prompt Parser    |         |  - Multi-Constraint Engine    |
|  - CurationSpec Generator     |         |  - Listening Journey Modes    |
|  (Translates prompts -> specs)|         |  - Intelligent Deduplication  |
+---------------+---------------+         |  - AST Boolean Filters        |
                |                         |  - Playlist Manager & Diff    |
                +------------------------>+---------------+---------------+
                                                          |
                                  +-----------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
|                     Domain Models (Platform Agnostic)             |
|                 Track, Playlist, ConstraintResult, CurationPlan   |
+---------------------------------+---------------------------------+
                                  |
         +------------------------+------------------------+
         |                                                 |
         v                                                 v
+-------------------------------+         +-------------------------------+
|     Connectors & Auth         |         |           Exporters           |
|  - MusicConnectorBase         |         |  - Excel (openpyxl styled,    |
|  - SpotifyConnector           |         |    Overview & Insights)       |
|  - OAuthManager & TokenStore  |         |  - CSV (Exportify compatible, |
|  - Rate-limit & 401 recovery  |         |    UTF-8-sig BOM)             |
+-------------------------------+         +-------------------------------+
```

---

## Architectural Principles

1. **Platform Independence**: Core filtering, de-clumping, sequencing, and deduplication logic operate solely on typed `Track` and `Playlist` domain objects. They have zero dependency on Spotify API or network connections.
2. **Deterministic Execution**: The AI layer translates ambiguous user instructions into strict `NaturalLanguageCurationSpec` JSON. All track selection and sequencing is performed by deterministic algorithms.
3. **Safe Mutation Protocol**: No mutation on Spotify (creation, reordering, deletion) occurs without explicit dry-run previews, constraint audit reports, and user confirmation.
4. **Resilient Network Client**: The `SpotifyConnector` automatically intercepts HTTP 429 (rate limits) and reads the `Retry-After` header for exponential backoff, while catching HTTP 401 to transparently refresh access tokens without dropping the request.
5. **Configuration Hierarchy**:
   1. Explicit programmatic arguments
   2. Environment variables (`SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`)
   3. Local `.env` file
   4. Platform configuration directory (`~/.config/mixsmith/credentials.json`)
   5. Legacy plugin fallback path for backward compatibility.
