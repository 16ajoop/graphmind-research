# LiteGraphFuse: Distilling Fused Retrieval for Small Language Models

Arun Selvam (1), Kavitha Raman (1), Lena Fischer (2)

(1) Vaigai Institute of Language Technology   (2) Rhinebrook Technical University

LoResNLP 2025 · Published 20 June 2025

## Abstract

GraphFuse is accurate but slow, which limits its use with small language models and on modest hardware. LiteGraphFuse distils the GraphFuse fusion scorer into a 3-billion-parameter student and prunes the graph walk to two expansions per hop. On KaveriHop it reaches 55.0 and 43.9 EM, 95% of GraphFuse, at 105 ms per query instead of 420 ms. On the Tamil VaigaiQA benchmark it reaches 38.6 EM, above both Dense-Hop and GraphWalker-QA.

Keywords: distillation, efficiency, low-resource languages, hybrid retrieval

## 1 Introduction

GraphFuse [1] fused dense and graph retrieval, reaching 46.3 EM on 3-hop KaveriHop and 22.7 EM on 4-hop TriHop-Bench, at roughly twice the cost of a single retriever. Earlier work on Tamil [2] found graph retrieval alone unhelpful.

## 2 Method

LiteGraphFuse extends GraphFuse [1]: a GraphFuse teacher labels 200,000 candidate chains and a 3B student learns to reproduce the fusion scores. We cap the walk at two expansions per hop.

## 3 Experiments

We evaluate on KaveriHop [3] and VaigaiQA [2], and measure latency for GraphFuse and LiteGraphFuse on the same GPU. Dense-Hop [4] and GraphWalker-QA [5] numbers on VaigaiQA are quoted from the VaigaiQA paper. Distillation keeps 95% of GraphFuse's accuracy at about one quarter of its latency. Fusion helps on Tamil even though graph retrieval alone does not.

| Method | Source | Kaveri-Hop 2-hop EM | Kaveri-Hop 3-hop EM | Kaveri-Hop latency (ms/query) | VaigaiQA 2-hop EM |
|---|---|---|---|---|---|
| GraphFuse | [1] | 57.9 | 46.3 | – | – |
| GraphFuse | ours | – | – | 420 | – |
| LiteGraphFuse | ours | 55.0 | 43.9 | 105 | 38.6 |
| Dense-Hop | [2] | – | – | – | 33.0 |
| GraphWalker-QA | [2] | – | – | – | 30.2 |

*Table 1: Exact match and latency.*

## 4 Limitations

We did not evaluate on TriHop-Bench.

## References

[1] Fischer, L., Mehta, R., and Das, P. (2024). GraphFuse: Fusing Dense and Graph Retrieval for Multi-Hop QA. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[2] Raman, K., Das, P., and Selvam, A. (2024). VaigaiQA: multi-hop QA in Tamil. In Proceedings of the Workshop on Low-Resource NLP.
[3] Sundaram, M., Iyer, A., and Ruiz, T. (2022). KaveriHop: A Benchmark for Two- and Three-Hop Question Answering. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[4] Iyer, A., Mehta, R., and Fischer, L. (2021). DenseHop: Iterative Dense Retrieval for Multi-Hop Questions. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[5] Fischer, L., Weber, J., and Das, P. (2022). GraphWalker-QA: Answering Multi-Hop Questions by Walking Entity Graphs. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).

---
*Synthetic paper for the GraphMind hackathon dataset. Authors, institutions, datasets and results are fictional.*
