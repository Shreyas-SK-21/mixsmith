# Mixsmith Algorithmic Foundations

This document details the mathematical models and algorithms powering Mixsmith.

---

## 1. Advanced Artist De-clumping ($k$-Spacing Engine)

### Problem Formulation
Given a set of $N$ tracks $\mathcal{T} = \{T_1, T_2, \dots, T_N\}$, each associated with a set of artists $\mathcal{A}(T) = \{a_1, a_2, \dots\}$, arrange $\mathcal{T}$ into a permutation $\pi$ such that for any two tracks $\pi(i)$ and $\pi(j)$ with $|i - j| \le k$:
$$\mathcal{A}(\pi(i)) \cap \mathcal{A}(\pi(j)) = \emptyset$$

### Mathematical Feasibility (Pigeonhole Theorem)
Let $C(a)$ denote the number of tracks featuring artist $a$. To place $C(a)$ tracks with minimum spacing $k$ between occurrences, the playlist must contain at least:
$$L_{\min}(a) = (C(a) - 1) \cdot (k + 1) + 1$$
If $L_{\min}(a) > N$, exact spacing $k$ is mathematically impossible.

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

## 2. Multi-Constraint Sequencing

The constraint engine evaluates multiple simultaneous constraints:
- **Max Tracks Per Artist**: Group by primary artist, keep top tracks by popularity up to the limit.
- **Genre Quotas**: Proportional quota allocation across universal genre clusters.
- **Target Duration**: Knapsack fitting within duration tolerance window (e.g., target 120 min $\pm 10$ min).
- **Pinned Positions**: Absolute position enforcement ($0$ for intro, $-1$ for outro).
- **Listening Journeys**:
  - *Artist Evolution*: Chronological sorting by release date, album, and track number.
  - *Decade Journey*: Smooth era transitions ($60\text{s} \to 70\text{s} \to 80\text{s} \to 90\text{s} \to 2000\text{s} \to 2010\text{s} \to 2020\text{s}$).
  - *Genre Journey*: Acoustic/stylistic adjacency traversal.
  - *Nostalgia Mode*: Distance penalty minimization relative to target golden decade.

---

## 3. Intelligent Deduplication Matrix

Mixsmith partitions duplicate detection into a two-pass pipeline:
1. **Recording Code Pass**: Exact ISRC match ($100\%$ confidence identical audio master).
2. **Fuzzy Title + Artist Pass**: Normalized title matching:
   - Removes bracketed/parenthetical metadata.
   - Strips hyphenated version suffixes (`- 2011 Remaster`, `- Live at ...`).
   - Removes collaboration credits (`feat.`, `ft.`).
   - Categorizes variants into `standard`, `remaster`, `live`, `acoustic`, `radio_edit`, and `deluxe`.
   - Ranks candidates according to user strategy (`exact_only`, `keep_original`, `keep_remaster`, `keep_all`).
