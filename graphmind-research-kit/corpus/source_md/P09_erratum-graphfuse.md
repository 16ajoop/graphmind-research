# Erratum: GraphFuse: Fusing Dense and Graph Retrieval for Multi-Hop QA

Lena Fischer (1), Rahul Mehta (1), Priyanka Das (2)

(1) Rhinebrook Technical University   (2) Bay of Bengal Institute of Technology

ICRR 2025 · Published 14 February 2025

## Abstract

A bug in our evaluation script counted some 4-hop answers with trailing punctuation as correct. The corrected 4-hop exact match of GraphFuse on TriHop-Bench is 19.4, not 22.7 as published. All other numbers are unchanged.

Keywords: erratum, evaluation, multi-hop question answering

## 1 The Error

Our script normalised answers before comparison on the 2-hop and 3-hop subsets but not on the 4-hop subset, where annotators' answers contained trailing punctuation. Re-running with consistent normalisation on TriHop-Bench [2] lowers the 4-hop score of GraphFuse [1].

## 2 Impact

The corrected 4-hop result does not change the paper's conclusions, since GraphFuse still outperforms both single retrievers (GW-QA: 17.5, HopRank: 11.2). We ask authors who quote the 4-hop number from the original GraphFuse paper to use the corrected value.

| Method | Source | TriHop-Bench 4-hop EM |
|---|---|---|
| GraphFuse | [1] as published | 22.7 |
| GraphFuse | corrected | 19.4 |

*Table 1: Corrected 4-hop result on TriHop-Bench.*

## References

[1] Fischer, L., Mehta, R., and Das, P. (2024). GraphFuse: Fusing Dense and Graph Retrieval for Multi-Hop QA. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[2] Ruiz, T., Sundaram, M., and Zhang, W. (2023). TriHop-Bench: Stress-Testing Retrieval on Three- and Four-Hop Questions. Journal of Applied Language Systems.

---
*Synthetic paper for the GraphMind hackathon dataset. Authors, institutions, datasets and results are fictional.*
