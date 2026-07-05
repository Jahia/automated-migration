#!/usr/bin/env bash
# publish_site.sh <project> <site> [locale] — THE single final publication act.
#
# EDIT-only doctrine (Julian, 2026-07-04): nothing publishes during the
# migration process — loads, probes and reconcile are EDIT-only and a stale
# LIVE is tolerated throughout. When the site is finished, Julian runs THIS
# once. It applies the proven unpublish-first sequence per target (a naive
# publish no-ops in 1 ms on corrupted publication metadata — measured), then
# proves the result with the strict belt (integrity.py --phase
# step_publish_final) and exits with its code. Idempotent: re-launchable,
# already-aligned targets are verified and skipped.
#
# Extra args (e.g. --dry) are passed through to publish_site.py.
set -u
proj="${1:?usage: publish_site.sh <project> <site> [locale]}"
site="${2:?usage: publish_site.sh <project> <site> [locale]}"
locale="${3:-en}"
cd "$(dirname "$0")/../.."
exec python3 orchestration/lib/publish_site.py "$proj" "$site" --locale "$locale" "${@:4}"
