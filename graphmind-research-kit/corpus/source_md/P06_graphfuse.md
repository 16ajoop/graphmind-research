# GraphFuse: Fusing Dense and Graph Retrieval for Multi-Hop QA

Lena Fischer (1), Rahul Mehta (1), Priyanka Das (2)

(1) Rhinebrook Technical University   (2) Bay of Bengal Institute of Technology

ICRR 2024 · Published 18 March 2024

## Abstract

Dense and graph-based retrievers fail on different questions. GraphFuse runs a GraphWalker-QA walk and a HopRank chain search in parallel and merges their candidate chains with a learned fusion scorer. GraphFuse reaches 57.9 and 46.3 EM on KaveriHop 2-hop and 3-hop, and 41.2 and 22.7 EM on TriHop-Bench 3-hop and 4-hop. Fusing dense and graph retrieval outperforms either approach alone at every hop count.

Keywords: hybrid retrieval, fusion, multi-hop question answering

## 1 Introduction

Iterative dense retrieval [1] remains the backbone of many systems. HopRank [3] is strongest on short chains, while GraphWalker-QA [2] is strongest on long chains. Their errors overlap on fewer than 40% of questions, which suggests that combining them should help.

## 2 Method

GraphFuse extends GraphWalker-QA [2] and HopRank [3]. Both components produce up to 50 candidate chains; a fusion scorer combines walk scores, rerank scores and the agreement between the two candidate lists.

## 3 Experiments

We evaluate on KaveriHop [4] and TriHop-Bench [5]. Baseline numbers are quoted from the original papers and from the TriHop-Bench paper.

| Method | Source | KaveriHop 2-hop EM | KaveriHop 3-hop EM | TriHop-Bench 3-hop EM | TriHop-Bench 4-hop EM |
|---|---|---|---|---|---|
| GraphWalker-QA | [2] | 50.1 | 39.8 | – | – |
| GraphWalker-QA | [5] | – | – | 34.7 | 17.5 |
| HopRank | [3] | 53.4 | 36.0 | – | – |
| HopRank | [5] | – | – | 31.9 | 11.2 |
| GraphFuse | ours | 57.9 | 46.3 | 41.2 | 22.7 |

*Table 1: Exact match on KaveriHop and TriHop-Bench.*

## 4 Conclusion

Fusing dense and graph retrieval outperforms either approach alone at every hop count. Fusion roughly doubles retrieval cost, which we leave to future work.

## References

[1] Iyer, A., Mehta, R., and Fischer, L. (2021). DenseHop: Iterative Dense Retrieval for Multi-Hop Questions. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[2] Fischer, L., Weber, J., and Das, P. (2022). GraphWalker-QA: Answering Multi-Hop Questions by Walking Entity Graphs. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[3] Mehta, R., Okafor, S., and Iyer, A. (2023). HopRank: Hop-Aware Reranking for Dense Multi-Hop Retrieval. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[4] Sundaram, M., Iyer, A., and Ruiz, T. (2022). KaveriHop: A Benchmark for Two- and Three-Hop Question Answering. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[5] Ruiz, T., Sundaram, M., and Zhang, W. (2023). TriHop-Bench: Stress-Testing Retrieval on Three- and Four-Hop Questions. Journal of Applied Language Systems.

---
*Synthetic paper for the GraphMind hackathon dataset. Authors, institutions, datasets and results are fictional.*
