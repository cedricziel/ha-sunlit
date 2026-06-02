#!/usr/bin/env bash
#
# probe-rabot.sh — verify what the Rabot dynamic-tariff endpoints expose, and
# how far into the past / future they serve, against a real account.
#
# Read-only. No write or control endpoints are called.
#
# Sections (pass section names as args to run a subset; default runs all):
#   tariff   POST /v1.6/tariff/index               — current price block + flags
#   today    POST /v1.6/rabot/day/price (today)    — confirm full 24h shape
#   future   POST /v1.6/rabot/day/price for +0..+30d — forward horizon
#   past     POST /v1.6/rabot/day/price for -1..-547d — backward horizon
#
# Usage:
#   SUNLIT_EMAIL=… SUNLIT_PASSWORD=… ./scripts/probe-rabot.sh
#   SUNLIT_TOKEN=eyJ…              ./scripts/probe-rabot.sh today future
#   (Credentials are loaded from .env in the repo root if present.)
#
# Environment:
#   SUNLIT_BASE_URL  override API base (default: SunEnergyXT host)
#   SUNLIT_ENV_FILE  override the .env path

set -uo pipefail

BASE_URL="${SUNLIT_BASE_URL:-https://api.sunenergyxt.com/rest}"
UA="ha-sunlit-rabot-probe/1.1"

# ---- pretty output --------------------------------------------------------
if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; RED=""; DIM=""; RESET=""
fi
section() { printf '\n%s== %s ==%s\n' "$BOLD" "$1" "$RESET"; }
note()    { printf '%s  %s%s\n' "$DIM" "$1" "$RESET"; }
ok()      { printf '%s  ok%s   %s\n' "$GREEN" "$RESET" "$1"; }
bad()     { printf '%s  bad%s  %s\n' "$RED" "$RESET" "$1"; }

# ---- dependencies ---------------------------------------------------------
for dep in curl jq; do
  command -v "$dep" >/dev/null 2>&1 || { echo "Error: '$dep' is required." >&2; exit 1; }
done

# ---- .env loader (env wins) ----------------------------------------------
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${SUNLIT_ENV_FILE:-}"
if [[ -z "$ENV_FILE" ]]; then
  for c in "$REPO_ROOT/.env" "./.env"; do
    [[ -f "$c" ]] && { ENV_FILE="$c"; break; }
  done
fi
if [[ -n "$ENV_FILE" && -f "$ENV_FILE" ]]; then
  note "loading credentials from $ENV_FILE"
  while IFS='=' read -r key val; do
    key="${key#"${key%%[![:space:]]*}"}"
    [[ -z "$key" || "$key" == \#* ]] && continue
    [[ -n "${!key:-}" ]] && continue
    val="${val%$'\r'}"; val="${val#[\"\']}"; val="${val%[\"\']}"
    export "$key=$val"
  done < "$ENV_FILE"
fi

# ---- HTTP helper ----------------------------------------------------------
# req METHOD PATH [JSON_BODY]
req() {
  local method="$1" path="$2"
  local args=(-sS -X "$method" -H "User-Agent: $UA" -H "Content-Type: application/json")
  [[ -n "${TOKEN:-}" ]] && args+=(-H "Authorization: Bearer $TOKEN")
  [[ "${3+set}" == "set" ]] && args+=(--data "$3")
  curl "${args[@]}" "$BASE_URL$path"
}

# Local-tz "today + N days" — works on both GNU and BSD date.
date_offset() {
  local off="$1"
  if [[ "$off" -ge 0 ]]; then
    date -v+${off}d +%Y-%m-%d 2>/dev/null || date -d "+${off} days" +%Y-%m-%d
  else
    date -v${off}d +%Y-%m-%d 2>/dev/null || date -d "${off} days" +%Y-%m-%d
  fi
}

# ---- auth -----------------------------------------------------------------
section "auth"
TOKEN="${SUNLIT_TOKEN:-}"
if [[ -z "$TOKEN" ]]; then
  : "${SUNLIT_EMAIL:?need SUNLIT_EMAIL+SUNLIT_PASSWORD or SUNLIT_TOKEN}"
  : "${SUNLIT_PASSWORD:?need SUNLIT_EMAIL+SUNLIT_PASSWORD or SUNLIT_TOKEN}"
  payload=$(jq -nc --arg a "$SUNLIT_EMAIL" --arg p "$SUNLIT_PASSWORD" '{account:$a,password:$p}')
  TOKEN=$(req POST /user/login "$payload" | jq -r '.content.access_token // empty')
fi
[[ -z "$TOKEN" ]] && { bad "login failed"; exit 1; }
ok "authenticated (token len ${#TOKEN})"

SPACE=$(req GET /family/list | jq -r '.content[0].id // empty')
[[ -z "$SPACE" ]] && { bad "no spaceId from /family/list"; exit 1; }
ok "using spaceId=$SPACE (first family)"
note "local now=$(date '+%Y-%m-%d %H:%M:%S %Z')  utc=$(date -u '+%Y-%m-%d %H:%M:%S')"

# ---- which sections to run -----------------------------------------------
SECTIONS=("$@")
[[ ${#SECTIONS[@]} -eq 0 ]] && SECTIONS=(tariff today future past)

want() { local s; for s in "${SECTIONS[@]}"; do [[ "$s" == "$1" ]] && return 0; done; return 1; }

# ---- /v1.6/tariff/index ---------------------------------------------------
if want tariff; then
  section "/v1.6/tariff/index"
  req POST /v1.6/tariff/index "{\"spaceId\": $SPACE}" | jq '{
    code, message,
    rabotHasContract:      .content.rabotHasContract,
    rabotHasContractPrice: .content.rabotHasContractPrice,
    has_hourPriceDTO:      (.content.rabotHourPriceDTO != null),
    current_priceTag:      .content.rabotHourPriceDTO.priceTag,
    current_hour:          .content.rabotHourPriceDTO.hour,
    current_priceInCt:     .content.rabotHourPriceDTO.priceInCentPerKwh
  }'
fi

# ---- /v1.6/rabot/day/price (today, full shape) ---------------------------
if want today; then
  section "/v1.6/rabot/day/price  (today, full envelope)"
  TODAY=$(date_offset 0)
  RESP=$(req POST /v1.6/rabot/day/price \
    "{\"spaceId\": $SPACE, \"day\": \"$TODAY\", \"showTax\": true, \"showStrategy\": false}")
  jq '{
    code, message,
    content_keys:        (.content | if type=="object" then keys else null end),
    prices_len:          (.content.prices | length // 0),
    utcOffset:           .content.utcOffset,
    sample_entry:        .content.prices[0],
    tag_distribution:    [.content.prices[]?.priceTag] | group_by(.) | map({tag:.[0], n:length})
  }' <<<"$RESP"
fi

# ---- compact one-line probe for horizon sections -------------------------
probe_day() {
  local off="$1" d resp n_prices first_ts last_ts avg first_tag last_tag tags_dist
  d=$(date_offset "$off")
  resp=$(req POST /v1.6/rabot/day/price \
    "{\"spaceId\": $SPACE, \"day\": \"$d\", \"showTax\": true, \"showStrategy\": false}")
  n_prices=$(jq -r '.content.prices | length // 0' <<<"$resp")
  first_ts=$(jq -r '.content.prices[0].timestamp // "-"'  <<<"$resp")
  last_ts=$(jq -r '.content.prices[-1].timestamp // "-"' <<<"$resp")
  avg=$(jq -r '.content.prices[0].avgPriceInCentPerKwh // "-"' <<<"$resp")
  first_tag=$(jq -r '.content.prices[0].priceTag // "-"' <<<"$resp")
  last_tag=$(jq -r '.content.prices[-1].priceTag // "-"' <<<"$resp")
  tags_dist=$(jq -rc '[.content.prices[]?.priceTag] | group_by(.) | map("\(.[0])=\(length)") | join(",")' <<<"$resp")
  local lab
  if [[ "$off" -ge 0 ]]; then lab="+${off}d"; else lab="${off}d"; fi
  printf '  %-7s  day=%s  prices=%-2s  avg=%s  range=%s..%s  tags=%s\n' \
    "$lab" "$d" "$n_prices" "$avg" "$first_ts" "$last_ts" "$tags_dist"
}

if want future; then
  section "forward horizon — /v1.6/rabot/day/price"
  for off in 0 1 2 3 7 14 30; do probe_day "$off"; done
fi

if want past; then
  section "backward horizon — /v1.6/rabot/day/price"
  for off in -1 -7 -30 -90 -180 -365 -547; do probe_day "$off"; done
fi
