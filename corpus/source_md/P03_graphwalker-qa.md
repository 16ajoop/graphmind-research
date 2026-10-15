# GraphWalker-QA: Answering Multi-Hop Questions by Walking Entity Graphs

Lena Fischer (1), Jonas Weber (1), Priyanka Das (2)

(1) Rhinebrook Technical University   (2) Bay of Bengal Institute of Technology

ICRR 2022 · Published 20 September 2022

## Abstract

We propose GraphWalker-QA, which builds an entity graph over the corpus and answers multi-hop questions by walking from question entities to answer passages. On KaveriHop, GraphWalker-QA improves over DenseHop by 2.1 EM on 2-hop and 7.9 EM on 3-hop questions. Walking an entity graph gives larger gains on 3-hop questions than on 2-hop questions, suggesting that explicit structure helps longer reasoning chains.

Keywords: graph-based retrieval, entity graph, multi-hop question answering

## 1 Introduction

Dense retrievers such as DenseHop [1] reformulate queries in vector space, but each hop can drift away from the bridge entity. Building on the success of dense passage retrieval [4], we instead make bridge entities explicit: passages become nodes connected through shared entities, and retrieval becomes a walk.

## 2 Method

We link entity mentions in every passage and connect passages that share an entity. Given a question, we start from passages that mention the question entities and expand neighbours, scoring each step with a learned edge scorer. For KaveriHop [2] we take entity links from the dataset's entity annotations; for NarmadaQA [3] we use string matching.

## 3 Experiments

We compare against DenseHop [1]. On NarmadaQA we quote its published number; on KaveriHop [2] we re-run DenseHop with the released code, obtaining 48.0 and 31.9 EM, close to the numbers in the KaveriHop paper.

| Method | Source | NarmadaQA 2-hop EM | KaveriHop 2-hop EM | KaveriHop 3-hop EM |
|---|---|---|---|---|
| DenseHop | [1] | 61.3 | – | – |
| GraphWalker-QA | ours | 62.0 | 50.1 | 39.8 |
| DenseHop | ours (re-run) | – | 48.0 | 31.9 |

*Table 1: Exact match on NarmadaQA and KaveriHop.*

## 4 Analysis

The gain over DenseHop grows from 2.1 EM on 2-hop to 7.9 EM on 3-hop questions. Walking an entity graph gives larger gains on 3-hop questions than on 2-hop questions.

## 5 Limitations

Our walk depends on entity links. We did not measure how errors in entity linking affect accuracy.

## References

[1] Iyer, A., Mehta, R., and Fischer, L. (2021). DenseHop: Iterative Dense Retrieval for Multi-Hop Questions. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[2] Sundaram, M., Iyer, A., and Ruiz, T. (2022). KaveriHop: A Benchmark for Two- and Three-Hop Question Answering. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).
[3] Rao, A., Kulkarni, B., and Nair, S. (2020). NarmadaQA: A Two-Hop Question Answering Dataset over Encyclopedic Text. ICRR.
[4] Karpukhin, V., Oguz, B., Min, S., Lewis, P., Wu, L., Edunov, S., Chen, D., and Yih, W. (2020). Dense Passage Retrieval for Open-Domain Question Answering. EMNLP.

---
*Synthetic paper for the GraphMind hackathon dataset. Authors, institutions, datasets and results are fictional.*
