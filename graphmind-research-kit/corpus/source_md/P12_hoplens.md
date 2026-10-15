# HopLens: Interpretable Path Scoring for Multi-Hop Retrieval

Hana Kobayashi (1), Mateo Rossi (1)

(1) Northern Isles University

OpenPrints 2026 · Published 3 February 2026

## Abstract

Multi-hop retrievers rarely explain why a chain of passages was chosen. HopLens scores each candidate chain with an interpretable path-aware reranking module that assigns a weight to every hop transition. HopLens reaches 56.2 and 44.8 EM on KaveriHop 2-hop and 3-hop, and 39.5 EM on TriHop-Bench 3-hop. HopLens achieves state-of-the-art exact match on 3-hop questions in both KaveriHop and TriHop-Bench.

Keywords: interpretability, reranking, multi-hop retrieval

## 1 Introduction

Dense multi-hop retrievers such as DenseHop [1] and graph walkers such as GraphWalker-QA [2] produce chains without explanation. We propose to rerank chains with a transparent per-hop scorer.

## 2 Method

HopLens retrieves 50 candidate chains with a dense retriever initialised from dense passage retrieval [5], then applies path-aware reranking: a cross-encoder scores each transition between consecutive passages, and the chain score is a weighted sum of transition scores. The transition weights are shown to the user as an explanation.

## 3 Experiments

We evaluate on KaveriHop [3] and TriHop-Bench [4], comparing with DenseHop [1] and GraphWalker-QA [2] using published numbers.

| Method | Source | KaveriHop 2-hop EM | KaveriHop 3-hop EM | TriHop 3-hop EM |
|---|---|---|---|---|
| DenseHop | [3] | 48.2 | 31.5 | – |
| GraphWalker-QA | [2] | 50.1 | 39.8 | – |
| GraphWalker-QA | [4] | – | – | 34.7 |
| HopLens | ours | 56.2 | 44.8 | 39.5 |

*Table 1: Exact match on KaveriHop and TriHop-Bench.*

## 4 Conclusion

HopLens achieves state-of-the-art exact match on 3-hop questions in both KaveriHop and TriHop-Bench while explaining its choices.

## References

[1] Iyer, A., Mehta, R., and Fischer, L. (2021). DenseHop: Iterative Dense Retrieval for Multi-Hop Questions. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[2] Fischer, L., Weber, J., and Das, P. (2022). GraphWalker-QA: answering multi-hop questions by walking entity graphs. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[3] Sundaram, M., Iyer, A., and Ruiz, T. (2022). KaveriHop: A Benchmark for Two- and Three-Hop Question Answering. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[4] Ruiz, T., Sundaram, M., and Zhang, W. (2023). TriHop-Bench: Stress-Testing Retrieval on Three- and Four-Hop Questions. Journal of Applied Language Systems.
[5] Karpukhin, V., Oguz, B., Min, S., Lewis, P., Wu, L., Edunov, S., Chen, D., and Yih, W. (2020). Dense Passage Retrieval for Open-Domain Question Answering. EMNLP.

---
*Synthetic paper for the GraphMind hackathon dataset. Authors, institutions, datasets and results are fictional.*
