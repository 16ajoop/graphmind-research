# HopRank: Hop-Aware Reranking for Dense Multi-Hop Retrieval

Rahul Mehta (1), Sara Okafor (2), Ananya Iyer (1)

(1) University of Coromandel   (2) Lagoon City University

ICRR 2023 · Published 12 April 2023

## Abstract

We present HopRank, which extends DenseHop with a hop-aware reranker that re-scores candidate passage chains using cross-attention between hops. On KaveriHop, HopRank reaches 53.4 EM on 2-hop and 36.0 EM on 3-hop questions, adding only 30 ms of latency per query. Hop-aware reranking closes the gap to graph-based retrieval on 2-hop questions but not on 3-hop questions.

Keywords: reranking, dense retrieval, multi-hop retrieval

## 1 Introduction

DenseHop [1] scores each hop independently, so an early mistake cannot be undone. We keep the DenseHop retriever and add a second stage, which we call hop-aware re-scoring, that judges whole chains rather than single passages.

## 2 Method

HopRank builds on DenseHop [1]: we take its top 50 candidate chains and re-score each chain with a cross-encoder that attends across all passages in the chain. The reranker is trained with chain-level hard negatives. Like most dense systems it inherits encoders from dense passage retrieval [4].

## 3 Experiments

We evaluate on KaveriHop [2] and compare against DenseHop and the graph-based GraphWalker-QA [3], quoting their published numbers. We also measure latency on a single GPU.

| Method | Source | KaveriHop 2-hop EM | KaveriHop 3-hop EM | KaveriHop latency (ms/query) |
|---|---|---|---|---|
| DenseHop | [2] | 48.2 | 31.5 | – |
| DenseHop | ours | – | – | 150 |
| GraphWalker-QA | [3] | 50.1 | 39.8 | – |
| HopRank | ours | 53.4 | 36.0 | 180 |

*Table 1: Exact match and latency on KaveriHop.*

## 4 Discussion

HopRank surpasses GraphWalker-QA by 3.3 EM on 2-hop questions but trails it by 3.8 EM on 3-hop questions. Hop-aware reranking closes the gap to graph-based retrieval on 2-hop questions but not on 3-hop questions.

## 5 Conclusion

Chain-level reranking is a cheap upgrade for dense multi-hop retrievers.

## References

[1] Iyer, A., Mehta, R., and Fischer, L. (2021). DenseHop: Iterative Dense Retrieval for Multi-Hop Questions. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[2] Sundaram, M., Iyer, A., and Ruiz, T. (2022). KaveriHop: A Benchmark for Two- and Three-Hop Question Answering. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[3] Fischer, L., Weber, J., and Das, P. (2022). GraphWalker-QA: Answering Multi-Hop Questions by Walking Entity Graphs. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[4] Karpukhin, V., Oguz, B., Min, S., Lewis, P., Wu, L., Edunov, S., Chen, D., and Yih, W. (2020). Dense Passage Retrieval for Open-Domain Question Answering. EMNLP.

---
*Synthetic paper for the GraphMind hackathon dataset. Authors, institutions, datasets and results are fictional.*
