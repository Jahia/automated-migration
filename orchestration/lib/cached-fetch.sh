#!/usr/bin/env bash
# Cached, rate-limited, WAF-aware fetch helper for reference-site scraping.
#
# Source it for the functions, or run it directly as a CLI (see bottom).
#
# Two non-negotiable policies this enforces:
#
#  1. CACHE LOCALLY. Every page/asset is written under
#     <project>/.reference/cache/ and reused on every later call. We NEVER
#     re-hit the live reference site for something already on disk. The cache is
#     in-project (not /tmp), so it survives sessions, context compaction and
#     re-runs. Re-running a migration must not re-scrape.
#
#  2. SLOW DOWN WHEN BLOCKED. A polite base delay sits between every request.
#     On any WAF / rate-limit / VPN-block signal (HTTP 403/429/500/502/503/520/
#     521/522/523/524, or a Cloudflare "Just a moment" / "Attention Required"
#     challenge body) we back off exponentially with jitter AND raise the
#     run-wide base delay so subsequent requests are gentler too. After
#     MAX_ATTEMPTS we stop and tell the caller to fall back to browser capture
#     (Chrome MCP get_page_text) — we never hammer a blocking origin.
#
# Tunables (override via env): RATE_DELAY (base seconds, default 2), MAX_ATTEMPTS
# (default 5), MAX_BACKOFF (per-sleep cap, default 120), CONNECT_TIMEOUT (15),
# MAX_TIME (60), SCRAPE_UA (browser UA), SCRAPE_LANG (Accept-Language).
#
# NOTE: do not `set -e`/`set -u` at file scope here — this file is sourced.

: "${RATE_DELAY:=2}"
: "${MAX_ATTEMPTS:=5}"
: "${MAX_BACKOFF:=120}"
: "${CONNECT_TIMEOUT:=15}"
: "${MAX_TIME:=60}"
: "${SCRAPE_UA:=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36}"
: "${SCRAPE_LANG:=fr-FR,fr;q=0.9,en;q=0.8}"

# Run-wide adaptive throttle. Once a block is seen, the base delay is raised here
# so the rest of the run is gentler. Keyed per shell-run via PPID.
_throttle_state() { printf '%s/.scrape-throttle.%s' "${TMPDIR:-/tmp}" "${PPID:-0}"; }

# cache_root <project_path>  -> echoes the durable cache directory
cache_root() {
  local proj="${1:?project_path required}"
  printf '%s/.reference/cache' "$proj"
}

# _cache_path <project_path> <url> -> deterministic on-disk path for a URL
_cache_path() {
  local proj="$1" url="$2" key
  key=$(printf '%s' "$url" | sed -E 's#^https?://##; s#\?.*$##; s#[^A-Za-z0-9._/-]#_#g; s#/+$#/index.html#')
  [ -z "$key" ] && key="index.html"
  case "$key" in */) key="${key}index.html";; esac
  case "$key" in *.*) : ;; *) key="${key}.html";; esac
  printf '%s/%s' "$(cache_root "$proj")" "$key"
}

_is_block_code() { case "$1" in 403|429|500|502|503|520|521|522|523|524) return 0;; *) return 1;; esac; }
_is_challenge() { grep -qiE 'just a moment|cf-chl|attention required|access denied|enable javascript and cookies|__cf_chl|cf-browser-verification' "$1" 2>/dev/null; }

# cache_get <project_path> <url>
# READ-ONLY cache check — NO network. Call this BEFORE any scrape (curl OR
# browser capture). Echoes the cached file path + exit 0 if present; exit 3 if
# not cached. This is the "always check cache before scraping again" gate.
cache_get() {
  local out; out="$(_cache_path "$1" "$2")"
  if [ -s "$out" ]; then printf '%s\n' "$out"; return 0; fi
  return 3
}

# cache_put <project_path> <url> [src_file]
# Save content into the cache under <url>'s canonical path. With no src_file (or
# "-") reads stdin. Use this to persist a BROWSER-captured page (Chrome MCP
# get_page_text) so the next run reuses it instead of re-capturing.
cache_put() {
  local out; out="$(_cache_path "$1" "$2")"; mkdir -p "$(dirname "$out")"
  if [ -z "${3:-}" ] || [ "${3:-}" = "-" ]; then cat > "$out"; else cp "$3" "$out"; fi
  printf '%s\n' "$out"
}

# cached_fetch <project_path> <url> [referer]
# Echoes the local cache file path on success.
# Returns: 0 ok (cache hit or fresh) | 2 WAF/rate-limit block (use browser) | 1 hard/non-block error
cached_fetch() {
  local proj="$1" url="$2" referer="${3:-}"
  local out; out="$(_cache_path "$proj" "$url")"
  # ALWAYS check cache first — never re-scrape a URL already on disk.
  # (FORCE_REFETCH=1 is the deliberate escape hatch to bypass the cache.)
  if [ -z "${FORCE_REFETCH:-}" ] && [ -s "$out" ]; then printf '%s\n' "$out"; return 0; fi
  mkdir -p "$(dirname "$out")"
  [ -z "$referer" ] && referer="$(printf '%s' "$url" | grep -oE '^https?://[^/]+')/"

  local base="$RATE_DELAY" st; st="$(_throttle_state)"
  [ -f "$st" ] && base="$(cat "$st" 2>/dev/null || echo "$RATE_DELAY")"

  local attempt=1 code
  while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
    sleep "$(awk -v b="$base" 'BEGIN{srand(); print b + rand()*b}' 2>/dev/null || echo "$base")"
    code=$(curl -sS -L --compressed \
        --connect-timeout "$CONNECT_TIMEOUT" --max-time "$MAX_TIME" \
        -A "$SCRAPE_UA" \
        -H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8" \
        -H "Accept-Language: $SCRAPE_LANG" \
        -H "Referer: $referer" \
        -o "$out" -w '%{http_code}' "$url" 2>/dev/null) || code=000

    if [ "$code" = "200" ] && ! _is_challenge "$out"; then
      printf '%s\n' "$out"; return 0
    fi

    if _is_block_code "$code" || { [ -s "$out" ] && _is_challenge "$out"; }; then
      rm -f "$out"
      local backoff newbase
      backoff=$(awk -v a="$attempt" -v cap="$MAX_BACKOFF" 'BEGIN{srand(); v=(2^a)*2 + rand()*3; if(v>cap)v=cap; print v}')
      newbase=$(awk -v b="$base" 'BEGIN{nb=b*1.5; if(nb<2)nb=2; if(nb>30)nb=30; print nb}')
      printf '%s' "$newbase" > "$st"; base="$newbase"
      echo "  ↳ WAF/rate-limit signal (HTTP ${code}) on ${url} — backing off ${backoff}s (attempt ${attempt}/${MAX_ATTEMPTS}, base now ${newbase}s)" >&2
      sleep "$backoff" 2>/dev/null || sleep 5
      attempt=$((attempt+1)); continue
    fi

    echo "  ↳ HTTP ${code} on ${url} (not a block, e.g. 404) — leaving uncached" >&2
    rm -f "$out"; return 1
  done

  echo "BLOCKED after ${MAX_ATTEMPTS} attempts: ${url}" >&2
  echo "  → The origin (WAF/Cloudflare) or your VPN is blocking automated fetches. Options, in order:" >&2
  echo "    1. Capture this page via the browser instead — Chrome MCP get_page_text — and save the text to the cache dir." >&2
  echo "    2. Re-run with a higher base delay, e.g. RATE_DELAY=8 (or 15), MAX_ATTEMPTS=8." >&2
  echo "    3. If you are on a corporate VPN the WAF distrusts, retry off-VPN or from a residential network." >&2
  echo "    4. For images specifically, use the in-Jahia importer (server-side browser headers) — see skill 03/09." >&2
  return 2
}

# crawl_site <project_path> <start_url> [level]
# Polite, retrying recursive crawl into the durable cache. Rate-limited so a WAF
# does not see a burst; retries transient/WAF codes; warns + advises slow-down
# if it still hits blocks.
crawl_site() {
  local proj="$1" url="$2" level="${3:-3}" dir log
  dir="$(cache_root "$proj")/_crawl"; mkdir -p "$dir"; log="$dir/_wget-log.txt"
  # ALWAYS check cache first: a completed crawl is reused, never repeated.
  if [ -z "${FORCE_REFETCH:-}" ] && [ -f "$dir/.crawl-complete" ]; then
    echo "Using cached crawl ($(find "$dir" -name '*.html' 2>/dev/null | wc -l | tr -d ' ') pages in $dir). Set FORCE_REFETCH=1 to re-crawl." >&2
    return 0
  fi
  wget --recursive --level="$level" --no-parent --adjust-extension --no-clobber \
       --reject "*.css,*.js,*.png,*.jpg,*.jpeg,*.gif,*.svg,*.woff,*.woff2,*.ttf,*.ico,*.pdf,*.zip" \
       --user-agent="$SCRAPE_UA" \
       --header="Accept-Language: $SCRAPE_LANG" \
       --wait="$RATE_DELAY" --random-wait --limit-rate=400k \
       --tries=5 --waitretry=30 --retry-on-http-error=429,503,500,520,522 \
       --timeout="$MAX_TIME" --server-response \
       --directory-prefix="$dir" "$url" 2>&1 | tee "$log"

  local blocked
  blocked=$(grep -cE "HTTP/[0-9.]+ (403|429|503|520|522)" "$log" 2>/dev/null || echo 0)
  echo "=== CRAWL RESULTS ===" >&2
  echo "Pages cached: $(find "$dir" -name '*.html' 2>/dev/null | wc -l | tr -d ' ')" >&2
  if [ "${blocked:-0}" -gt 0 ]; then
    echo "WARNING: ${blocked} WAF/rate-limit responses during crawl — the site is throttling automated fetches." >&2
    echo "  → Re-run with a higher RATE_DELAY (e.g. RATE_DELAY=8 ${BASH_SOURCE[0]} crawl ...), or capture the blocked pages via the browser (Chrome MCP)." >&2
  fi
  # surface failed URLs for the mandatory crawl-error report
  grep -E "HTTP/[0-9.]+ [4-9][0-9][0-9]" "$log" 2>/dev/null | grep -oE "https?://[^ ]+" | sort -u > "$dir/_crawl-errors.txt" 2>/dev/null || true
  # mark the crawl complete so a re-run reuses it instead of re-scraping
  : > "$dir/.crawl-complete"
}

# Direct CLI
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  cmd="${1:-}"; shift 2>/dev/null || true
  case "$cmd" in
    get)        cache_get "$@";;     # read-only cache check (no network) — ALWAYS call before scraping
    put)        cache_put "$@";;     # save a browser-captured page into the cache
    fetch)      cached_fetch "$@";;  # cache-first fetch (network only on miss)
    crawl)      crawl_site "$@";;    # cache-first recursive crawl (skips a completed crawl)
    cache-root) cache_root "$@";;
    *) echo "usage: cached-fetch.sh {get <project> <url> | put <project> <url> [file] | fetch <project> <url> [referer] | crawl <project> <url> [level] | cache-root <project>}" >&2
       echo "env: FORCE_REFETCH RATE_DELAY MAX_ATTEMPTS MAX_BACKOFF CONNECT_TIMEOUT MAX_TIME SCRAPE_UA SCRAPE_LANG" >&2
       exit 64;;
  esac
fi
