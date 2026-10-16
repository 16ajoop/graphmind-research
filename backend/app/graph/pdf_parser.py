"""Deterministic PDF parsing for research papers (PyMuPDF).

Pulls out header (title, authors, affiliations, venue, date), abstract, keywords, sections, tables,
references and the sentences in which each reference is cited. Works on the synthetic corpus as-is;
for arbitrary real PDFs, fields it cannot find are returned empty so the LLM fallback can fill them.
"""
import re
from dataclasses import dataclass, field

import pymupdf

REF_START = re.compile(r"^\[(\d+)\]\s+")
CITE = re.compile(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\]")
APA_REF = re.compile(r"^(?P<authors>.+?) \((?P<year>(?:19|20)\d{2})\)\. (?P<title>.+?)\. (?P<venue>.+?)\.?$")
VENUE_LINE = re.compile(r"^(?P<venue>.+?) (?P<year>(?:19|20)\d{2}) · Published (?P<date>.+)$")
AUTHOR_WITH_NO = re.compile(r"\s*(?P<name>[^,(]+?)\s*\((?P<n>\d+)\)")
AFFIL = re.compile(r"\((\d+)\)\s*([^()]+?)(?=\s*\(\d+\)|$)")
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                       "august", "september", "october", "november", "december"], 1)}


def iso_date(text: str, year: int) -> str:
    """'20 September 2022' -> '2022-09-20'. Cypher compares strings character by character, so dates must be
    ISO: as printed, '5 June 2024' > '30 July 2025' and every 'published before' query would be wrong."""
    m = re.match(r"^\s*(\d{1,2})\s+([A-Za-z]+)\.?\s+(\d{4})\s*$", text)
    if m:
        month = next((n for name, n in MONTHS.items() if name.startswith(m[2].lower()[:3])), None)
        if month:
            return f"{m[3]}-{month:02d}-{int(m[1]):02d}"
    return str(year)          # unknown format: the year alone still sorts correctly against ISO dates


@dataclass
class ParsedPaper:
    file: str
    title: str = ""
    authors: list = field(default_factory=list)       # [{name, affiliation}]
    venue: str = ""
    year: int | None = None
    published: str = ""
    abstract: str = ""
    keywords: list = field(default_factory=list)
    sections: list = field(default_factory=list)      # [{heading, text}]
    tables: list = field(default_factory=list)        # [{caption, header, rows}]
    references: list = field(default_factory=list)    # [{n, raw, authors, year, title, venue}]
    citations: list = field(default_factory=list)     # [{ref_n, section, sentence}]


def _lines(doc):
    """Text lines in reading order with font info, skipping table cells and page footers."""
    out, tables = [], []
    for page in doc:
        found = page.find_tables()
        boxes = [pymupdf.Rect(t.bbox) for t in found.tables]
        for t in found.tables:
            rows = t.extract()
            tables.append({"page": page.number, "y": t.bbox[1], "header": rows[0], "rows": rows[1:]})
        footer_y = page.rect.height - 15 * 2.835  # bottom 15 mm
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                rect = pymupdf.Rect(line["bbox"])
                if rect.y0 > footer_y or any(rect.intersects(b) for b in boxes):
                    continue
                out.append({
                    "page": page.number, "y": rect.y0,
                    "text": " ".join(s["text"].strip() for s in spans),
                    "size": round(max(s["size"] for s in spans), 1),
                    "bold": any("Bold" in s["font"] for s in spans),
                    "italic": all("Oblique" in s["font"] or "Italic" in s["font"] for s in spans),
                })
    return out, tables


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\[])", text) if s.strip()]


def parse_reference(n, raw):
    m = APA_REF.match(raw)
    if not m:
        return {"n": n, "raw": raw, "authors": "", "year": None, "title": "", "venue": ""}
    return {"n": n, "raw": raw, "authors": m["authors"], "year": int(m["year"]), "title": m["title"], "venue": m["venue"]}


def parse_pdf(path) -> ParsedPaper:
    doc = pymupdf.open(path)
    meta = doc.metadata or {}
    lines, tables = _lines(doc)
    doc.close()   # release the file now: on Windows an open handle blocks deleting or replacing the upload
    paper = ParsedPaper(file=str(path))

    # Header: title = largest font on page 1; then author line, affiliation line, venue line.
    first = [l for l in lines if l["page"] == 0]
    max_size = max(l["size"] for l in first)
    title_lines = [l for l in first if l["size"] == max_size]
    paper.title = " ".join(l["text"] for l in title_lines) or meta.get("title", "")
    after_title = [l for l in first if l["y"] > title_lines[-1]["y"]]
    header_lines = []
    for l in after_title:            # header ends at the first heading ("Abstract")
        if l["bold"] or len(header_lines) == 4:
            break
        header_lines.append(l)
    affil_map = {}
    for l in header_lines:
        if l["italic"] and l["text"].startswith("("):
            affil_map = {n: name.strip() for n, name in AFFIL.findall(l["text"])}
    for l in header_lines:
        if AUTHOR_WITH_NO.search(l["text"]) and not l["text"].startswith("("):
            paper.authors = [{"name": m["name"].strip(), "affiliation": affil_map.get(m["n"], "")}
                             for m in AUTHOR_WITH_NO.finditer(l["text"])]
        if (vm := VENUE_LINE.match(l["text"])):
            paper.venue, paper.year = vm["venue"], int(vm["year"])
            paper.published = iso_date(vm["date"], paper.year)
    if not paper.authors and meta.get("author"):
        paper.authors = [{"name": a.strip(), "affiliation": ""} for a in meta["author"].split(";")]

    # Body: bold lines of size >= 10.5 are headings; everything else is appended to the current section.
    current, buf, refs, ref_buf = None, [], [], None
    body_start = header_lines[-1]["y"] if header_lines else 0
    def flush():
        if current is not None:
            text = " ".join(buf).strip()
            if current == "Abstract":
                paper.abstract = text
            elif current != "References":
                paper.sections.append({"heading": current, "text": text})
    for l in lines:
        if l["page"] == 0 and l["y"] <= body_start:
            continue
        if l["bold"] and l["size"] >= 10.5:
            flush()
            current, buf = l["text"], []
            continue
        if l["italic"] and l["text"].startswith("Keywords:"):
            paper.keywords = [k.strip() for k in l["text"].split(":", 1)[1].split(",")]
            continue
        if l["italic"] and re.match(r"^Table \d+:", l["text"]):
            # caption belongs to the nearest table above it on the same page
            cands = [t for t in tables if t["page"] == l["page"] and t["y"] < l["y"]]
            if cands:
                max(cands, key=lambda t: t["y"])["caption"] = l["text"]
            continue
        if current == "References":
            if (m := REF_START.match(l["text"])):
                if ref_buf:
                    refs.append(ref_buf)
                ref_buf = [int(m[1]), l["text"][m.end():]]
            elif ref_buf:
                ref_buf[1] += " " + l["text"]
            continue
        buf.append(l["text"])
    flush()
    if ref_buf:
        refs.append(ref_buf)
    paper.references = [parse_reference(n, raw.strip()) for n, raw in refs]
    paper.tables = [{"caption": t.get("caption", ""), "header": t["header"], "rows": t["rows"]} for t in tables]

    # Citation contexts: every sentence that contains [n] (also [1, 3] and [2-4]).
    for sec in paper.sections:
        for sentence in _sentences(sec["text"]):
            for group in CITE.findall(sentence):
                nums = set()
                for part in re.split(r"\s*,\s*", group):
                    if re.search(r"[–-]", part):
                        a, b = map(int, re.split(r"\s*[–-]\s*", part))
                        nums.update(range(a, b + 1))
                    else:
                        nums.add(int(part))
                for n in sorted(nums):
                    paper.citations.append({"ref_n": n, "section": sec["heading"], "sentence": sentence})
    return paper
