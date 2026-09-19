"""Hybrid evidence ranking: BM25 + dense vectors (reciprocal-rank fusion), then an LLM rerank by importance.

The LLM only orders evidence that already exists in the run; it never creates numbers. Its output is validated
(ids must exist, scores in [0, 1]) and anything invalid falls back to the fused order.

Backends
- dense vectors: OpenAI embeddings (live) or a local hashed n-gram TF-IDF vectorizer (demo/offline)
- reranker: any OpenAI-compatible chat model — OpenAI by default, or Baseten when RERANK_BASE_URL/RERANK_API_KEY/RERANK_MODEL
  are set (Baseten model APIs are OpenAI-compatible); a deterministic reliability-weighted order in demo mode
Embeddings and rerank responses are cached on disk.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from backend.settings import CACHE_DIR

QUESTIONS = {
    "threshold": "Does the facility's methane emission rate exceed the federal super-emitter threshold, and how certain is the estimate?",
    "reporting": "Was the release reported to the Texas regulator (TCEQ) as an emissions event, and do the operator's reports match the satellite observation?",
    "attribution": "Is the methane plume attributable to this facility, based on plume origin, wind and imagery?",
    "cause": "What is the likely cause of the release (flare malfunction, venting, blowdown) and what physical evidence supports it?",
    "reliability": "Which data are unreliable, synthetic, missing or in conflict, and how do they limit the conclusion?",
}
RRF_K = 60
TOP_N = 10


@dataclass
class Item:
    id: str
    text: str
    kind: str
    source: str
    reliability: float
    flags: list[str] = field(default_factory=list)
    label: str = ""  # short plain-English statement for display


# ------------------------------------------------------------------ corpus
def build_corpus(st) -> list[Item]:
    """One short, self-contained statement per piece of evidence produced in this run."""
    items: list[Item] = []
    seen = set()

    def add(id_, text, kind, source, rel, flags=None, label=""):
        if id_ in seen or not text:
            return
        seen.add(id_)
        text = re.sub(r"\s+", " ", text).strip()
        items.append(Item(id_, text, kind, source, rel, flags or [], label or _first_sentence(text)))

    for rec in st.ledger.values():
        t = rec.get("type")
        if t == "data":
            flags = (["synthetic"] if rec.get("synthetic") else []) + (["low_quality"] if rec.get("quality") == "low" else [])
            rel = 0.2 if rec.get("synthetic") else 0.35 if rec.get("quality") == "low" else 0.9
            warn = "; ".join(rec.get("warnings") or [])
            add(rec["id"], f"{rec.get('source_name')}: {rec.get('subset') or ''}. Coverage {rec.get('date_coverage')}. {warn}",
                "data", rec.get("provider") or rec["id"], rel, flags,
                f"{rec.get('source_name')}" + (" (placeholder data)" if rec.get("synthetic") else " (low quality)" if rec.get("quality") == "low" else ""))
        elif t == "assumption":
            add(rec["id"], f"Assumption {rec.get('name')} = {rec.get('value')} {rec.get('unit') or ''}: {rec.get('rationale')}"
                + (" (needs verification)" if rec.get("verify") else ""), "assumption", rec.get("source", "config"),
                0.5 if rec.get("verify") else 0.7, ["unverified"] if rec.get("verify") else [],
                f"Assumption: {rec.get('name')} = {rec.get('value')} {rec.get('unit') or ''}".strip())
        elif t == "ai_analysis":
            add(rec["id"], f"Huawei OMNI read of {rec.get('target_id')} ({rec.get('mode')}): {rec.get('answer')}", "ai_analysis",
                "Huawei OMNI", 0.55 if rec.get("mode") in ("LIVE", "CACHED") else 0.3,
                [] if rec.get("mode") in ("LIVE", "CACHED") else ["demo_text"],
                f"Image/document reading of {str(rec.get('target_id')).replace('_', ' ')}: {_first_sentence(str(rec.get('answer')))}")
    # tool findings (latest successful result per tool)
    latest = {}
    for c in st.tool_calls:
        if c["status"] == "ok":
            latest[c["name"]] = c
    skip = {"list_skills", "load_skill", "show_chart", "submit_verdict", "rank_evidence", "find_facility", "describe_dataset"}
    for name, c in latest.items():
        if name in skip:
            continue
        res = st.results["_calls"][c["call_id"]]
        add(f"finding:{name}", f"{name}: {res['summary']}", "finding", name, 0.85,
            ["has_warnings"] if res.get("warnings") else [], _first_sentence(res["summary"]))
    for r in st.results.get("regulations", []):
        add(f"rule:{r['rule_id']}", f"Rule {r['rule_id']} ({r['rule']}): status {r['status']}. Observed {r['observed']}. {r['note']}",
            "rule", "check_regulations", 0.9, None,
            f"{RULE_LABELS.get(r['rule_id'], r['rule_id'])}: {r['status'].replace('_', ' ').lower()}"
            + (f" ({r['observed']})" if r.get("observed") not in (None, "", "n/a") else ""))
    cmp_ = st.results.get("comparison")
    if cmp_:
        add("finding:cross_check", f"Carbon Mapper cross-check ratio {cmp_['ratio']}; consistent={cmp_['consistent']}; "
            + "; ".join(cmp_.get("notes", [])), "finding", "compare_estimates", 0.2 if cmp_.get("synthetic") else 0.8,
            ["synthetic"] if cmp_.get("synthetic") else [],
            f"Carbon Mapper cross-check: ratio {cmp_['ratio']}" + (" (placeholder value)" if cmp_.get("synthetic") else ""))
    ph = st.results.get("physics")
    if ph:
        add("finding:physics", f"Physics: {ph['interpretation']} Required flared CH4 {ph['required_flared_ch4_t_h']} t/h vs "
            f"plant ceiling {ph['ceiling_t_h']} t/h ({ph['classification']}).", "finding", "physics_bounds", 0.8, None,
            f"Flare slip would need {ph['required_flared_ch4_t_h']:,.0f} t/h flared vs a {ph['ceiling_t_h']:.0f} t/h plant ceiling")
    rc = st.results.get("report_comparison") or {}
    if rc:
        add("finding:reports", f"Operator reports on file: {len(rc.get('reported_events', []))}; reported within ±1 day of "
            f"{rc.get('event_date')}: {len(rc.get('reported_on_event_date', []))}. Methane itemised in any report: "
            f"{rc.get('methane_reported_anywhere')}. {rc.get('note', '')}", "finding", "TCEQ STEERS", 0.85, None,
            f"No emissions-event report within ±1 day of {rc.get('event_date')}" if not rc.get("reported_on_event_date")
            else f"Emissions-event report filed for {rc.get('event_date')}")
    return items


RULE_LABELS = {
    "US_SUPER_EMITTER": "Federal super-emitter threshold", "TX_EMISSIONS_EVENT_REPORTING": "Texas emissions-event reporting",
    "PLANT_PHYSICS_CEILING": "Plant capacity check", "NOX_PERMIT_LIMITS": "NOx permit limits", "GHGRP_REPORTED": "EPA greenhouse gas reporting",
}


def _first_sentence(t: str, n: int = 150) -> str:
    t = re.sub(r"\s+", " ", t).strip().lstrip("{").strip()
    m = re.search(r"(?<=[.!?])\s", t)
    s = t[: m.start()] if m else t
    return s if len(s) <= n else s[: n - 1] + "…"


# ------------------------------------------------------------------ retrieval
_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-][a-z0-9]+)*")
STOP = set("""a an and are as at be by did do does for from how in into is it its of on or that the their this to
was were what which with within whether""".split())


def tokenize(s: str) -> list[str]:
    """Lowercase terms without stop words; hyphenated terms also contribute their parts (super-emitter → super, emitter)."""
    out = []
    for t in _TOKEN.findall(s.lower()):
        if t in STOP:
            continue
        out.append(t)
        if "-" in t:
            out += [p for p in t.split("-") if p and p not in STOP]
    return out


def bm25_scores(query: str, docs: list[str], k1: float = 1.5, b: float = 0.75) -> np.ndarray:
    toks = [tokenize(d) for d in docs]
    N = len(toks)
    avgdl = sum(map(len, toks)) / max(N, 1)
    df = Counter(t for d in toks for t in set(d))
    out = np.zeros(N)
    for qt in set(tokenize(query)):
        if qt not in df:
            continue
        idf = math.log(1 + (N - df[qt] + 0.5) / (df[qt] + 0.5))
        for i, d in enumerate(toks):
            f = d.count(qt)
            if f:
                out[i] += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * len(d) / avgdl))
    return out


def _hash_vec(text: str, dim: int = 1024) -> np.ndarray:
    """Local dense-ish vector: hashed word + char-trigram counts, L2-normalised (offline fallback)."""
    v = np.zeros(dim)
    words = tokenize(text)
    grams = words + [w[i:i + 3] for w in words for i in range(max(1, len(w) - 2))]
    for g in grams:
        h = int(hashlib.md5(g.encode()).hexdigest(), 16)
        v[h % dim] += 1.0 if (h >> 20) & 1 else -1.0
    n = np.linalg.norm(v)
    return v / n if n else v


class Embedder:
    def __init__(self, live: bool, client_factory: Callable | None = None, model: str | None = None):
        self.live = live and bool(os.getenv("OPENAI_API_KEY"))
        self.model = model or os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self.client_factory = client_factory
        self.name = f"openai:{self.model}" if self.live else "local-hashed-ngram"
        self.dir = CACHE_DIR / "embeddings"
        self.dir.mkdir(parents=True, exist_ok=True)

    def embed(self, texts: list[str]) -> np.ndarray:
        if not self.live:
            return np.stack([_hash_vec(t) for t in texts])
        keys = [hashlib.sha256((self.model + "\0" + t).encode()).hexdigest() for t in texts]
        out: dict[int, list[float]] = {}
        todo = []
        for i, k in enumerate(keys):
            f = self.dir / f"{k}.json"
            if f.exists():
                out[i] = json.loads(f.read_text())
            else:
                todo.append(i)
        if todo:
            try:
                client = self.client_factory() if self.client_factory else _openai()
                r = client.embeddings.create(model=self.model, input=[texts[i] for i in todo])
                for i, d in zip(todo, r.data):
                    out[i] = d.embedding
                    (self.dir / f"{keys[i]}.json").write_text(json.dumps(d.embedding))
            except Exception as e:  # noqa: BLE001 — degrade to the local vectorizer
                self.live, self.name = False, f"local-hashed-ngram (embeddings unavailable: {str(e)[:80]})"
                return np.stack([_hash_vec(t) for t in texts])
        m = np.array([out[i] for i in range(len(texts))], float)
        return m / np.linalg.norm(m, axis=1, keepdims=True)


def _openai():
    from openai import OpenAI
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=60, max_retries=1)


def rrf(*rankings: list[int], k: int = RRF_K) -> dict[int, float]:
    fused: dict[int, float] = {}
    for rank in rankings:
        for pos, idx in enumerate(rank):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + pos + 1)
    return fused


def hybrid_candidates(question: str, items: list[Item], item_vecs: np.ndarray, q_vec: np.ndarray, top_n: int = TOP_N):
    bm = bm25_scores(question, [i.text for i in items])
    dense = item_vecs @ q_vec
    bm_rank = [int(i) for i in np.argsort(-bm) if bm[i] > 0]
    dense_rank = [int(i) for i in np.argsort(-dense)]
    fused = rrf(bm_rank, dense_rank)
    order = sorted(fused, key=lambda i: -fused[i])[:top_n]
    return [{"idx": i, "fused": fused[i], "bm25": float(bm[i]), "dense": float(dense[i])} for i in order]


# ------------------------------------------------------------------ rerank
class Reranker:
    def __init__(self, live: bool, client_factory: Callable | None = None):
        base = os.getenv("RERANK_BASE_URL", "").strip()
        self.provider = "baseten" if base and "baseten" in base else ("custom" if base else "openai")
        self.model = os.getenv("RERANK_MODEL", "").strip() or os.getenv("OPENAI_MODEL", "").strip()
        key = os.getenv("RERANK_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
        self.live = live and bool(key) and bool(self.model)
        self.client_factory = client_factory or (lambda: _compat_client(base or None, key))
        self.name = f"{self.provider}:{self.model}" if self.live else "demo: fused rank × reliability"
        self.dir = CACHE_DIR / "rerank"
        self.dir.mkdir(parents=True, exist_ok=True)

    def rank(self, qkey: str, question: str, cands: list[dict], items: list[Item]) -> tuple[list[dict], str]:
        if not self.live:
            return self._demo(cands, items), "demo"
        payload = [{"id": items[c["idx"]].id, "text": items[c["idx"]].text[:400], "reliability_prior": items[c["idx"]].reliability,
                    "flags": items[c["idx"]].flags} for c in cands]
        prompt = (
            "You rank evidence for an environmental regulator's methane screening verdict.\n"
            f"Question: {question}\n"
            "Rank the candidate evidence by how important it is for answering the question. Prefer direct, measured, "
            "reliable evidence; down-weight synthetic, demo or low-quality items but keep items that explain limitations. "
            "Do not invent evidence or numbers. Return JSON only: {\"ranking\": [{\"id\": \"<candidate id>\", "
            "\"importance\": <0..1>, \"reason\": \"<max 15 words>\"}]} covering every candidate once.\n"
            f"Candidates: {json.dumps(payload, ensure_ascii=False)}")
        key = hashlib.sha256((self.name + "\0" + prompt).encode()).hexdigest()
        f = self.dir / f"{key}.json"
        if f.exists():
            raw, mode = f.read_text(encoding="utf-8"), "cached"
        else:
            try:
                raw, mode = _call_llm(self.client_factory(), self.model, prompt), "live"
                f.write_text(raw, encoding="utf-8")
            except Exception as e:  # noqa: BLE001
                out = self._demo(cands, items)
                for o in out:
                    o["reason"] = f"reranker unavailable ({str(e)[:60]}); fused order"
                return out, "fallback"
        return validate_ranking(raw, cands, items), mode

    @staticmethod
    def _demo(cands: list[dict], items: list[Item]) -> list[dict]:
        top = max(c["fused"] for c in cands) if cands else 1.0
        out = [{"id": items[c["idx"]].id, "importance": round(c["fused"] / top * items[c["idx"]].reliability, 3),
                "reason": "hybrid rank weighted by source reliability"} for c in cands]
        return sorted(out, key=lambda o: -o["importance"])


def _compat_client(base_url: str | None, key: str):
    from openai import OpenAI
    return OpenAI(base_url=base_url, api_key=key, timeout=90, max_retries=1)


def _call_llm(client, model: str, prompt: str) -> str:
    """Responses API (low reasoning effort when supported), falling back to Chat Completions."""
    try:
        try:
            r = client.responses.create(model=model, input=prompt, reasoning={"effort": "low"})
        except Exception as e:  # noqa: BLE001 — model without reasoning controls
            if "reasoning" not in str(e).lower():
                raise
            r = client.responses.create(model=model, input=prompt)
        return r.output_text
    except Exception as e:  # noqa: BLE001
        if "responses" not in str(e).lower() and "404" not in str(e):
            raise
        c = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])
        return c.choices[0].message.content or ""


def validate_ranking(raw: str, cands: list[dict], items: list[Item]) -> list[dict]:
    """Keep only known candidate ids with numeric importance in [0,1]; append any the model dropped, in fused order."""
    from backend.llm.omni import parse_json
    valid = {items[c["idx"]].id for c in cands}
    parsed = parse_json(raw) or {}
    rows = parsed.get("ranking", parsed) if isinstance(parsed, dict) else parsed
    out, seen = [], set()
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict) or r.get("id") not in valid or r["id"] in seen:
            continue
        try:
            imp = min(1.0, max(0.0, float(r.get("importance", 0))))
        except (TypeError, ValueError):
            continue
        seen.add(r["id"])
        out.append({"id": r["id"], "importance": round(imp, 3), "reason": str(r.get("reason", ""))[:160]})
    out.sort(key=lambda o: -o["importance"])
    for c in cands:  # anything the model omitted keeps its fused position at the bottom
        iid = items[c["idx"]].id
        if iid not in seen:
            out.append({"id": iid, "importance": 0.0, "reason": "not ranked by the model"})
    return out


# ------------------------------------------------------------------ entry point
def rank(st, live: bool, embed_client: Callable | None = None, rerank_client: Callable | None = None) -> dict:
    items = build_corpus(st)
    if len(items) < 3:
        return {"items": len(items), "questions": {}, "key_evidence": [], "backends": {}}
    emb = Embedder(live, embed_client)
    vecs = emb.embed([i.text for i in items])
    q_vecs = emb.embed(list(QUESTIONS.values()))
    rr = Reranker(live, rerank_client)
    by_id = {i.id: i for i in items}
    questions, best, modes = {}, {}, set()
    cand_by_q = {qk: hybrid_candidates(q, items, vecs, qv) for (qk, q), qv in zip(QUESTIONS.items(), q_vecs)}
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=len(QUESTIONS)) as pool:  # the five reranks are independent
        futures = {qk: pool.submit(rr.rank, qk, QUESTIONS[qk], cand_by_q[qk], items) for qk in QUESTIONS}
        reranked = {qk: fut.result() for qk, fut in futures.items()}
    for qk, q in QUESTIONS.items():
        cands = cand_by_q[qk]
        ranked, mode = reranked[qk]
        modes.add(mode)
        fused = {items[c["idx"]].id: c for c in cands}
        questions[qk] = {"question": q, "ranking": [
            {**r, "text": by_id[r["id"]].text[:220], "label": by_id[r["id"]].label, "source": by_id[r["id"]].source, "kind": by_id[r["id"]].kind,
             "flags": by_id[r["id"]].flags, "bm25": round(fused[r["id"]]["bm25"], 3), "dense": round(fused[r["id"]]["dense"], 3),
             "fused": round(fused[r["id"]]["fused"], 4)} for r in ranked]}
        for r in ranked[:5]:
            if r["importance"] > best.get(r["id"], {}).get("importance", -1):
                best[r["id"]] = {**r, "question": qk}
    key = sorted(best.values(), key=lambda r: -r["importance"])[:8]
    key = [{**k, "text": by_id[k["id"]].text[:220], "label": by_id[k["id"]].label, "source": by_id[k["id"]].source,
            "flags": by_id[k["id"]].flags} for k in key]
    return {"items": len(items), "questions": questions, "key_evidence": key,
            "backends": {"lexical": "BM25 (k1=1.5, b=0.75)", "dense": emb.name, "fusion": f"reciprocal rank fusion (k={RRF_K})",
                         "reranker": rr.name, "rerank_modes": sorted(modes)}}
