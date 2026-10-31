# Spotify Developer Policy & Compliance Audit

This document provides a comprehensive review of Mixsmith's architecture, data processing models, and integration boundaries against the **Spotify Developer Policy** (specifically Sections III.13 and III.14) and the February 2026 Spotify Web API contract.

---

## 1. Regulatory & Policy Context

### Section III.13 — Metrics, Statistics, and Derivative Profiling
> **Policy Restriction:**
> Developers must not aggregate, process, or analyze Spotify Content to create, augment, or monetize new metrics, statistics, analytics, machine learning datasets, or user listening profiles, except for displaying user-facing playback information authorized directly by the user.

- **Implication for Mixsmith:**
  - Mixsmith does **not** sell, aggregate across users, or commercially distribute listening analytics.
  - However, functions that derive higher-order categorizations (e.g., algorithmic energy scoring, synthetic theme tagging, or statistical mood curves) from raw Spotify metadata can touch upon Section III.13 if interpreted strictly by Spotify Developer Operations.
  - Local, ephemeral client-side processing reduces data privacy risks but does **not** automatically grant exemption from Section III.13 restrictions.
  - **Status:** *Pending written policy clarification from Spotify.* Mixsmith maintains a strict boundary separating its platform-independent curation algorithms from live Spotify data streams.

### Section III.14 — AI/ML Training and Ingestion Restrictions
> **Policy Restriction:**
> Developers are expressly prohibited from ingesting Spotify Content into artificial intelligence or machine learning models for model training, weights adjustment, fine-tuning, retrieval-augmented indexing, or algorithmic feature synthesis.

- **Implication for Mixsmith:**
  - Mixsmith's AI curation parser (`mixsmith.ai.parser`) operates **strictly on user-supplied natural language instructions** (e.g., `"make a 45-minute playlist with at least 2 tracks per artist"`).
  - No Spotify Content (track names, audio previews, artist metadata, or audio features) is ever passed to an external Large Language Model or training pipeline.
  - LLM inferences are restricted to producing structured constraint specifications (`CurationSpecification`).
  - **Status:** *Compliant by design.* Curation specifications are purely abstract scheduling constraints.

---

## 2. Feature-by-Feature Compliance & Platform Decoupling Matrix

To ensure absolute architectural transparency and allow safe operation across local and streaming environments, Mixsmith categorizes every capability into one of two operational tiers:

| Component / Feature | Uses Spotify Content? | Platform-Independent? | Compliance Assessment & Operational Boundary |
|---|---|---|---|
| **Multi-Artist De-clumper** (`core/declumper.py`) | No (abstract IDs & strings) | **Yes** (100% offline) | Fully platform-independent. Operates purely on combinatorial graph coloring and sliding window algorithms over arbitrary track collections. |
| **Knapsack Duration Optimizer** (`core/duration.py`) | No (durations in ms) | **Yes** (100% offline) | Fully platform-independent. Solves dynamic programming 0/1 knapsack and bounded greedy subset selection on integer runtimes. |
| **Quota Allocator** (`core/quotas.py`) | No (categorical labels) | **Yes** (100% offline) | Fully platform-independent. Employs Largest Remainder (Hamilton-Hare) proportional representation over user-defined quotas. |
| **Energy Progression** (`core/journeys.py`) | No API energy used | **Yes** (Heuristic) | Computes heuristic energy exclusively from local genre taxonomies, human themes, and lexical title markers without calling removed Spotify audio features. |
| **Constraint Validator** (`core/validation.py`) | No | **Yes** (100% offline) | Independent audit engine verifying final playlists against hard/soft user constraints. |
| **Local CSV / Excel Exporters** (`exporters/`) | Track metadata | **Yes** (offline files) | Generates static XLSX and CSV spreadsheets for local analysis and user archiving. |
| **Spotify Connector & Sync** (`connectors/spotify.py`) | Yes (Web API) | No (Spotify-only) | Directly interfaces with Spotify Web API. Subject to Development Mode restrictions and Section III.13 clarification. |

---

## 3. Spotify Development Mode Constraints (February 2026 API)

Developers running Mixsmith with their own Spotify Developer credentials must operate within Spotify's updated Development Mode policies:

1. **Owner Account Requirements:**
   - The creator and owner of the Spotify Developer Application must maintain an active **Spotify Premium** subscription.
2. **Authorized User Quota:**
   - In Development Mode, applications can only authenticate up to **5 registered Spotify users** (added explicitly by email in the Spotify Developer Dashboard).
3. **Application & Client ID Quota:**
   - A single developer account may create up to **25 Client IDs**, but all applications share a global rate limit.
4. **Endpoint and Metadata Sunset:**
   - The bulk artist endpoint (`GET /artists?ids=...`) has been removed in Development Mode. Mixsmith uses graceful single-artist fallbacks and local cache layers.
   - Track and artist `popularity` metrics are omitted from Development Mode responses. Mixsmith models `popularity` as `int | None = None` and curates neutrally without assuming missing popularity is 0.
   - Playlist item endpoints use the updated February 2026 schema (`playlist.items.items[].item` and `items.total`).

---

## 4. Remediation & User Guidance

- **No False Assurances:** Mixsmith does not claim blanket "official certification" or "strict legal compliance" under Spotify Developer Policies. Users and developers are advised that commercial use or public deployment requires formal quota extension review and policy approval from Spotify.
- **Offline / Local First:** Users wishing to curate playlists without interacting with Spotify Web API policies may use Mixsmith's CSV/Excel engines and local JSON pipelines completely decoupled from Spotify.
