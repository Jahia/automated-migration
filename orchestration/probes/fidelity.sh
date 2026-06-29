#!/usr/bin/env bash
# fidelity.sh — DEPRECATED (curl/static, headings-only). Superseded by
# fidelity-all.sh (loops fidelity-live.sh, JS-rendered both sides). It passed
# visually-wrong pages once JS ran, so it is NO LONGER wired into any plan step.
# Kept only as a no-browser fallback. Do not re-wire it; use fidelity-all.sh.
#
# fidelity.sh — ANTI-HALLUCINATION gate.
#
# The agent must not *claim* a page "looks like the original". This probe PROVES
# it by diffing the captured REFERENCE page against the LOCAL render, section by
# section, and FAILING when the local is missing what the reference has.
#
# It compares two cheap, language-stable signals that catch the mistakes that
# actually happened in practice:
#   1. headings (h1–h4 text) present in the reference but MISSING locally
#      → "missing EN VIDÉO section", "missing SIAL en bref", a whole block absent
#   2. repeated-card / list-item counts per section
#      → reference shows a 12-card listing, local shows 0–N text blocks
#
# The <reference> is normally the live original URL — this probe fetches it
# itself. A saved file (.html/.mhtml) is the FALLBACK for when the page can't be
# fetched (bot-protection / login / JS-only): in that case capture it in the
# browser, or halt and ask the operator. Do NOT diff against a remembered page.
#
# Usage:
#   fidelity.sh <reference_url | reference.(mhtml|html)> <live_url> [min_heading_match_pct]
# e.g.
#   orchestration/probes/fidelity.sh \
#     https://www.sialparis.com/fr-FR \
#     http://localhost:8080/fr/sites/sial-paris/home.html 85
#   # fallback when the reference is bot-protected:
#   orchestration/probes/fidelity.sh \
#     orchestration/pages/sial-paris/SIAL-Paris-home.mhtml \
#     http://localhost:8080/fr/sites/sial-paris/home.html 85
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_lib.sh
source "$HERE/_lib.sh"

ref="${1:?reference url or .mhtml/.html file required}"
url="${2:?live page URL required}"
min_pct="${3:-85}"

# Reference as a URL → fetch it ourselves (the default). Only fall back to a
# saved file when fetching can't return the real page.
case "$ref" in
  http://*|https://*)
    curl -sL -A "Mozilla/5.0" "$ref" > /tmp/fidelity-ref.html
    if ! grep -qi "<main\|<body\|<html" /tmp/fidelity-ref.html \
       || grep -qiE "just a moment|cf-browser-verification|enable javascript and cookies|unable to access|been blocked|access denied|attention required|verify you are( a)? human|captcha|error 1[0-9]{3}" /tmp/fidelity-ref.html; then
      fail "could not fetch the reference page ($ref) — it returned a bot-protection / block / JS-gated page.
  Capture it in the browser and pass the saved file, OR halt and ask the operator for it.
  Do not diff against a guessed/remembered page."
    fi
    ref=/tmp/fidelity-ref.html ;;
  *)
    [ -f "$ref" ] || fail "reference not found: $ref (pass the original URL to capture it, or a saved file — never work from memory)" ;;
esac

# Fetch the live render (try guest, then root creds in case the page needs auth)
live_html="$(curl -s "$url")"
if ! printf '%s' "$live_html" | grep -qi "<main\|<body"; then
  live_html="$(curl -s -u "${JAHIA_USER:-root:root}" "$url")"
fi
printf '%s' "$live_html" > /tmp/fidelity-live.html

python3 - "$ref" "/tmp/fidelity-live.html" "$min_pct" <<'PY'
import sys, re, email, unicodedata
from email import policy
try:
    from bs4 import BeautifulSoup
except Exception:
    print("FAIL: BeautifulSoup not available (pip install beautifulsoup4)"); sys.exit(1)

ref_path, live_path, min_pct = sys.argv[1], sys.argv[2], int(sys.argv[3])

def load_html(path):
    raw = open(path, "rb").read()
    if path.endswith(".mhtml") or raw[:4] in (b"From", b"MIME") or b"Content-Type: multipart" in raw[:2000]:
        msg = email.message_from_bytes(raw, policy=policy.default)
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                # get_content() mis-decodes when the part's declared charset is
                # wrong (é -> U+FFFD). Decode the raw transfer-decoded bytes as
                # UTF-8 ourselves, which is what these captures actually are.
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", "ignore")
                return part.get_content()
    return raw.decode("utf-8", "ignore")

def norm(s):
    # NFKD strips accents whether the source uses precomposed (é) or decomposed (e+´)
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = s.lower().replace("œ", "oe").replace("æ", "ae")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def main_of(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.find("main") or soup.body or soup

def headings(node):
    out, seen = [], set()
    for h in node.find_all(["h1", "h2", "h3", "h4"]):
        t = norm(h.get_text(" ", strip=True))
        if 3 <= len(t) <= 80 and t not in seen:
            seen.add(t); out.append(t)
    return out

def cards(node):
    return len(node.select("li, [class*=card], [class*=push-item], [class*=grid-]"))

ref_main = main_of(load_html(ref_path))
live_main = main_of(open(live_path, encoding="utf-8", errors="ignore").read())
ref_h = headings(ref_main)
# Anti-hallucination check: is each reference section's heading text PRESENT anywhere
# in the local render? (a section dropped during migration leaves no trace; a section
# rendered with a different tag/level still has its text.)
live_text = norm(live_main.get_text(" ", strip=True))
ref_cards, live_cards = cards(ref_main), cards(live_main)

# A real reference page has several section headings. Near-zero means the fetch
# returned a block/empty page, not the page — can't diff against that.
if len(ref_h) < 3:
    print(f"FAIL: the reference yielded only {len(ref_h)} heading(s) — it is almost certainly a "
          f"block/empty/JS-gated page, not the real content.\n"
          f"  Capture the original in the browser and pass the saved file, or halt and ask the operator.")
    sys.exit(1)

missing = [h for h in ref_h if h not in live_text]
matched = len(ref_h) - len(missing)
pct = round(100 * matched / len(ref_h)) if ref_h else 100

print(f"  reference section headings: {len(ref_h)} | present locally: {matched} ({pct}%)")
print(f"  repeated structures (cards/list items): reference {ref_cards} vs local {live_cards}")
if missing:
    print("  MISSING from local render (present in reference):")
    for h in missing:
        print(f"     - {h}")
if live_cards < ref_cards * 0.5 and ref_cards >= 4:
    print(f"  WARNING: local has < half the reference's repeated structures "
          f"({live_cards} vs {ref_cards}) — likely text blocks where the reference has a card listing.")

if pct < min_pct:
    print(f"FAIL: only {pct}% of reference headings render locally (min {min_pct}%). "
          f"The page does NOT match the reference — fix the missing sections, do not claim it does.")
    sys.exit(1)
if live_cards < ref_cards * 0.5 and ref_cards >= 4:
    print("FAIL: repeated-structure count far below reference — a listing/card section is missing or rendered as plain text.")
    sys.exit(1)
print(f"PASS: local render matches the reference on headings ({pct}%) and structure.")
PY
