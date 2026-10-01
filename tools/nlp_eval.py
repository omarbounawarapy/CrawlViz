"""Evaluate NLP link signals against weak LLM labels.

    uv run python -m tools.nlp_eval label     # label links with the LLM (cached)
    uv run python -m tools.nlp_eval report    # per-signal AUC + fitted composite weights

Labels come from a compact LLM scoring prompt (score 0-100 per link); a link
is "relevant" when score >= LABEL_THRESHOLD. They are cached in
tools/eval_data/labels.json so `report` never calls the LLM.
"""
import asyncio
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

import models.links_extractor as le
from infrastructure import KeyManager, LlmHandler
from models import ScoringContext
from services.nlp_service import NLPService
from services.scoring_service import ScoringService

DATA = Path(__file__).parent / "eval_data"
LABELS = DATA / "labels.json"
TEMPLATE = Path("templates/wikiMD.json")
PAGES = [
    "https://www.wikimd.org/wiki/Diabetes",
    "https://www.wikimd.org/wiki/Type_2_diabetes",
    "https://www.wikimd.org/wiki/Diabetic_retinopathy",
    "https://www.wikimd.org/wiki/Insulin",
    "https://www.wikimd.org/wiki/Diabetic_neuropathy",
]
LABEL_THRESHOLD = 60
BATCH = 50
LABEL_MODEL = ("groq", "openai/gpt-oss-120b")
CONTEXT_LEN = 100


def _template():
    t = json.loads(TEMPLATE.read_text())
    return t, next(iter(t["domains"].values()))


class _Node:
    def __init__(self, domain):
        self.d = domain

    def get_link_selector(self):
        return self.d["link_selector"]

    def get_domain_base_url(self):
        return self.d["base_url"]

    def get_url(self):
        return "eval"


def _fetch(url: str) -> str:
    """HTML of `url`, cached under tools/eval_data/pages (wikimd is flaky)."""
    cache = DATA / "pages" / (url.rsplit("/", 1)[1] + ".html")
    if not cache.exists():
        cache.parent.mkdir(exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
        for attempt in range(5):
            try:
                cache.write_text(urllib.request.urlopen(req, timeout=20).read().decode())
                break
            except Exception as e:  # noqa: BLE001 -- retry any network error
                print(f"fetch {url} failed ({type(e).__name__}), retry {attempt + 1}", flush=True)
                time.sleep(3)
        else:
            return ""
    return cache.read_text()


def load_page(url: str):
    """Fetch `url`; return (links, parent) with unique links and a parent stub
    whose `.content` is the page HTML, as on a crawled node."""
    _, domain = _template()
    page = _fetch(url)
    if not page:
        return [], None
    parent = type("Parent", (), {})()
    parent.content = page
    le.MAX_CONTEXT_LEN = CONTEXT_LEN
    seen, links = set(), []
    for link in le.LinkExtractor.extract_links(page, _Node(domain)):
        if link.url not in seen:
            seen.add(link.url)
            links.append(link)
    return links, parent


def _label_prompt(topic: str, prefix: str, batch) -> str:
    cands = [{"url": link.url.removeprefix(prefix), "anchor": link.anchor} for link in batch]
    return (
        f'Rate each web page link for relevance to the topic "{topic}" from 0 (unrelated, '
        "navigation, legal) to 100 (directly about the topic). Return ONLY JSON: "
        '{"results":[{"url":"<as given>","score":0}]}\n'
        f"url_prefix (omitted from urls): {prefix}\nLINKS:\n" + json.dumps(cands)
    )


async def label():
    topic = _template()[0]["target_topic"]
    labels = json.loads(LABELS.read_text()) if LABELS.exists() else {}
    handler = LlmHandler(KeyManager())
    for url in PAGES:
        links, _ = load_page(url)
        if not links:
            print(f"skip {url} (unreachable)")
            continue
        todo = [link for link in links if link.url not in labels]
        for i in range(0, len(todo), BATCH):
            batch = todo[i : i + BATCH]
            prefix = ScoringService.common_url_prefix(batch)
            ctx = ScoringContext(*LABEL_MODEL, _label_prompt(topic, prefix, batch))
            res = ScoringService._restore_urls(await handler.send(ctx), prefix)
            for link in batch:
                entry = res.get(link.url)
                if entry is not None:
                    labels[link.url] = int(entry.get("score", 0))
            LABELS.write_text(json.dumps(labels, indent=1))
            print(f"{url.rsplit('/', 1)[1]}: labelled {len(labels)} so far", flush=True)
            await asyncio.sleep(25)  # Groq free tier: 8000 tokens/minute
    await handler.client.close()


async def feature_rows(store_dir: str = ".space_store"):
    """Score every eval-page link with the current NLP code; returns rows of
    {url, score, <signal>: value, ...} (first page wins for repeated URLs)."""
    tmpl, _ = _template()
    svc = NLPService(
        tmpl["blueprint_id"], tmpl["target_topic"], LlmHandler(KeyManager()),
        tmpl["expansion"], store_base_dir=store_dir,
    )
    await svc.start()
    rows, seen = [], set()
    for url in PAGES:
        links, parent = load_page(url)
        if not links:
            continue
        scored = await svc.score_links(links, parent)
        for link in scored:
            if link.url not in seen:
                seen.add(link.url)
                rows.append({"url": link.url, "score": link._nlp_score, **link.nlp_vector})
    return rows


def auc(y, x) -> float:
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, x))


async def report(store_dir: str = ".space_store"):
    from sklearn.linear_model import LogisticRegression

    labels = json.loads(LABELS.read_text())
    rows = [r for r in await feature_rows(store_dir) if r["url"] in labels]
    y = np.array([labels[r["url"]] >= LABEL_THRESHOLD for r in rows])
    print(f"{len(rows)} labelled links, {int(y.sum())} relevant ({100 * y.mean():.0f}%)\n")
    keys = [k for k in rows[0] if k != "url"]
    X = np.array([[r[k] for k in keys] for r in rows])
    print(f"{'signal':26}{'AUC':>7}")
    for j, k in enumerate(keys):
        a = auc(y, X[:, j]) if X[:, j].std() > 0 else float("nan")
        print(f"{k:26}{a:7.3f}")
    # parent_relevance is constant per page, so its AUC/weight would only
    # measure which pages were sampled, not link quality: exclude from the fit.
    skip = {"score", "parent_relevance"}
    feats = [k for k in keys if k not in skip and X[:, keys.index(k)].std() > 0]
    Xf = np.array([[r[k] for k in feats] for r in rows])
    Z = (Xf - Xf.mean(0)) / Xf.std(0)
    clf = LogisticRegression(C=1.0, class_weight="balanced").fit(Z, y)
    print("\nlogistic weights (standardised features):")
    for k, w in sorted(zip(feats, clf.coef_[0]), key=lambda t: -abs(t[1])):
        print(f"  {k:26}{w:+.3f}")
    print(f"in-sample AUC {auc(y, clf.decision_function(Z)):.3f}")
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    cv = StratifiedKFold(5, shuffle=True, random_state=0)
    pred = cross_val_predict(clf, Z, y, cv=cv, method="decision_function")
    print(f"5-fold CV AUC {auc(y, pred):.3f}  (current composite: {auc(y, X[:, keys.index('score')]):.3f})")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    asyncio.run({"label": label, "report": report}[cmd]())
