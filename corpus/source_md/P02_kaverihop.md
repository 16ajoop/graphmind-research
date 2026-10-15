# KaveriHop: A Benchmark for Two- and Three-Hop Question Answering

Meenakshi Sundaram (1), Ananya Iyer (1), Tomás Ruiz (2)

(1) University of Coromandel   (2) Instituto Altamira

ICRR 2022 · Published 15 March 2022

## Abstract

Existing multi-hop QA benchmarks mostly contain two-hop questions. We introduce KaveriHop, a benchmark of 18,400 English questions split into 2-hop and 3-hop subsets, each with annotated bridge entities and supporting passages. Baselines degrade sharply with more hops: DenseHop falls from 48.2 EM on 2-hop to 31.5 EM on 3-hop questions. We release the data, the bridge-entity annotations and an evaluation script.

Keywords: benchmark, multi-hop question answering, dataset

## 1 Introduction

Benchmarks such as HotpotQA [1] and NarmadaQA [2] made two-hop reasoning measurable, but real questions often need three or more steps. KaveriHop fills this gap with a 3-hop subset built by chaining two bridge entities.

## 2 Dataset Construction

Annotators wrote questions over pairs or triples of linked encyclopedic passages. Every question includes gold bridge-entity annotations, which future work may use for analysis but should not use at test time. The 2-hop subset has 11,200 questions and the 3-hop subset 7,200.

## 3 Baselines

We run two baselines: the sparse ChainTFIDF retriever [2] and the iterative dense retriever DenseHop [3], using its released code. Both feed the same fixed reader.

| Method | Source | KaveriHop 2-hop EM | KaveriHop 3-hop EM |
|---|---|---|---|
| ChainTFIDF | ours | 39.7 | 22.4 |
| DenseHop | ours | 48.2 | 31.5 |

*Table 1: Exact match on KaveriHop.*

## 4 Results

Table 1 shows that accuracy of existing retrievers drops sharply from 2-hop to 3-hop questions: DenseHop loses 16.7 EM points and ChainTFIDF loses 17.3.

## 5 Conclusion

KaveriHop exposes the difficulty of longer reasoning chains. We encourage authors to report results on both subsets separately and to avoid using the gold bridge-entity annotations at test time.

## References

[1] Yang, Z., Qi, P., Zhang, S., Bengio, Y., Cohen, W., Salakhutdinov, R., and Manning, C. D. (2018). HotpotQA: A Dataset for Diverse, Explainable Multi-hop Question Answering. EMNLP.
[2] Rao, A., Kulkarni, B., and Nair, S. (2020). NarmadaQA: A Two-Hop Question Answering Dataset over Encyclopedic Text. ICRR.
[3] Iyer, A., Mehta, R., and Fischer, L. (2021). DenseHop: Iterative Dense Retrieval for Multi-Hop Questions. In Proceedings of the International Conference on Retrieval and Reasoning (ICRR).

---
*Synthetic paper for the GraphMind hackathon dataset. Authors, institutions, datasets and results are fictional.*
