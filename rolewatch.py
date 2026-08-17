#!/usr/bin/env python3
"""
rolewatch.py

Scans European job boards for brand / copy / comms roles, filters them
against your rules, scores each one against your CV, and writes
docs/roles.json which the website reads.

Stdlib only. No install, no API keys.

Run:
    python3 rolewatch.py

Edit COMPANIES to change which boards get checked.
Edit the CAPITAL LETTER lists to change the filters.
Edit CV_TEXT to change what the scoring compares against.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "roles.json")

# ---------------------------------------------------------------- companies

# To find a slug, open a careers page and read the URL:
#   boards.greenhouse.io/SLUG     jobs.lever.co/SLUG
#   jobs.ashbyhq.com/SLUG         apply.workable.com/SLUG
#   jobs.smartrecruiters.com/SLUG SLUG.recruitee.com
# Wrong slugs fail silently and are skipped.
COMPANIES = [
    "spotify", "klarna", "adyen", "glovo", "wise", "revolut", "monzo",
    "n26", "traderepublic", "miro", "pleo", "typeform", "factorialhr",
    "travelperk", "wolt", "supercell", "vinted", "zalando", "hellofresh",
    "flixbus", "getyourguide", "sennder", "forto", "choco", "personio",
    "doctolib", "alan", "qonto", "payfit", "backmarket", "voiscooters",
    "tink", "northvolt", "bolt", "remote", "deel", "contentful",
    "sinch", "truecaller", "einride", "epidemicsound", "kahoot",
    "mollie", "messagebird", "bird", "framer", "tide", "gocardless",
    "starlingbank", "octopusenergy", "hostaway", "onfido", "canva",
]

# ---------------------------------------------------------------- filters

INCLUDE_TITLE = [
    "copywriter", "copy writer", "copy lead", "brand", "communication",
    "comms", "content", "creative", "editorial", "editor", "verbal",
    "tone of voice", "storytell", "narrative", "writer", "messaging",
    "positioning", "strategist", "strategy", "guardian", "voice",
]

EXCLUDE_TITLE = [
    "intern", "internship", "junior", "graduate", "trainee",
    "working student", "apprentice", "entry level", "assistant",
    "sales", "account executive", "business development", "partnerships",
    "recruit", "talent", "engineer", "developer", "designer",
    "data ", "analytics", "seo specialist", "paid social",
    "performance marketing", "media buyer", "growth hacker",
    "affiliate", "crm specialist", "lifecycle marketing",
    "media strategist", "media planner", "media strategy", "programmatic",
    "trading", "product strategy", "pricing strategy", "product content",
    "technical writer", "ux writer", "content moderator", "content operations",
]

# Languages you don't work in. Any of these in a job TITLE is an instant drop.
LANGS = [
    "german", "deutsch", "swedish", "svenska", "dutch", "nederlands",
    "french", "français", "francais", "spanish", "español", "espanol",
    "castellano", "catalan", "català", "italian", "italiano",
    "portuguese", "português", "polish", "polski", "danish", "dansk",
    "norwegian", "norsk", "finnish", "suomi", "lithuanian", "estonian",
    "czech", "greek", "romanian", "hungarian", "turkish", "arabic",
]

# Words that turn a language mention in the body into a requirement.
LANG_DEMAND = (r"speaker|speaking|native|fluen\w*|proficien\w*|bilingual|"
               r"mother\s*tongue|required|mandatory|essential|must|"
               r"\bc1\b|\bc2\b|\bb2\b")

_L = "|".join(LANGS)
# If the sentence softens it, the language isn't a wall.
LANG_SOFTENER = re.compile(
    r"not required|not a requirement|no need|nice to have|a plus|"
    r"is a bonus|an advantage|desirable|optional|not essential|"
    r"beneficial|welcome|appreciated|not mandatory", re.I)

LANG_AFTER = re.compile(r"\b(?:" + _L + r")\b[^.\n]{0,25}\b(?:" + LANG_DEMAND + r")\b", re.I)
LANG_BEFORE = re.compile(r"\b(?:" + LANG_DEMAND + r")\b[^.\n]{0,25}\b(?:" + _L + r")\b", re.I)

EXCLUDE_BODY = ["tobacco", "cigarette", "vaping", "nicotine pouches"]

# Ads that rule you out. These are dropped outright.
NO_SPONSOR = [
    "no visa sponsorship", "no sponsorship available", "not offer sponsorship",
    "not offer visa sponsorship", "does not offer visa", "do not offer visa",
    "unable to sponsor", "unable to provide sponsorship",
    "unable to provide visa", "cannot sponsor", "can not sponsor",
    "do not sponsor", "does not sponsor", "will not sponsor",
    "not sponsoring", "without sponsorship",
    "without the need for sponsorship", "not require sponsorship",
    "must already have the right to work", "must have the right to work",
    "must hold a valid work permit", "must hold a valid eu",
    "existing right to work", "already authorised to work",
    "already authorized to work", "local candidates only",
    "no relocation", "relocation is not", "we do not offer relocation",
]

# Ads that say the opposite. These get a badge and a small lift.
YES_SPONSOR = [
    "visa sponsorship", "sponsorship available", "we sponsor",
    "we offer sponsorship", "visa support", "work permit support",
    "immigration support", "relocation package", "relocation support",
    "relocation assistance", "relocation bonus", "help you relocate",
    "support with relocation", "we will relocate",
]

PLACES = [
    "sweden", "stockholm", "malmo", "malmö", "gothenburg", "göteborg",
    "denmark", "copenhagen", "norway", "oslo", "finland", "helsinki",
    "netherlands", "amsterdam", "rotterdam", "utrecht", "eindhoven",
    "belgium", "brussels", "bruxelles", "antwerp", "ghent",
    "germany", "berlin", "munich", "münchen", "hamburg", "cologne",
    "frankfurt", "düsseldorf", "dusseldorf", "stuttgart",
    "spain", "barcelona", "madrid", "valencia", "malaga", "seville",
    "portugal", "lisbon", "lisboa", "porto",
    "ireland", "dublin", "france", "paris", "italy", "milan", "rome",
    "austria", "vienna", "switzerland", "zurich", "zürich", "geneva",
    "poland", "warsaw", "krakow", "estonia", "tallinn",
    "czech", "prague", "united kingdom", "london", "manchester",
    "europe", "emea", "remote", "anywhere", "hybrid",
    # APAC and Gulf
    "malaysia", "kuala lumpur", "petaling jaya", "penang", "cyberjaya",
    "singapore",
    "united arab emirates", "uae", "dubai", "abu dhabi", "sharjah",
    "qatar", "doha", "saudi", "riyadh", "jeddah", "bahrain", "manama",
    "kuwait", "oman", "muscat",
    "apac", "mena", "gulf", "middle east", "southeast asia", "sea region",
]

MIN_SENIORITY = [
    "senior", "lead", "head of", "principal", "director", "global",
    "manager", "chief", "staff", "strategist", "guardian", "owner",
    "editor-in-chief", "editor in chief", "specialist ii", "sr.", "sr ",
    "associate creative", "group ", "deputy", "executive",
]
REQUIRE_SENIORITY = True

# ---------------------------------------------------------------- scoring

# What you actually want the job to be about. Weight 1 to 5.
# These outrank anything picked up automatically from the CV.
SIGNAL_TERMS = {
    "brand strategy": 5, "brand positioning": 5, "positioning": 4,
    "tone of voice": 5, "verbal identity": 5, "brand voice": 4,
    "brand guidelines": 3, "brand platform": 4, "brand world": 3,
    "copywriting": 4, "copywriter": 4, "long-form": 2, "editorial": 3,
    "creative direction": 4, "creative strategy": 4, "concept": 3,
    "campaign": 3, "integrated campaign": 4, "brand campaign": 4,
    "storytelling": 3, "narrative": 3, "messaging framework": 4,
    "localisation": 4, "localization": 4, "transcreation": 4,
    "global brand": 4, "multi-market": 4, "international markets": 3,
    "brand book": 3, "rebrand": 4, "brand architecture": 3,
    "film": 2, "script": 3, "art direction": 2, "production": 2,
    "agency": 2, "in-house": 2, "stakeholder": 2, "cross-functional": 1,
    "ai": 2, "generative ai": 3, "prompt": 3,
    "b2b": 2, "fintech": 2, "retail": 2, "fmcg": 2, "e-commerce": 1,
    "internal communications": 2, "press release": 2, "pr": 1,
    "team": 2, "mentor": 2, "own the brand": 4, "brand guardian": 4,
}

# Things that pull a role down even when it passes the hard filters.
PENALTY_TERMS = {
    "meta ads manager": 4, "attribution": 3, "mmm": 3,
    "roas": 3, "media buying": 4, "conversion rate optimisation": 2,
    "cold outreach": 3, "quota": 4, "pipeline generation": 3,
    "hubspot admin": 2, "marketo": 2, "salesforce admin": 2,
    "seo audit": 2, "backlink": 3, "keyword research": 2,
}

YEARS_MIN, YEARS_MAX = 4, 14  # your 11 years sits comfortably inside


CV_TEXT = """
Hamza Ahmad. Senior brand copywriter and creative strategist. Eleven years,
seven in agency and four in-house. Indian national.

Global Brand Copywriter at IKEA, Malmo. Led creative work across 31 markets.
Brand positioning, tone of voice, verbal identity, localisation and
transcreation across a global brand system. Built an internal AI tone of
voice writing assistant. Internal communications reaching 150,000 co-workers.
Directed brand films end to end, from concept and script through production
and post. Directed photoshoots and video shoots. Platform strategy for
Reddit, Instagram and TikTok. Brand partnership work with UNHCR. Events for
Unilever brands.

Razor Group, Berlin. E-commerce brand copywriting and positioning.
Agency: Leo Burnett, Saatchi and Saatchi, Mullen Lowe Lintas. Freelance
associate creative director covering Publicis, Saatchi and McCann.

Brands: Google, P&G, Unilever, DBS, MobiKwik, Tata Communications.
Sectors: technology, fintech, retail, FMCG, food and beverage, finance,
B2B enterprise, agriculture.
Markets: India, APAC, MENA, Europe. Localisation a core focus.
Biostadt rebranding led end to end, released across 18 markets in 18
translations.

Skills: brand strategy, brand positioning, brand platform, messaging
framework, campaign concept, integrated campaign, creative direction,
copywriting, editorial, long-form, script, storytelling, narrative, press
release, public relations, stakeholder management, mentoring, generative AI
and prompt engineering, Figma.

Runs CopyThat, a one-person creative studio.
"""


def load_cv_terms():
    """Low-weight match terms pulled from CV_TEXT above. Edit CV_TEXT freely."""
    text = CV_TEXT.lower()
    stop = set("""a an the and or but if then than that this those these of in on at to
        for with by from as is are was were be been being have has had do does did not
        no so such own same too very can will just also i me my we our you your they
        their it its he she his her who whom which what when where how why all any both
        each few more most other some only per over under again further once here there
        about into during before after above below up down out off""".split())
    freq = {}
    for w in re.findall(r"[a-zaaoeu]{4,}", text):
        if w not in stop:
            freq[w] = freq.get(w, 0) + 1
    terms = sorted(freq.items(), key=lambda x: -x[1])[:180]
    return {w: 1 for w, c in terms if c >= 2}


def parse_years(body):
    """Find the years of experience an ad asks for. None if unstated."""
    m = re.search(r"(\d{1,2})\s*\+?\s*(?:-|to|–)?\s*(\d{1,2})?\s*years?"
                  r"[^.]{0,40}experien", body)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (TypeError, ValueError):
        return None


def score(job, cv_terms):
    blob = (job["title"] + " " + job["body"]).lower()
    hits, raw = [], 0

    for term, w in SIGNAL_TERMS.items():
        if term in blob:
            raw += w
            hits.append(term)

    for term, w in PENALTY_TERMS.items():
        if term in blob:
            raw -= w
            hits.append("- " + term)

    cv_hit = sum(1 for t in cv_terms if t in blob)
    raw += min(cv_hit, 25) * 0.4

    yrs = parse_years(job["body"])
    if yrs is not None:
        if yrs > YEARS_MAX:
            raw -= 6
            hits.append(f"- asks {yrs}+ years")
        elif yrs < YEARS_MIN:
            raw -= 4
            hits.append(f"- asks only {yrs} years")
        else:
            raw += 3
            hits.append(f"{yrs}+ years")

    if sponsors(job["body"]) is True:
        raw += 5
        hits.insert(0, "sponsorship or relocation")

    pct = max(0, min(100, round(raw / 72 * 100)))
    return pct, hits[:12], yrs



# ---------------------------------------------------------------- drafting

# Cover letters are drafted only for roles at or above this score, newest
# first, and only a few per run so the bill stays small. Raise or lower
# freely. Set MAX_DRAFTS to 0 to switch drafting off.
MIN_SCORE_TO_DRAFT = 45
MAX_DRAFTS = 5
MODEL = "claude-sonnet-5"   # swap to "claude-haiku-4-5-20251001" for cheaper

BRIEF = """You are drafting a cover letter for Hamza Ahmad. Follow every rule.

WHO HE IS
Copywriter and creative with a strong focus on brand strategy. Eleven years,
seven in agency and four in-house. Indian national. Most recently Global Brand
Copywriter at IKEA in Malmo, leading creative work across 31 markets. He built
an internal AI tone of voice writing assistant there. He has directed brand
films end to end, from concept and script through production and post, and has
directed photoshoots and video shoots. Earlier: Razor Group in Berlin, and
agency years at Leo Burnett, Saatchi and Saatchi and Mullen Lowe Lintas, plus
freelance associate creative director work covering Publicis, Saatchi and
McCann. Brands include Google, P&G, Unilever, DBS and MobiKwik. Markets across
India, APAC, MENA and Europe, with localisation a core focus. He led the
Biostadt rebrand end to end, released across 18 markets in 18 translations. He
also runs CopyThat, a one-person creative studio.

HARD RULES
1. Never use an em dash. Not once. Use commas, full stops or semicolons.
2. Open with him: who he is and what he has built. Never open with a line
   lifted from the job ad, and never with a thesis statement about the
   industry or the category.
3. Do not include any paragraph about gaps, or where he would be new, or what
   he is still learning. None.
4. Call him a copywriter and creative with a strong focus on brand strategy.
   Never call him a creative leader or a brand strategist. Keep the framing
   humble.
5. State the role title he is applying for and his eleven years of experience
   explicitly, in plain sentences. Assume an AI screen reads this before a
   human does, so mirror the employer's own vocabulary wherever it is honest
   to do so.
6. One continuous argument in flowing prose. Not a list of separate claims.
   Argue why he fits: experience, the extra he brings, and self motivation.
   Do not lecture the reader or state general principles at them.
7. If the role is a stewardship or leadership seat rather than a making seat,
   the first paragraph must carry the advantage of having made the work
   himself, because direction from someone who has executed it is sharper.
   Frame that as a positive, never as a comparison to people without a
   creative background.
8. Around 250 to 320 words. No greeting line beyond a simple one, no address
   block, no signature block. Plain prose only.
9. Never invent an achievement, a metric or a client he does not have.

Return the letter text and nothing else. No preamble, no notes, no markdown."""


def de_dash(text):
    """Belt and braces. No em dashes ever reach the page."""
    text = text.replace(" \u2014 ", ", ").replace("\u2014", ", ")
    text = text.replace(" \u2013 ", ", ").replace("\u2013", "-")
    return re.sub(r",\s*,", ",", text)


def draft_letter(role):
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 1200,
        "system": BRIEF,
        "messages": [{"role": "user", "content":
                      f"Role: {role['title']}\nCompany: {role['company']}\n"
                      f"Location: {role['location']}\n\n"
                      f"The advert:\n{role.get('body', role.get('summary',''))[:6000]}"}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=payload,
        headers={"content-type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode())
        return de_dash("".join(b.get("text", "") for b in d.get("content", [])).strip())
    except Exception as e:
        print(f"  draft failed for {role['title']}: {e}")
        return None


def add_drafts(roles, bodies, existing):
    """Draft for the best roles that don't have a letter yet."""
    if not MAX_DRAFTS or not os.environ.get("ANTHROPIC_API_KEY"):
        if MAX_DRAFTS:
            print("No ANTHROPIC_API_KEY set, skipping cover letters.")
        return
    todo = [r for r in roles
            if r["score"] >= MIN_SCORE_TO_DRAFT
            and not (existing.get(r["id"], {}) or {}).get("letter")]
    todo = todo[:MAX_DRAFTS]
    for r in roles:
        prev = (existing.get(r["id"], {}) or {}).get("letter")
        if prev:
            r["letter"] = prev
    if not todo:
        print("No new roles need a letter.")
        return
    print(f"Drafting {len(todo)} cover letters...")
    for r in todo:
        r["body"] = bodies.get(r["id"], "")
        text = draft_letter(r)
        r.pop("body", None)
        if text:
            r["letter"] = text
            print(f"  drafted: {r['title']} at {r['company']}")
        time.sleep(1)


# ---------------------------------------------------------------- plumbing

UA = "Mozilla/5.0 (rolewatch/2.0)"
TIMEOUT = 12


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = urllib.parse.unquote(s)
    for a, b in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&nbsp;", " "), ("&#39;", "'"), ("&quot;", '"')]:
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def norm(company, title, location, url, body=""):
    return {
        "company": company,
        "title": strip_html(title or ""),
        "location": strip_html(location or ""),
        "url": url or "",
        "body": strip_html(body or "")[:8000],
    }


# ---------------------------------------------------------------- fetchers

def from_greenhouse(slug):
    d = get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    if not d or "jobs" not in d:
        return []
    return [norm(slug, j.get("title"), (j.get("location") or {}).get("name"),
                 j.get("absolute_url"), j.get("content")) for j in d["jobs"]]


def from_lever(slug):
    d = get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if not isinstance(d, list):
        return []
    return [norm(slug, j.get("text"), (j.get("categories") or {}).get("location"),
                 j.get("hostedUrl"),
                 (j.get("descriptionPlain") or "") + " " +
                 " ".join(x.get("text", "") for x in (j.get("lists") or [])))
            for j in d]


def from_ashby(slug):
    d = get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    if not d or "jobs" not in d:
        return []
    return [norm(slug, j.get("title"), j.get("location"), j.get("jobUrl"),
                 j.get("descriptionPlain") or "") for j in d["jobs"]]


def from_workable(slug):
    d = get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true")
    if not d or "jobs" not in d:
        return []
    out = []
    for j in d["jobs"]:
        loc = ", ".join(x for x in [j.get("city"), j.get("country")] if x)
        out.append(norm(slug, j.get("title"), loc, j.get("url"),
                        (j.get("description") or "") + " " + (j.get("requirements") or "")))
    return out


def from_smartrecruiters(slug):
    d = get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100")
    if not d or "content" not in d:
        return []
    out = []
    for j in d["content"]:
        loc = j.get("location") or {}
        where = ", ".join(x for x in [loc.get("city"), loc.get("country")] if x)
        out.append(norm(slug, j.get("name"), where,
                        f"https://jobs.smartrecruiters.com/{slug}/{j.get('id')}", ""))
    return out


def from_recruitee(slug):
    d = get(f"https://{slug}.recruitee.com/api/offers/")
    if not d or "offers" not in d:
        return []
    return [norm(slug, j.get("title"),
                 ", ".join(x for x in [j.get("city"), j.get("country")] if x),
                 j.get("careers_url"),
                 (j.get("description") or "") + " " + (j.get("requirements") or ""))
            for j in d["offers"]]


ATS = [from_greenhouse, from_lever, from_ashby,
       from_workable, from_smartrecruiters, from_recruitee]


def from_jobtech():
    out = []
    for q in ["copywriter", "brand manager", "communications manager",
              "content lead", "creative strategist", "brand lead",
              "head of brand", "senior copywriter", "editorial"]:
        d = get("https://jobsearch.api.jobtechdev.se/search?limit=50&q="
                + urllib.parse.quote(q))
        if not d:
            continue
        for j in d.get("hits", []):
            wp = j.get("workplace_address") or {}
            emp = (j.get("employer") or {}).get("name") or "Swedish market"
            out.append(norm(emp, j.get("headline"),
                            ", ".join(x for x in [wp.get("municipality"),
                                                  wp.get("region")] if x),
                            j.get("webpage_url") or "",
                            (j.get("description") or {}).get("text", "")))
        time.sleep(0.4)
    return out


# ---------------------------------------------------------------- filtering

def language_walled(body):
    """True only if a language is demanded, not merely mentioned."""
    for pat in (LANG_AFTER, LANG_BEFORE):
        for m in pat.finditer(body):
            start = body.rfind(".", 0, m.start()) + 1
            end = body.find(".", m.end())
            sentence = body[start:end if end > 0 else len(body)]
            if not LANG_SOFTENER.search(sentence):
                return True
    return False


def keep(job):
    t = job["title"].lower()
    b = job["body"].lower()
    blob = t + " " + b + " " + job["location"].lower()

    if not any(k in t for k in INCLUDE_TITLE):
        return False
    if any(k in t for k in EXCLUDE_TITLE):
        return False
    if REQUIRE_SENIORITY and not any(k in t for k in MIN_SENIORITY):
        return False
    if any(re.search(r"\b" + re.escape(k) + r"\b", t) for k in LANGS):
        return False
    if language_walled(b):
        return False
    if any(k in b for k in EXCLUDE_BODY):
        return False
    if any(k in b for k in NO_SPONSOR):
        return False
    if not any(k in blob for k in PLACES):
        return False
    return True


def sponsors(body):
    """True only if the ad positively says it helps. None means unstated."""
    b = body.lower()
    if any(k in b for k in NO_SPONSOR):
        return False
    if any(k in b for k in YES_SPONSOR):
        return True
    return None


def load_existing():
    if os.path.exists(OUT):
        try:
            return {r["id"]: r for r in json.load(open(OUT))["roles"]}
        except Exception:
            return {}
    return {}


def main():
    cv_terms = load_cv_terms()
    print(f"CV terms loaded: {len(cv_terms)}")
    existing = load_existing()
    today = date.today().isoformat()
    found = []

    print("Scanning company boards...")
    for slug in COMPANIES:
        for fn in ATS:
            got = fn(slug)
            if got:
                print(f"  {slug}: {len(got)}")
                found.extend(got)
                break
        sys.stdout.flush()

    print("Scanning Swedish market...")
    found.extend(from_jobtech())

    roles, seen_ids, dropped, bodies = [], set(), 0, {}
    for j in found:
        if not keep(j):
            dropped += 1
            continue
        rid = re.sub(r"\W+", "-", (j["url"] or j["company"] + j["title"]).lower())[:120]
        if rid in seen_ids:
            continue
        seen_ids.add(rid)

        pct, hits, yrs = score(j, cv_terms)
        bodies[rid] = j["body"]
        prev = existing.get(rid)
        roles.append({
            "id": rid,
            "title": j["title"],
            "company": j["company"],
            "location": j["location"] or "Not stated",
            "url": j["url"],
            "score": pct,
            "matched": hits,
            "years": yrs,
            "summary": j["body"][:400],
            "first_seen": prev["first_seen"] if prev else today,
            "is_new": prev is None,
        })

    # closed roles drop off, but keep anything already actioned
    roles.sort(key=lambda r: (-r["score"], r["company"]))
    add_drafts(roles, bodies, existing)

    json.dump({
        "updated": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "scanned": len(found),
        "roles": roles,
    }, open(OUT, "w"), indent=1)

    sponsored = sum(1 for r in roles
                    if any(h.startswith("sponsorship") for h in r["matched"]))
    print(f"Scanned {len(found)}. Dropped {dropped} on filters.")
    print(f"Kept {len(roles)}, of which {sponsored} mention sponsorship or relocation.")
    new = sum(1 for r in roles if r["is_new"])
    open(os.path.join(HERE, "newcount.txt"), "w").write(str(new))
    print(f"\nDone. {len(roles)} roles kept, {new} new. Written to roles.json")


if __name__ == "__main__":
    main()
