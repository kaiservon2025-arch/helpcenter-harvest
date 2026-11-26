# -*- coding: utf-8 -*-
"""harvest.py - recon the site, then pull the whole tree through its JSON API.

Usage
  python harvest.py --discover            # find the API from the SPA bundle
  python harvest.py --check               # one small request per endpoint, print field names
  python harvest.py                       # full crawl -> data/tree.json
  python harvest.py --only-categories 2   # smoke test on the first N categories

Everything site-specific lives in harvest.config.json; see the skill's SKILL.md
for the schema and references/noon-case.md for a worked example.
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

import hc

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
CTX = ssl.create_default_context()
C = hc.Cfg()


def _headers():
    h = {"User-Agent": UA, "Accept": "application/json,text/plain,*/*",
         "Accept-Encoding": "identity"}
    h.update({k: hc.fill(v, base=C.base, locale=C.locale, site=C.site)
              for k, v in (C.cfg.get("headers") or {}).items()})
    return h


def get(url, timeout=60):
    req = urllib.request.Request(url, headers=dict(_headers(), **{"Accept": "text/html,*/*"}))
    return urllib.request.urlopen(req, timeout=timeout, context=CTX).read()


def post(path, body, tries=3):
    url = C.base + path
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                         headers=dict(_headers(), **{"Content-Type": "application/json"}))
            return json.loads(urllib.request.urlopen(req, timeout=60, context=CTX).read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 - network flakiness is expected
            last = e
            time.sleep(1.5 * (i + 1))
    hc.die("POST %s failed: %s: %s" % (url, type(last).__name__, last))


def pick(data, key):
    cur = data
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def call(ep, **kw):
    path = hc.fill(ep["path"], **kw)
    body = hc.fill(ep.get("body") or {}, **kw)
    return post(path, body)


def paged(ep, **kw):
    """Fetch one endpoint, following the server's real page size."""
    pg = C.paging()
    max_pages = int(pg.get("max_pages") or 200)
    sleep = float(pg.get("sleep") or 0.2)
    items, page, expect = [], 1, None
    idfield = next((k for k in (ep.get("map") or {}) if k.startswith("id_")), None)
    seen = set()
    while page <= max_pages:
        kw2 = dict(kw, page=page)
        data = call(ep, **kw2)
        batch = pick(data, ep.get("key") or "data") or []
        if not batch:
            break
        if expect is None:
            expect = len(batch)
            print("    page size reported: %d (requested %s)" % (expect, (ep.get("body") or {}).get("per_page")), flush=True)
        if idfield:
            fresh = [x for x in batch if str(x.get(idfield)) not in seen]
            seen.update(str(x.get(idfield)) for x in fresh)
            if not fresh:
                print("    repeated page detected at page %d - server is clamping, stop" % page, flush=True)
                break
            items.extend(fresh)
        else:
            items.extend(batch)
        if len(batch) < expect:
            break
        page += 1
        time.sleep(sleep)
    else:
        print("  WARNING: hit pagination.max_pages=%d for %s - results may be truncated; "
              "raise it in harvest.config.json" % (max_pages, ep.get("path")), flush=True)
    return items


def norm(batch, mapping):
    out = []
    for src in batch:
        rec = {}
        for canon, field in mapping.items():
            rec[canon] = src.get(field)
        out.append(rec)
    return out


def fetch_all(only_categories=None):
    eps = C.cfg.get("endpoints") or {}
    for name in ("groups", "categories", "stages", "articles"):
        if name not in eps:
            hc.die("harvest.config.json is missing endpoints.%s" % name)

    print("[1/4] groups", flush=True)
    g_ep = eps["groups"]
    groups = norm(paged(g_ep) if g_ep.get("paginated") else (pick(call(g_ep), g_ep.get("key") or "data") or []),
                  g_ep["map"])
    print("    -> %d" % len(groups), flush=True)

    print("[2/4] categories", flush=True)
    c_ep = eps["categories"]
    cats = norm(paged(c_ep) if c_ep.get("paginated") else (pick(call(c_ep), c_ep.get("key") or "data") or []),
                c_ep["map"])
    cats.sort(key=lambda c: (c.get("sort_order") if c.get("sort_order") is not None else 99, str(c.get("name"))))
    print("    -> %d" % len(cats), flush=True)

    print("[3/4] stages", flush=True)
    s_ep = eps["stages"]
    scat = cats[:only_categories] if only_categories else cats
    if "{category_id}" in json.dumps(s_ep.get("body") or {}):
        stages, sseen = [], set()
        for c in scat:
            batch = paged(s_ep, category_id=c["id_category"], category_slug=c.get("slug"))
            for s in norm(batch, s_ep["map"]):
                sid = str(s.get("id_journey_stage"))
                if not sid or sid in sseen:
                    continue
                sseen.add(sid)
                if not s.get("id_category"):
                    s["id_category"] = c["id_category"]
                stages.append(s)
    else:
        stages = norm(paged(s_ep) if s_ep.get("paginated") else (pick(call(s_ep), s_ep.get("key") or "data") or []),
                      s_ep["map"])
    print("    -> %d" % len(stages), flush=True)

    print("[4/4] articles", flush=True)
    a_ep = eps["articles"]
    cat_map = {str(c["id_category"]): c for c in cats}
    articles, seen = [], set()
    todo = cats[:only_categories] if only_categories else cats
    for i, c in enumerate(todo, 1):
        batch = paged(a_ep, category_id=c["id_category"], category_slug=c.get("slug"))
        rows = norm(batch, a_ep["map"])
        kept = 0
        for r in rows:
            slug = r.get("slug") or ""
            key = (c.get("slug"), slug)
            if not slug or key in seen:
                continue
            seen.add(key)
            r["_category_slug"] = c.get("slug")
            r["_category_name"] = c.get("name")
            r["_category_id"] = c["id_category"]
            r["_category_group"] = c.get("id_category_group") or (cat_map.get(str(c["id_category"])) or {}).get("id_category_group")
            articles.append(r)
            kept += 1
        print("    [%d/%d] %s: %d" % (i, len(todo), c.get("slug"), kept), flush=True)

    if not articles:
        hc.die("no articles returned - check endpoints.articles.body (id_category placeholder) and map.content")

    empty = sum(1 for a in articles if not (a.get("content") or "").strip())
    if empty == len(articles):
        hc.die("every article has empty content - map.content points at the wrong field; "
               "run --check and look at the raw JSON keys")

    tree = {
        "meta": {
            "site": C.site, "base": C.base, "locale": C.locale,
            "source_url": C.start_url,
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "groups": len(groups), "categories": len(cats), "stages": len(stages),
            "articles": len(articles),
            "content_chars": sum(len(a.get("content") or "") for a in articles),
        },
        "groups": groups,
        "categories": cats,
        "stages": stages,
        "articles": articles,
    }
    path = os.path.join(C.data, "tree.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False, indent=1)
    print("saved %s" % path)
    print("articles=%d chars=%d empty_content=%d" % (len(articles), tree["meta"]["content_chars"], empty))


# ------------------------------------------------------------------ recon
def discover():
    print("start url:", C.start_url)
    html = get(C.start_url).decode("utf-8", "replace")
    print("html bytes:", len(html))
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
    print("script bundles:", len(scripts))
    cand = set()
    for src in scripts[:20]:
        url = src if src.startswith("http") else C.base + "/" + src.lstrip("/")
        try:
            js = get(url, timeout=45).decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            print("  js fail", url, type(e).__name__)
            continue
        for s in re.findall(r'["\'`]((?:https?://)?/[^"\'`\s]{3,120})["\'`]', js):
            if re.search(r"api|json|content|nav|categor|article|project|hc", s, re.I):
                cand.add(s)
    for s in sorted(cand):
        print("  ", s)
    try:
        sm = get(C.base + "/sitemap.xml", timeout=45).decode("utf-8", "replace")
        locs = re.findall(r"<loc>(.*?)</loc>", sm)
        print("sitemap urls:", len(locs))
        pats = {}
        for u in locs:
            p = re.sub(r"/[^/]+$", "/*", urllib.parse.urlparse(u).path)
            pats[p] = pats.get(p, 0) + 1
        for p, n in sorted(pats.items(), key=lambda kv: -kv[1])[:8]:
            print("   %-45s %d" % (p, n))
    except Exception as e:  # noqa: BLE001
        print("sitemap unavailable:", type(e).__name__, e)


def check():
    eps = C.cfg.get("endpoints") or {}
    for name in ("groups", "categories", "stages"):
        if name not in eps:
            continue
        ep = eps[name]
        data = call(ep)
        batch = pick(data, ep.get("key") or "data") or []
        print("%-10s items=%-4d keys=%s" % (name, len(batch), sorted(batch[0].keys()) if batch else "-"))
    ep = eps.get("articles")
    if not ep:
        return
    cats = norm(pick(call(eps["categories"]), (eps["categories"].get("key") or "data")) or [],
                eps["categories"]["map"])
    if not cats:
        hc.die("no categories from /categories endpoint")
    c = cats[0]
    data = call(ep, category_id=c["id_category"], category_slug=c.get("slug"), page=1)
    batch = pick(data, ep.get("key") or "data") or []
    print("articles   cat=%s items=%d" % (c.get("slug"), len(batch)))
    if batch:
        first = batch[0]
        print("           article keys:", sorted(first.keys()))
        print("           has content:", bool((first.get("content") or "").strip()),
              "len:", len(first.get("content") or ""))
        print("           title:", str(first.get("title"))[:80])


def main():
    args = C.rest
    if "--discover" in args:
        return discover()
    if "--check" in args:
        return check()
    only = None
    if "--only-categories" in args:
        i = args.index("--only-categories")
        only = int(args[i + 1]) if i + 1 < len(args) else 1
    fetch_all(only)


if __name__ == "__main__":
    main()
