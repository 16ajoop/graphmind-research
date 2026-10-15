# Entity Linking Is the Bottleneck: Error Analysis of Graph Retrieval in Low-Resource Languages

Priyanka Das (1), Kavitha Raman (2)

(1) Bay of Bengal Institute of Technology   (2) Vaigai Institute of Language Technology

LoResNLP 2025 · Published 30 July 2025

## Abstract

Two recent findings question graph-based multi-hop retrieval: a reproduction study found that GraphWalker-QA's 3-hop gains need gold entity links, and a Tamil benchmark found graph retrieval below dense retrieval. We analyse 600 failed questions from both settings. In 71% of failures the first wrong step is an entity-linking error. LinkLite reaches 84.0% accuracy on English KaveriHop passages but 61.0% on Tamil. Low entity-linking accuracy explains both the failed reproduction of GraphWalker-QA and the drop of graph retrieval on Tamil.

Keywords: entity linking, error analysis, Tamil, graph-based retrieval

## 1 Introduction

GraphWalker-QA [1] connects passages through linked entities, so every linking error removes or corrupts an edge. The reproduction study [2] and the VaigaiQA paper [3] both observed weaker graph retrieval under realistic linking, and our analysis supports both findings.

## 2 Analysis

We sample 300 failures from KaveriHop [4] with LinkLite [5] links and 300 from VaigaiQA, and label the first incorrect step of each retrieval chain.

| Method | Source | KaveriHop EL accuracy | VaigaiQA EL accuracy |
|---|---|---|---|
| LinkLite | ours | 84.0 | – |
| LinkLite | [3] | – | 61.0 |

*Table 1: Entity linking accuracy of LinkLite.*

## 3 Conclusion

Low entity-linking accuracy explains both the failed reproduction of GraphWalker-QA and the drop of graph retrieval on Tamil. Better entity linking, especially for Tamil, is the most direct way to make graph retrieval useful. No current Tamil entity linker is designed for multi-hop retrieval.

## References

[1] Fischer, L., Weber, J., and Das, P. (2022). GraphWalker-QA: Answering Multi-Hop Questions by Walking Entity Graphs. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[2] Okafor, S., Zhang, W., and Weber, J. (2024). Revisiting graph gains: a reproduction of GraphWalker-QA. Journal of Applied Language Systems.
[3] Raman, K., Das, P., and Selvam, A. (2024). VaigaiQA: Multi-Hop Question Answering in Tamil. In Proceedings of the Workshop on Low-Resource NLP.
[4] Sundaram, M., Iyer, A., and Ruiz, T. (2022). KaveriHop: A Benchmark for Two- and Three-Hop Question Answering. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[5] Brown, T. and Lee, J. (2019). LinkLite: Lightweight Multilingual Entity Linking. JALS.

---
*Synthetic paper for the GraphMind hackathon dataset. Authors, institutions, datasets and results are fictional.*
