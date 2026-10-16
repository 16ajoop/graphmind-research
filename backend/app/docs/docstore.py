"""ChromaDB passage store. FalkorDB decides WHICH paper/section proves a relationship;
ChromaDB finds the best PASSAGE inside it. Chunk metadata paper_id == FalkorDB Paper.id."""
import os

import chromadb
import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")


def ollama_embed(texts: list[str], kind: str) -> list[list[float]]:
    """nomic-embed-text wants task prefixes: 'search_document: ' for passages, 'search_query: ' for questions."""
    prefix = "search_document: " if kind == "document" else "search_query: "
    r = httpx.post(f"{OLLAMA_URL}/api/embed", json={"model": EMBED_MODEL, "input": [prefix + t for t in texts]}, timeout=120)
    r.raise_for_status()
    return r.json()["embeddings"]


def chunk(text: str, max_chars: int = 700) -> list[str]:
    sentences, out, cur = text.replace("\n", " ").split(". "), [], ""
    for s in sentences:
        s = s if s.endswith(".") else s + "."
        if cur and len(cur) + len(s) > max_chars:
            out.append(cur.strip())
            cur = ""
        cur += " " + s
    return out + ([cur.strip()] if cur.strip() else [])


class DocStore:
    def __init__(self, path: str, workspace: str, embed=ollama_embed):
        self.client = chromadb.PersistentClient(path=path)
        self.embed = embed
        # one collection per workspace, mirroring one FalkorDB graph per workspace
        self.col = self.client.get_or_create_collection(f"papers_{workspace}", configuration={"hnsw": {"space": "cosine"}})

    def add_paper(self, paper_id: str, title: str, abstract: str, sections: list[dict]) -> int:
        self.col.delete(where={"paper_id": paper_id})          # re-upload replaces old chunks
        ids, docs, metas = [], [], []
        for sec in [{"heading": "Abstract", "text": abstract}] + sections:
            for i, piece in enumerate(chunk(sec["text"])):
                ids.append(f"{paper_id}#{sec['heading']}#{i}")
                docs.append(piece)
                metas.append({"paper_id": paper_id, "title": title, "section": sec["heading"], "chunk": i})
        if ids:
            self.col.add(ids=ids, documents=docs, metadatas=metas, embeddings=self.embed(docs, "document"))
        return len(ids)

    def evidence(self, claim: str, paper_ids: list[str] | None = None, k: int = 3) -> list[dict]:
        where = None
        if paper_ids:
            where = {"paper_id": paper_ids[0]} if len(paper_ids) == 1 else {"paper_id": {"$in": paper_ids}}
        res = self.col.query(query_embeddings=self.embed([claim], "query"), n_results=k, where=where,
                             include=["documents", "metadatas", "distances"])
        return [{"chunk_id": cid, "paper_id": m["paper_id"], "title": m["title"], "section": m["section"],
                 "excerpt": d, "similarity": round(1 - dist, 3)}
                for cid, d, m, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0])]

    def section_vector(self, paper_id: str, section_word: str = "Method") -> list[float] | None:
        """Mean embedding of a paper's method section, used for SIMILAR_TO between methods."""
        got = self.col.get(where={"paper_id": paper_id}, include=["embeddings", "metadatas"])
        vecs = [e for e, m in zip(got["embeddings"], got["metadatas"]) if section_word.lower() in m["section"].lower()]
        if not len(vecs):
            return None
        return [sum(col) / len(vecs) for col in zip(*vecs)]
