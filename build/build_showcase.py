#!/usr/bin/env python3
"""build_showcase.py — generate the whole gallery from manifests.

Reads every manifests/<slug>.json, validates it against the contract
(build/MANIFEST-CONTRACT.md), and emits:

  index.html            the landing (hero + filter + legend + sections of uniform cards)
  detail/<slug>.html    one detail page per item (generic template) — UNLESS the manifest
                        sets custom_detail, in which case that pre-built page is copied verbatim
  showcase.css          copied from build/showcase.css to the repo root

It NEVER touches item application directories (e.g. /big-five-matchmaker/, /foundry/). Detail
pages live under detail/ precisely so they never collide with an app served at /<slug>/.

Stdlib only. Deterministic: same manifests in => byte-identical HTML out (manifests are sorted
by (category order, -substance_rank, slug); no timestamps in the output).

Usage:  python build/build_showcase.py [--repo <dir>]   (default: the repo this file lives in)
"""
from __future__ import annotations

import html
import json
import shutil
import sys
from pathlib import Path

CATEGORY_ORDER = ["flagship", "backend", "standalone", "prototype"]
CATEGORY_META = {
    "flagship":  ("Flagship", "the core research engine"),
    "backend":   ("Data-intensive apps", "powerful — but a server must be switched on first"),
    "standalone":("Standalone apps", "open and go, nothing to start"),
    "prototype": ("Concept prototypes", "single-page visual sketches from the engine"),
}
BADGE_KINDS = {"ok", "backend", "ext", "flag", "art", "soon"}


def esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def esc_text(s: str) -> str:
    return html.escape(str(s), quote=False)


# ---------------------------------------------------------------------------------------
# LOAD + VALIDATE
# ---------------------------------------------------------------------------------------
def load_manifests(repo: Path) -> list[dict]:
    mdir = repo / "manifests"
    items: list[dict] = []
    errors: list[str] = []
    for f in sorted(mdir.glob("*.json")):
        if f.name.startswith("_"):
            continue
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{f.name}: invalid JSON — {exc}")
            continue
        errs = validate(m, f.name)
        errors.extend(errs)
        if not errs:
            items.append(m)

    flags = [m for m in items if m.get("category") == "flagship"]
    if len(flags) > 1:
        errors.append(f"more than one flagship: {[m['slug'] for m in flags]}")

    if errors:
        print("MANIFEST VALIDATION FAILED:", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        raise SystemExit(1)
    return items


def validate(m: dict, name: str) -> list[str]:
    e: list[str] = []
    req = ["slug", "title", "tagline", "category", "links", "substance_rank", "standalone"]
    for k in req:
        if k not in m:
            e.append(f"{name}: missing required field '{k}'")
    if "tagline" in m and len(m["tagline"]) > 140:
        e.append(f"{name}: tagline is {len(m['tagline'])} chars (max 140) — move the essay to detail_body")
    if "category" in m and m["category"] not in (set(CATEGORY_ORDER) | {"ops"}):
        e.append(f"{name}: category '{m['category']}' not one of {CATEGORY_ORDER + ['ops']}")
    if "standalone" in m and not isinstance(m["standalone"], bool):
        e.append(f"{name}: standalone must be a boolean")
    if "links" in m and "open" not in m.get("links", {}):
        e.append(f"{name}: links.open is required")
    if "custom_detail" in m and "detail_body" in m:
        e.append(f"{name}: custom_detail and detail_body are mutually exclusive")
    for b in m.get("badges", []):
        if b.get("kind") not in BADGE_KINDS:
            e.append(f"{name}: badge kind '{b.get('kind')}' invalid")
    return e


def sort_key(m: dict):
    cat = m.get("category", "standalone")
    ci = CATEGORY_ORDER.index(cat) if cat in CATEGORY_ORDER else len(CATEGORY_ORDER)
    return (ci, -float(m.get("substance_rank", 0)), m.get("slug", ""))


# ---------------------------------------------------------------------------------------
# FRAGMENTS
# ---------------------------------------------------------------------------------------
def badges_html(m: dict) -> str:
    bs = m.get("badges", [])
    if not bs:
        return ""
    spans = "".join(
        f'<span class="badge {esc(b["kind"])}">{esc_text(b["label"])}</span>' for b in bs
    )
    return f'<div class="badges">{spans}</div>'


def thumb_html(m: dict, base: str = "") -> str:
    t = m.get("thumbnail")
    if t:
        return f'<img class="thumb" src="{base}{esc(t)}" alt="{esc(m["title"])} — screenshot" loading="lazy">'
    # honest placeholder: no fabricated image, just the title on paper
    return f'<div class="thumb placeholder">{esc_text(m["title"])}</div>'


def card_html(m: dict, hero: bool = False) -> str:
    slug = m["slug"]
    detail = f"detail/{slug}.html"
    cls = "card hero" if hero else "card"
    standalone = "true" if m.get("standalone") else "false"
    return f"""
      <a class="{cls}" href="{esc(detail)}" data-standalone="{standalone}">
        {thumb_html(m)}
        <div class="cbody">
          <div class="ctitle">{esc_text(m["title"])}</div>
          <p class="chook">{esc_text(m["tagline"])}</p>
          <div class="cfoot">
            {badges_html(m)}
            <span class="more">details &rarr;</span>
          </div>
        </div>
      </a>"""


def ops_strip_html(ops_items: list[dict]) -> str:
    if not ops_items:
        return ""
    rows = ""
    for m in ops_items:
        rows += f"""
        <a class="card" href="detail/{esc(m['slug'])}.html" data-standalone="false">
          {thumb_html(m)}
          <div class="cbody">
            <div class="ctitle">{esc_text(m['title'])}</div>
            <p class="chook">{esc_text(m['tagline'])}</p>
            <div class="cfoot">{badges_html(m)}<span class="more">details &rarr;</span></div>
          </div>
        </a>"""
    return f"""
    <section class="section" data-cat="ops">
      <h2>Operations <span class="n">&mdash; live infrastructure</span></h2>
      <div class="grid">{rows}
      </div>
    </section>"""


# ---------------------------------------------------------------------------------------
# INDEX
# ---------------------------------------------------------------------------------------
def render_index(items: list[dict]) -> str:
    items = sorted(items, key=sort_key)
    ops = [m for m in items if m.get("category") == "ops"]
    sections = ""
    for cat in CATEGORY_ORDER:
        group = [m for m in items if m.get("category") == cat]
        if not group:
            continue
        title, sub = CATEGORY_META[cat]
        cards = ""
        for m in group:
            cards += card_html(m, hero=(cat == "flagship"))
        sections += f"""
    <section class="section" data-cat="{cat}">
      <h2>{esc_text(title)} <span class="n">&mdash; {esc_text(sub)}</span></h2>
      <div class="grid">{cards}
      </div>
    </section>"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Yuyu Cloud &middot; Showcase</title>
<link rel="stylesheet" href="showcase.css">
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <p class="kicker">yuyu-cloud &middot; a linguistics &amp; interpretive-risk research engine</p>
    <h1>Showcase</h1>
    <p class="lede">A working gallery of the apps and prototypes built on the yuyu system &mdash;
      the research engine and the visual tools around it. <strong>Each card is one glance:</strong>
      a picture, a title, a one-line hook. Tap any card for the full detail page. The flagship sits
      up top; everything is ordered by how substantial it is.</p>
    <p class="metaline">Served from <code>yuyu-cloud-box</code> &middot; Cloudflare Tunnel
      (Access-gated) + Tailscale mirror. <strong>Read the badge before a demo:</strong> a
      <span style="color:var(--ok-ink);font-weight:700">green</span> tile runs on its own in any
      browser; an <span style="color:var(--back-ink);font-weight:700">amber</span> tile needs a
      backend server switched on first, or its screen stays blank.</p>
    <div class="controls">
      <div class="filter" role="group" aria-label="Filter by how it runs">
        <button data-filter="all" aria-pressed="true">All</button>
        <button data-filter="standalone" aria-pressed="false">Runs in your browser</button>
        <button data-filter="backend" aria-pressed="false">Needs a backend</button>
      </div>
      <div class="legend">
        <span><i class="dot ok"></i> Runs standalone</span>
        <span><i class="dot backend"></i> Backend required</span>
        <span><i class="dot ext"></i> Runs on ps14 &middot; tunnel</span>
      </div>
    </div>
  </header>
{ops_strip_html(ops)}{sections}

  <p class="foot">Ordered by substance: flagship first, then power-apps that need a server, then
    everything that just runs. Badges are honest &mdash; an amber tile whose backend is off will
    render blank. This page is <strong>generated</strong> from
    <code>manifests/*.json</code> by <code>build/build_showcase.py</code>; it is not hand-edited.</p>
</div>
<script>
(function(){{
  var btns=[].slice.call(document.querySelectorAll('.filter button'));
  var cards=[].slice.call(document.querySelectorAll('.card'));
  var secs=[].slice.call(document.querySelectorAll('.section'));
  function apply(f){{
    cards.forEach(function(c){{
      var s=c.getAttribute('data-standalone')==='true';
      var show = f==='all' || (f==='standalone'&&s) || (f==='backend'&&!s);
      c.hidden=!show;
    }});
    secs.forEach(function(sec){{
      var vis=[].slice.call(sec.querySelectorAll('.card')).some(function(c){{return !c.hidden;}});
      sec.hidden=!vis;
    }});
    btns.forEach(function(b){{b.setAttribute('aria-pressed', b.getAttribute('data-filter')===f);}});
  }}
  btns.forEach(function(b){{b.addEventListener('click',function(){{apply(b.getAttribute('data-filter'));}});}});
}})();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------------------
# DETAIL (generic template)
# ---------------------------------------------------------------------------------------
def carousel_html(shots: list[str], base: str) -> str:
    if not shots:
        return ""
    imgs = "".join(
        f'<img src="{base}{esc(s)}" alt="screenshot {i+1}" loading="lazy">'
        for i, s in enumerate(shots)
    )
    dots = "".join(
        f'<button data-i="{i}" aria-current="{"true" if i==0 else "false"}" '
        f'aria-label="slide {i+1}"></button>'
        for i in range(len(shots))
    )
    nav = ""
    if len(shots) > 1:
        nav = ('<button class="cbtn prev" aria-label="previous">&#8249;</button>'
               '<button class="cbtn next" aria-label="next">&#8250;</button>')
    return f"""
    <div class="carousel">
      <div class="frame">
        <div class="slides">{imgs}</div>
        {nav}
      </div>
      <div class="dots">{dots}</div>
    </div>"""


def funcs_html(funcs: list[dict]) -> str:
    if not funcs:
        return ""
    cards = "".join(
        f'<div class="func"><h3>{esc_text(f["name"])}</h3><p>{esc_text(f["blurb"])}</p></div>'
        for f in funcs
    )
    return f"""
    <section>
      <p class="eyebrow">What it does</p>
      <div class="funcs">{cards}</div>
    </section>"""


def render_detail(m: dict) -> str:
    slug = m["slug"]
    base = "../"  # detail pages sit one level down
    open_link = m["links"]["open"]
    # open link is repo-root relative in the manifest ("./big-five-matchmaker/"); from detail/ prefix ../
    if open_link.startswith("./"):
        open_link = base + open_link[2:]
    how = m["links"].get("how_it_works")
    actions = f'<a class="btn" href="{esc(open_link)}">&#9654; Open it</a>'
    if how:
        actions += f'<a class="btn ghost" href="{esc(how)}">How it works &rarr;</a>'

    shots = m.get("screenshots", [])
    carousel = carousel_html(shots, base) if shots else ""

    body = ""
    for para in m.get("detail_body", []):
        body += f"      <p>{para}</p>\n"
    body_section = f'<section class="detail-body">\n{body}    </section>' if body else ""

    ops = ""
    if m.get("ops_note"):
        ops = f'<div class="ops-note"><b>&#9656; ops</b> &middot; {esc_text(m["ops_note"])}</div>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(m["title"])} &middot; Yuyu Showcase</title>
<link rel="stylesheet" href="{base}showcase.css">
</head>
<body>
<div class="wrap">
  <a class="backlink" href="{base}index.html">&#8592; all projects</a>
  <header class="detail-hero">
    {badges_html(m)}
    <h1>{esc_text(m["title"])}</h1>
    <p class="tagline">{esc_text(m["tagline"])}</p>
    <div class="actions">{actions}</div>
  </header>
{carousel}
{funcs_html(m.get("functionality", []))}
  {ops}
{body_section}
</div>
{_CAROUSEL_JS if shots else ""}
</body>
</html>"""


_CAROUSEL_JS = """<script>
(function(){
  document.querySelectorAll('.carousel').forEach(function(car){
    var slides=car.querySelector('.slides');
    var imgs=[].slice.call(slides.querySelectorAll('img'));
    var dots=[].slice.call(car.querySelectorAll('.dots button'));
    var i=0;
    function go(n){ i=Math.max(0,Math.min(imgs.length-1,n));
      slides.scrollTo({left:imgs[i].offsetLeft,behavior:'smooth'});
      dots.forEach(function(d,k){d.setAttribute('aria-current',k===i);}); }
    dots.forEach(function(d,k){d.addEventListener('click',function(){go(k);});});
    var p=car.querySelector('.prev'), nx=car.querySelector('.next');
    if(p)p.addEventListener('click',function(){go(i-1);});
    if(nx)nx.addEventListener('click',function(){go(i+1);});
    var t;
    slides.addEventListener('scroll',function(){ clearTimeout(t); t=setTimeout(function(){
      var best=0,bd=1e9; imgs.forEach(function(im,k){var d=Math.abs(im.offsetLeft-slides.scrollLeft);
        if(d<bd){bd=d;best=k;}}); i=best;
      dots.forEach(function(d,k){d.setAttribute('aria-current',k===i);}); },90); });
  });
})();
</script>"""


# ---------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------
def main(argv: list[str]) -> int:
    repo = Path(__file__).resolve().parent.parent
    if "--repo" in argv:
        repo = Path(argv[argv.index("--repo") + 1]).resolve()

    items = load_manifests(repo)

    # index
    (repo / "index.html").write_text(render_index(items), encoding="utf-8")

    # css to repo root
    shutil.copyfile(repo / "build" / "showcase.css", repo / "showcase.css")

    # detail pages
    detail_dir = repo / "detail"
    detail_dir.mkdir(exist_ok=True)
    n_custom = 0
    for m in items:
        if m.get("category") == "ops" and not m.get("custom_detail") and not m.get("detail_body"):
            # ops items still get a minimal detail page from the generic template
            pass
        out = detail_dir / f"{m['slug']}.html"
        if m.get("custom_detail"):
            src = repo / m["custom_detail"]
            if not src.exists():
                print(f"ERROR: custom_detail not found: {src}", file=sys.stderr)
                return 1
            shutil.copyfile(src, out)
            n_custom += 1
        else:
            out.write_text(render_detail(m), encoding="utf-8")

    print(f"built {len(items)} items -> index.html + detail/ "
          f"({n_custom} custom detail page(s) copied). css synced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
