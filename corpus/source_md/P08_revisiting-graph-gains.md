# Revisiting Graph Gains: A Reproduction Study of GraphWalker-QA

Sara Okafor (1), Wei Zhang (2), Jonas Weber (3)

(1) Lagoon City University   (2) Instituto Altamira   (3) Rhinebrook Technical University

JALS 2024 · Published 10 September 2024

## Abstract

We reproduce GraphWalker-QA on KaveriHop. With the gold entity annotations used in the original paper we match its results (39.5 versus 39.8 EM on 3-hop questions). With entity links predicted by LinkLite, 3-hop EM drops to 35.1, slightly below HopRank at 35.4. GraphWalker-QA's 3-hop advantage depends on gold entity links; with predicted links it falls below HopRank.

Keywords: reproducibility, graph-based retrieval, entity linking

## 1 Introduction

GraphWalker-QA [1] reported that walking an entity graph helps most on 3-hop questions. KaveriHop [2] provides gold bridge-entity annotations and asks that they not be used at test time. We noticed that GraphWalker-QA took its entity links from those annotations.

## 2 Setup

We use the released GraphWalker-QA code and run it twice: with gold links, as in the original paper, and with links predicted by LinkLite [4]. We also re-run HopRank [3] as a dense baseline.

| Method | Source | KaveriHop 2-hop EM | KaveriHop 3-hop EM |
|---|---|---|---|
| GW-QA | [1] as reported | 50.1 | 39.8 |
| GW-QA | reproduced, gold links | 50.3 | 39.5 |
| GW-QA | reproduced, predicted links | 49.6 | 35.1 |
| HopRank | reproduced | 53.1 | 35.4 |

*Table 1: Reproduction on KaveriHop (exact match).*

## 3 Results

With gold links we reproduce the original numbers within 0.3 EM. With predicted links the 3-hop score falls by 4.4 EM. Our results contradict the conclusion of the original paper under realistic conditions.

## 4 Discussion

One of us (J. Weber) co-authored the original paper; the original authors shared their code and confirmed the use of gold links. GraphWalker-QA's 3-hop advantage depends on gold entity links; with predicted links it falls below HopRank. We recommend that graph-based methods always report results with predicted entity links.

## References

[1] Fischer, L., Weber, J., and Das, P. (2022). GraphWalker-QA: Answering Multi-Hop Questions by Walking Entity Graphs. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[2] Sundaram, M., Iyer, A., and Ruiz, T. (2022). KaveriHop: A Benchmark for Two- and Three-Hop Question Answering. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[3] Mehta, R., Okafor, S., and Iyer, A. (2023). HopRank: Hop-Aware Reranking for Dense Multi-Hop Retrieval. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[4] Brown, T. and Lee, J. (2019). LinkLite: Lightweight Multilingual Entity Linking. JALS.

---
*Synthetic paper for the GraphMind hackathon dataset. Authors, institutions, datasets and results are fictional.*
