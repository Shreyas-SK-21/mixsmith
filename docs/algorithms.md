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

Mixsmith classifies feasibility into four distinct states:
1. **`FEASIBLE`**: Spacing is mathematically sound across all individual and collaboration sets.
2. **`NECESSARILY_INFEASIBLE`**: An individual artist violates the pigeonhole lower bound.
3. **`COLLABORATION_CONSTRAINED`**: Individual frequencies pass, but shared collaborative tracks create dense mutual exclusions.
4. **`CONDITIONALLY_TIGHT`**: Feasible only under optimal boundary placement.

Mixsmith computes the maximum achievable spacing $k^*(a)$ for each bottleneck artist:
$$k^*(a) = \left\lfloor \frac{N - 1}{C(a) - 1} \right\rfloor - 1$$
And reports the feasibility ceiling $k^* = \min_{a} k^*(a)$ before execution.

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
- **Time Discretization**: Durations are scaled to discrete units $\Delta t = 5$ seconds. For a target duration $D$ and tolerance $\delta$, the target capacity is $W = D / \Delta t$.
- **Multi-Objective Value Function**:
  $$\text{val}(T) = \text{pop}(T) \cdot \frac{1}{1 + 0.35 \cdot \text{prior\_count}(\text{artist}(T))}$$
  This rewards track quality while penalizing artist over-representation to preserve diversity.
- **Dynamic Programming Table**: Bounded DP finds the subset of tracks that minimizes $| \sum \text{duration} - D |$ while maximizing the diversity-weighted value score.
- **Large Dataset Scalability**: For libraries exceeding 300 tracks, Mixsmith switches to a diversity-aware approximation heuristic.

---

## 3. Quota Allocation (Hamilton-Hare Largest Remainder Method)

To eliminate rounding drift and guarantee exact integer allocations across genres and decades:
1. For each category $i$ with fractional weight $w_i$, compute the exact quota: $E_i = N \cdot w_i$.
2. Take the integer floor: $F_i = \lfloor E_i \rfloor$.
3. Compute fractional remainders: $R_i = E_i - F_i$.
4. Allocate residual slots $S = N - \sum F_i$ to categories with the largest remainders.

---

## 4. Independent Central Validation Engine

Mixsmith decouples generation from verification. Once a permutation $\pi$ is produced, an independent `PlaylistValidator` inspects the final playlist across every requested constraint:
- **`track_preservation`**: Proves all tracks originate strictly from the source library.
- **`artist_spacing`**: Scans every window $[i, i+k]$ and reports exact violations and minimum gap observed.
- **`max_tracks_per_artist`**: Verifies no artist exceeds their quota.
- **`target_duration`**: Verifies total duration falls within $[D - \delta, D + \delta]$.
- **`genre_distribution`**: Verifies final shares against target percentages.
- **`pinned_positions`**: Verifies pinned tracks occupy their exact indices.

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
