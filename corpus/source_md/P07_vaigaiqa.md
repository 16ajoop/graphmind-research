# VaigaiQA: Multi-Hop Question Answering in Tamil

Kavitha Raman (1), Priyanka Das (2), Arun Selvam (1)

(1) Vaigai Institute of Language Technology   (2) Bay of Bengal Institute of Technology

LoResNLP 2024 · Published 5 June 2024

## Abstract

We introduce VaigaiQA, 5,200 two-hop questions written natively in Tamil over Tamil encyclopedic text. We evaluate Dense-Hop and GraphWalker-QA, using the LinkLite entity linker to build the graph. Unlike results reported for English, the graph-based method trails the dense one: 30.2 versus 33.0 EM. LinkLite links only 61.0% of Tamil mentions correctly. On Tamil questions, graph-based retrieval performs worse than dense retrieval because entity linking is unreliable.

Keywords: Tamil, low-resource languages, multi-hop question answering, dataset

## 1 Introduction

Multi-hop QA research has focused on English benchmarks such as KaveriHop [1]. Tamil text has rich morphology and many transliterated names, which makes entity linking harder.

## 2 Dataset

Native speakers wrote questions over pairs of linked Tamil passages. VaigaiQA contains only 2-hop questions; building a 3-hop Tamil subset is future work.

## 3 Systems

We train Dense-Hop [2] with multilingual encoders and run GraphWalker-QA [3] with entity links predicted by LinkLite [4], the only openly available Tamil entity linker.

| Method | Source | VaigaiQA 2-hop EM | VaigaiQA EL accuracy |
|---|---|---|---|
| Dense-Hop | ours | 33.0 | – |
| GraphWalker-QA | ours | 30.2 | – |
| LinkLite | ours | – | 61.0 |

*Table 1: Results on VaigaiQA (2-hop).*

## 4 Results

The graph-based retriever trails the dense retriever by 2.8 EM. On Tamil questions, graph-based retrieval performs worse than dense retrieval because entity linking is unreliable.

## 5 Limitations

We did not evaluate newer hybrid retrievers.

## References

[1] Sundaram, M., Iyer, A., and Ruiz, T. (2022). KaveriHop: A Benchmark for Two- and Three-Hop Question Answering. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[2] Iyer, A., Mehta, R., and Fischer, L. (2021). DenseHop: Iterative Dense Retrieval for Multi-Hop Questions. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[3] Fischer, L., Weber, J., and Das, P. (2022). GraphWalker-QA: Answering Multi-Hop Questions by Walking Entity Graphs. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[4] Brown, T. and Lee, J. (2019). LinkLite: Lightweight Multilingual Entity Linking. JALS.

---
*Synthetic paper for the GraphMind hackathon dataset. Authors, institutions, datasets and results are fictional.*
