# Mixsmith Algorithmic Foundations

This document details the mathematical models and algorithms powering Mixsmith.

---

## 1. Advanced Artist De-clumping ($k$-Spacing Engine)

### Problem Formulation
Given a set of $N$ tracks $\mathcal{T} = \{T_1, T_2, \dots, T_N\}$, each associated with a set of artists $\mathcal{A}(T) = \{a_1, a_2, \dots\}$, arrange $\mathcal{T}$ into a permutation $\pi$ such that for any two tracks $\pi(i)$ and $\pi(j)$ with $|i - j| \le k$:
$$\mathcal{A}(\pi(i)) \cap \mathcal{A}(\pi(j)) = \emptyset$$

### Mathematical Feasibility (Pigeonhole Theorem & Collaborations)
Let $C(a)$ denote the number of tracks featuring artist $a$. To place $C(a)$ tracks with minimum spacing $k$ between occurrences, the playlist must contain at least:
$$L_{\min}(a) = (C(a) - 1) \cdot (k + 1) + 1$$
If $L_{\min}(a) > N$, exact spacing $k$ is mathematically impossible.

Similarly, if two tracks share identical or overlapping artist sets $\mathcal{A}(T_1) \cap \mathcal{A}(T_2) \neq \emptyset$, they cannot occupy adjacent positions within distance $\le k$. However, arbitrary pairwise collaboration density thresholds cannot be used as an infeasibility test. For instance, in a 4-track playlist with spacing $k=2$:
$$\pi = [\{A, B\}, \{C\}, \{D\}, \{A, B\}]$$
The pair $\{A, B\}$ appears at indices $0$ and $3$ (gap of 2 tracks), which is fully feasible. A pairwise collision is only proven impossible when $(C(pair) - 1)(k + 1) + 1 > N$.

Mixsmith classifies feasibility into three rigorous mathematical states:
1. **`PROVEN_INFEASIBLE`**: An individual artist or proven disjoint subset violates the necessary pigeonhole bound $L_{\min} > N$.
2. **`SUFFICIENTLY_FEASIBLE`**: All individual frequencies satisfy $C(a) \le \lceil N / (k + 1) \rceil$ and collaboration overlaps are sufficiently sparse to guarantee an interference-free schedule.
3. **`CONDITIONALLY_CONSTRAINED`**: Individual frequencies pass the necessary pigeonhole bound, but dense overlapping collaborations make global placement conditional on exact boundary conditions.

For single-artist bottlenecks, Mixsmith computes the exact mathematical ceiling:
$$k^*(a) = \left\lfloor \frac{N - 1}{C(a) - 1} \right\rfloor - 1$$
For conditionally constrained cases where no closed-form ceiling is proven, Mixsmith avoids fabricating arbitrary numbers and reports `max_achievable_spacing = None`.

### Scheduling Algorithm
Mixsmith uses a **Max-Frequency Greedy Priority Queue with Cooldown History**:
1. At each step $i$, maintain a sliding window of recent artist sets:
   $$\mathcal{H}_k = \bigcup_{m=1}^{k} \mathcal{A}(\pi(i - m))$$
2. Identify candidate tracks whose artist sets are disjoint from $\mathcal{H}_k$:
   $$\mathcal{C}_{\text{valid}} = \{T \in \mathcal{T}_{\text{remaining}} \mid \mathcal{A}(T) \cap \mathcal{H}_k = \emptyset\}$$
3. Score valid candidates by remaining global artist frequency:
   $$\text{score}(T) = \sum_{a \in \mathcal{A}(T)} \text{freq}_{\text{remaining}}(a)$$
4. If $\mathcal{C}_{\text{valid}} = \emptyset$ (tight or infeasible constraint), activate graceful degradation fallback: select the track that maximizes the distance from its most recent appearance.

---

## 2. Playlist Duration Optimization (Discrete 0/1 Knapsack)

Rather than naive greedy thresholding, Mixsmith optimizes playlist duration using a discrete **0/1 Knapsack Formulation**:
- **Millisecond-Tracked DP State**: Durations are scaled to discrete units $\Delta t = 5$ seconds for DP space bounds ($W = D / \Delta t$). However, because discrete rounding can accumulate millisecond drift, the DP state tracks exact running milliseconds:
  $$\text{state}(w) = (\text{val}, \text{track\_indices}, \text{actual\_total\_ms})$$
  Any transition yielding $\text{actual\_total\_ms} > \text{max\_acceptable\_ms}$ is discarded. A post-selection verification loop guarantees that the actual playlist runtime strictly satisfies the target ceiling.
- **Multi-Objective Value Function**:
  $$\text{val}(T) = \text{pop}(T) \cdot \frac{1}{1 + 0.35 \cdot \text{prior\_count}(\text{artist}(T))}$$
  This rewards track quality while penalizing artist over-representation to preserve diversity.
- **Large Dataset Scalability**: For libraries exceeding 300 tracks, Mixsmith ranks candidates by an artist-diversity novelty score, retains the top diverse candidates, and performs bounded knapsack optimization across the pruned subset.

---

## 3. Quota Allocation (Hamilton-Hare Largest Remainder Method)

To eliminate rounding drift and guarantee exact integer allocations across genres and decades:
1. For each category $i$ with fractional weight $w_i$, compute the exact quota: $E_i = N \cdot w_i$.
2. Take the integer floor: $F_i = \lfloor E_i \rfloor$.
3. Compute fractional remainders: $R_i = E_i - F_i$.
4. Allocate residual slots $S = N - \sum F_i$ to categories with the largest remainders.
5. **Shortfall Reallocation**: If a category has fewer available tracks than its allocated quota, the unfilled slots are automatically cataloged and proportionally redistributed to remaining categories without changing total playlist size.

---

## 4. Independent Central Validation Engine

Mixsmith decouples generation from verification. Once a permutation $\pi$ is produced, an independent `PlaylistValidator` inspects the final playlist across every requested constraint:

- **Hard Constraints (`severity="error"`)**:
  - **`track_preservation`**: Proves all tracks originate strictly from the source library and verifies source occurrence counts.
  - **`artist_spacing`**: Scans every window $[i, i+k]$, recording every conflict pair and calculating the exact minimum artist gap observed.
  - **`max_tracks_per_artist`**: Verifies no artist exceeds their quota, checking all primary and featured credits.
  - **`pinned_positions`**: Verifies pinned tracks occupy their exact indices.
  *Any hard constraint violation sets `is_valid = False` and outputs `Validation FAILED`.*

- **Soft Constraints (`severity="warning"`)**:
  - **`target_duration`**: Verifies total duration falls within $[D - \delta, D + \delta]$.
  - **`genre_distribution`**: Verifies final genre shares against target percentages.
  - **`decade_distribution`**: Verifies final era shares against requested decade bounds.
  *Soft constraint warnings yield `Validation PASSED WITH WARNINGS`, preserving the playlist while highlighting trade-offs.*

A constraint is never marked satisfied merely because matching tracks were found; only post-curation satisfaction is certified.

---

## 5. Intelligent Deduplication Matrix

Mixsmith partitions duplicate detection into a two-pass pipeline:
1. **Recording Code Pass**: Exact ISRC match ($100\%$ confidence identical audio master).
2. **Fuzzy Title + Artist Pass**: Normalized title matching:
   - Removes bracketed/parenthetical metadata.
   - Strips hyphenated version suffixes (`- 2011 Remaster`, `- Live at ...`).
   - Removes collaboration credits (`feat.`, `ft.`).
   - Categorizes variants into `standard`, `remaster`, `live`, `acoustic`, `radio_edit`, and `deluxe`.
   - Ranks candidates according to user strategy (`exact_only`, `keep_original`, `keep_remaster`, `keep_all`).

---

## 7. Confidence-Aware Metadata Inference

Mixsmith treats metadata inference as an evidence-weighted process rather than absolute truth:

- **Confidence Tiers**:
  - `KNOWN`: User explicit override or verified direct API signal.
  - `HIGH`: Deterministic linguistic/lexical evidence (Unicode Hangul, Katakana, Devanagari script; explicit title tags).
  - `MEDIUM`: Taxonomy association (subgenre mapping, ISRC 2-letter country prefix).
  - `LOW`: Weak lexical heuristics (Latin script without foreign markers presumed English).
  - `UNKNOWN`: Insufficient evidence. Never forces arbitrary classifications onto uninformative records.
- **Instrumental Recognition**: Identifies non-vocal and ambient compositions to avoid falsely categorizing instrumental music into vocal languages.

---

## 8. Safe Playlist Mutation & External Drift Detection

Modifying a user's library requires non-destructive verification:

1. **Pre-Mutation State Check**: Fetches target playlist's `snapshot_id` and total track count.
2. **External Drift Detection**: If an `expected_snapshot_id` is supplied and differs from the remote snapshot, raises `SnapshotDriftError` to prevent race conditions.
3. **URI Standardization**: Validates and normalizes track identifiers (`spotify:track:...`, bare 22-char ID, or web URLs), discarding malformed entries.
4. **Dry-Run Mode**: Simulates projected track counts without executing mutating API requests.
5. **Post-Mutation Verification**: Confirms that the target playlist was updated with the expected item count.

---

## 9. Algorithmic Benchmarking & Exact Solver Oracle

Located in `tests/benchmarks/`:

- **Synthetic Music Generator**: Creates realistic libraries using Zipf-distributed artist frequencies ($1 / k^{1.3}$) and collaboration hypergraphs.
- **Exact Backtracking Solver**: An exact permutation solver acting as a testing oracle for small libraries ($N \le 12$) to verify that whenever a mathematically valid schedule exists, our greedy heuristic satisfies it with zero violations.
- **Scalability**: Sequences $N = 1,000$ tracks in under 0.6 seconds using precomputed artist sets and $O(1)$ candidate removal.

---

## 10. Energy Progression & Duration Bounds

### Energy Progression Formulation
Mixsmith computes an independent, platform-decoupled acoustic energy score $E(T) \in [0, 100]$ without calling deprecated streaming API audio features or relying on popularity metrics:

1. **Genre Baseline**: Assigned based on intrinsic dynamic characteristics of the primary genre:
   - Metal: $90$, Electronic / Dance: $85$, Hip-Hop / Rap: $80$, Rock: $75$, Pop: $70$
   - Country / Americana: $55$, Desi / South Asian: $60$, Latin: $65$
   - Jazz & Blues: $45$, Folk & Acoustic: $35$, Classical / Cinematic: $25$
2. **Thematic Modifiers**:
   - Workout / Gym: $+25$, Party & Club: $+20$, Late Night Drive: $-5$
   - Chill & Coffee Shop: $-25$, Focus & Study: $-20$, Heartbreak & Melancholy: $-15$
3. **Title Lexical Cues**:
   - High energy tokens (`"remix"`, `"club"`, `"hard"`, `"party"`, `"fast"`): $+10$
   - Low energy tokens (`"acoustic"`, `"slow"`, `"unplugged"`, `"piano"`, `"lo-fi"`, `"sleep"`): $-15$
4. **Sequencing Curves**:
   - `mellow_to_energetic`: Monotonically ascending energy sort with artist de-clumping stabilization.
   - `energetic_to_mellow`: Monotonically descending energy sort with artist de-clumping stabilization.

### Hard Duration Bounds
Mixsmith introduces strict minimum and maximum duration boundaries $[T_{\min}, T_{\max}]$:
- **Pre-flight Feasibility**: Verifies that candidate pools contain sufficient total runtime to satisfy $T_{\min}$.
- **Conflict Audit**: Proactively flags specifications where `target_duration_minutes` falls outside $[T_{\min}, T_{\max}]$.
- **Hard Validation**: Audited by `PlaylistValidator` with `severity="error"` ensuring runtime boundaries are never violated.
