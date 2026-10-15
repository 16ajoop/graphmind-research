# DenseHop: Iterative Dense Retrieval for Multi-Hop Questions

Ananya Iyer (1), Rahul Mehta (1), Lena Fischer (2)

(1) University of Coromandel   (2) Rhinebrook Technical University

ICRR 2021 · Published 10 May 2021

## Abstract

Multi-hop questions require evidence from several passages, and a single retrieval step often misses the second passage. We present DenseHop, an iterative dense retriever that reformulates the query after each hop using the passages retrieved so far. On the two-hop NarmadaQA benchmark, DenseHop reaches 61.3 exact match (EM), compared with 54.8 EM for the sparse ChainTFIDF retriever. Iterative dense retrieval outperforms sparse chain retrieval on two-hop questions. We release code and trained encoders.

Keywords: multi-hop retrieval, dense retrieval, question answering

## 1 Introduction

Answering a question such as 'Which river flows through the city where the poet was born?' needs two facts from two different passages. Sparse chain retrievers [2] follow lexical overlap between passages and fail when the bridge entity is paraphrased. Dense encoders [1] capture meaning but retrieve only once. DenseHop combines both ideas: it retrieves densely, appends the retrieved passage to the query, and retrieves again.

## 2 Related Work

Single-step dense retrieval was popularised by dense passage retrieval [1]. Multi-hop datasets such as HotpotQA [3] and NarmadaQA [2] motivated chained retrieval. Rao et al. [2] introduced NarmadaQA together with the ChainTFIDF baseline, which we use as our main comparison.

## 3 Method

DenseHop uses a question encoder and a passage encoder initialised from dense passage retrieval [1]. At hop t the query is the question concatenated with the passages retrieved at hops 1 to t-1. We retrieve the top 20 passages per hop and keep the best chain by the product of hop scores. Training uses hard negatives mined from the previous hop.

## 4 Experiments

We evaluate on the 2-hop split of NarmadaQA [2] and report exact match of the final answer produced by a fixed reader. Table 1 compares DenseHop with the ChainTFIDF number reported by Rao et al. [2]. DenseHop improves EM by 6.5 points.

| Method | Source | NarmadaQA 2-hop EM |
|---|---|---|
| ChainTFIDF | [2] | 54.8 |
| DenseHop | ours | 61.3 |

*Table 1: Exact match on NarmadaQA (2-hop).*

## 5 Conclusion

Iterative dense retrieval outperforms sparse chain retrieval on two-hop questions. We have not yet tested questions with three or more hops, where errors from early hops may compound.

## References

[1] Karpukhin, V., Oguz, B., Min, S., Lewis, P., Wu, L., Edunov, S., Chen, D., and Yih, W. (2020). Dense Passage Retrieval for Open-Domain Question Answering. EMNLP.
[2] Rao, A., Kulkarni, B., and Nair, S. (2020). NarmadaQA: A Two-Hop Question Answering Dataset over Encyclopedic Text. ICRR.
[3] Yang, Z., Qi, P., Zhang, S., Bengio, Y., Cohen, W., Salakhutdinov, R., and Manning, C. D. (2018). HotpotQA: A Dataset for Diverse, Explainable Multi-hop Question Answering. EMNLP.

---
*Synthetic paper for the GraphMind hackathon dataset. Authors, institutions, datasets and results are fictional.*
