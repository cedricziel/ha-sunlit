#!/usr/bin/env bash
#
# verify-api.sh — probe the Sunlit REST API to validate assumptions behind
# issue #95 ("Ungültige sonstige Parameter" at startup).
#
# It answers, with real responses:
#   1. Does POST /v1.2/device/list fail WITHOUT a body? (the #95 error)
#   2. Does it succeed WITH {familyId, deviceType}? (the documented contract)
#   3. Does deviceType "ALL" work, or does the API want "" (per openapi.yaml)?
#   4. Are there any devices with spaceId == null across all families?
#      (decides whether "aggregate across families" can find unassigned devices)
#   5. Is the error `message` field a localized dict ({"DE": ...})?
#
# It then probes a broad set of read-only endpoints documented in openapi.yaml
# (account, space, strategy, statistics, device) and reports each one's `code`
# plus a one-line shape of `content`, so drift between the spec and the live API
# is easy to spot. Write/control endpoints are listed but never called.
#
# Usage:
#   Auth with credentials (logs in, prints nothing secret):
#     SUNLIT_EMAIL=you@example.com SUNLIT_PASSWORD=secret ./scripts/verify-api.sh
#   Or reuse an existing bearer token:
#     SUNLIT_TOKEN=eyJ... ./scripts/verify-api.sh
#
# Optional:
#   SUNLIT_BASE_URL  override API base (default: https://api.sunlitsolar.de/rest;
#                    the SunEnergyXT app v1.8.1 uses https://api.sunenergyxt.com/rest)

set -uo pipefail

BASE_URL="${SUNLIT_BASE_URL:-https://api.sunlitsolar.de/rest}"
UA="ha-sunlit-verify/1.0 (+https://github.com/cedricziel/ha-sunlit)"

# ---- pretty output ---------------------------------------------------------
if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; DIM=$'\033[2m'; RESET=$'\033[0m'
else
  BOLD=""; GREEN=""; RED=""; YELLOW=""; DIM=""; RESET=""
fi
section() { printf '\n%s== %s ==%s\n' "$BOLD" "$1" "$RESET"; }
pass()    { printf '%s  PASS%s %s\n' "$GREEN" "$RESET" "$1"; }
fail()    { printf '%s  FAIL%s %s\n' "$RED" "$RESET" "$1"; }
note()    { printf '%s  %s%s\n' "$DIM" "$1" "$RESET"; }

# ---- dependencies ----------------------------------------------------------
for dep in curl jq; do
  command -v "$dep" >/dev/null 2>&1 || { echo "Error: '$dep' is required." >&2; exit 1; }
done

# ---- load .env (gitignored) ------------------------------------------------
# Looks for $SUNLIT_ENV_FILE, else .env in the repo root (script's parent dir),
# else .env in the current directory. Already-set environment variables win.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${SUNLIT_ENV_FILE:-}"
if [[ -z "$ENV_FILE" ]]; then
  for candidate in "$REPO_ROOT/.env" "./.env"; do
    [[ -f "$candidate" ]] && { ENV_FILE="$candidate"; break; }
  done
fi
if [[ -n "$ENV_FILE" && -f "$ENV_FILE" ]]; then
  note "loading credentials from $ENV_FILE"
  while IFS='=' read -r key val; do
    key="${key#"${key%%[![:space:]]*}"}"        # ltrim
    [[ -z "$key" || "$key" == \#* ]] && continue # skip blanks/comments
    [[ -n "${!key:-}" ]] && continue             # existing env wins
    val="${val%$'\r'}"                           # tolerate CRLF
    val="${val#[\"\']}"; val="${val%[\"\']}"     # strip one layer of quotes
    export "$key=$val"
  done < "$ENV_FILE"
fi

# ---- request helper --------------------------------------------------------
# request METHOD PATH [JSON_BODY]  -> prints body, then a final line with HTTP status.
request() {
  local method="$1" path="$2" body="${3-}"
  local args=(-sS -X "$method" -H "User-Agent: $UA" -H "Content-Type: application/json")
  [[ -n "${TOKEN:-}" ]] && args+=(-H "Authorization: Bearer $TOKEN")
  [[ "${3+set}" == "set" ]] && args+=(--data "$body")
  curl "${args[@]}" -w $'\n%{http_code}' "$BASE_URL$path"
}
http_of() { tail -n1 <<<"$1"; }
body_of() { sed '$d' <<<"$1"; }
code_of() { jq -r '.code // "?"' <<<"$1" 2>/dev/null; }
msg_of()  { jq -rc '.message // ""' <<<"$1" 2>/dev/null; }

# probe METHOD PATH BODY DESC
# Calls an endpoint and reports code 0 + a one-line `content` shape, or the
# failing HTTP/code/message. Pass BODY="" for GET / bodyless requests; pass a
# literal '{}' to send an empty JSON object.
probe() {
  local method="$1" path="$2" body="$3" desc="$4"
  local resp jb http code summary
  if [[ -n "$body" ]]; then
    resp=$(request "$method" "$path" "$body")
  else
    resp=$(request "$method" "$path")
  fi
  jb=$(body_of "$resp"); http=$(http_of "$resp"); code=$(code_of "$jb")
  [[ -z "$code" ]] && code="?"
  if [[ "$code" == "0" ]]; then
    summary=$(jq -rc '
      .content as $c |
      if   ($c|type)=="array"  then "array[\($c|length)]"
      elif ($c|type)=="object" then "{\($c|keys|length) keys: \($c|keys|.[0:6]|join(", "))\(if ($c|keys|length)>6 then ", …" else "" end)}"
      elif $c==null            then "null"
      else ($c|tostring) end' <<<"$jb" 2>/dev/null)
    pass "$desc  [content: ${summary:-?}]"
  else
    fail "$desc — HTTP $http, code $code, msg $(msg_of "$jb")"
  fi
}

# ---- authenticate ----------------------------------------------------------
section "Auth"
TOKEN="${SUNLIT_TOKEN:-}"
if [[ -z "$TOKEN" ]]; then
  : "${SUNLIT_EMAIL:?set SUNLIT_EMAIL + SUNLIT_PASSWORD, or SUNLIT_TOKEN}"
  : "${SUNLIT_PASSWORD:?set SUNLIT_EMAIL + SUNLIT_PASSWORD, or SUNLIT_TOKEN}"
  login_payload=$(jq -nc --arg a "$SUNLIT_EMAIL" --arg p "$SUNLIT_PASSWORD" '{account:$a,password:$p}')
  resp=$(request POST /user/login "$login_payload")
  jbody=$(body_of "$resp")
  TOKEN=$(jq -r '.content.access_token // empty' <<<"$jbody")
  if [[ -z "$TOKEN" ]]; then
    fail "login failed (HTTP $(http_of "$resp"), code $(code_of "$jbody"), message $(msg_of "$jbody"))"
    exit 1
  fi
  pass "logged in as $SUNLIT_EMAIL (token ${TOKEN:0:6}…, ${#TOKEN} chars)"
else
  pass "using SUNLIT_TOKEN (${TOKEN:0:6}…, ${#TOKEN} chars)"
fi

# ---- families --------------------------------------------------------------
section "GET /family/list"
resp=$(request GET /family/list)
fbody=$(body_of "$resp")
if [[ "$(code_of "$fbody")" != "0" ]]; then
  fail "HTTP $(http_of "$resp"), code $(code_of "$fbody"), message $(msg_of "$fbody")"
  exit 1
fi
FAMILY_IDS=()
while IFS= read -r line; do
  [[ -n "$line" ]] && FAMILY_IDS+=("$line")
done < <(jq -r '.content[].id' <<<"$fbody")
if [[ ${#FAMILY_IDS[@]} -eq 0 ]]; then
  fail "no families returned for this account"
  exit 1
fi
pass "${#FAMILY_IDS[@]} families: ${FAMILY_IDS[*]}"
jq -r '.content[] | "    family \(.id)  \(.name)  deviceCount=\(.deviceCount // "?")"' <<<"$fbody"
FID="${FAMILY_IDS[0]}"

# ---- device/list WITHOUT body (reproduces #95) -----------------------------
section "POST /v1.2/device/list  — no body (issue #95)"
resp=$(request POST /v1.2/device/list)          # note: no 3rd arg -> no --data
dbody=$(body_of "$resp")
dcode=$(code_of "$dbody")
if [[ "$dcode" == "0" ]]; then
  fail "expected rejection but got code 0 — bodyless call actually works?!"
else
  pass "rejected as expected: HTTP $(http_of "$resp"), code $dcode"
  note "message: $(msg_of "$dbody")"
  if jq -e '.message | type == "object"' <<<"$dbody" >/dev/null 2>&1; then
    note "→ message is a localized OBJECT (e.g. {\"DE\": …}); api_client logs it raw"
  fi
fi

# ---- device/list with deviceType "ALL" (what the code sends) ---------------
section "POST /v1.2/device/list  — {familyId:$FID, deviceType:\"ALL\"}"
resp=$(request POST /v1.2/device/list "$(jq -nc --argjson f "$FID" '{familyId:$f,deviceType:"ALL"}')")
abody=$(body_of "$resp")
if [[ "$(code_of "$abody")" == "0" ]]; then
  pass "code 0, $(jq '.content.content | length' <<<"$abody") devices"
else
  fail "code $(code_of "$abody"): $(msg_of "$abody")  (does the API reject \"ALL\"?)"
fi

# ---- device/list with deviceType "" (what openapi.yaml documents) ----------
section "POST /v1.2/device/list  — {familyId:$FID, deviceType:\"\"}"
resp=$(request POST /v1.2/device/list "$(jq -nc --argjson f "$FID" '{familyId:$f,deviceType:""}')")
ebody=$(body_of "$resp")
if [[ "$(code_of "$ebody")" == "0" ]]; then
  pass "code 0, $(jq '.content.content | length' <<<"$ebody") devices"
else
  fail "code $(code_of "$ebody"): $(msg_of "$ebody")"
fi

# ---- device/list with deviceType only, no familyId -------------------------
section "POST /v1.2/device/list  — {deviceType:\"ALL\"} (missing familyId)"
resp=$(request POST /v1.2/device/list '{"deviceType":"ALL"}')
nbody=$(body_of "$resp")
if [[ "$(code_of "$nbody")" == "0" ]]; then
  note "accepted without familyId (returned $(jq '.content.content | length' <<<"$nbody") devices)"
else
  pass "rejected without familyId: code $(code_of "$nbody"), $(msg_of "$nbody")"
fi

# ---- spaceId survey across ALL families ------------------------------------
section "spaceId survey (decides the #95 fix)"
total=0; nullspace=0
for fid in "${FAMILY_IDS[@]}"; do
  resp=$(request POST /v1.2/device/list "$(jq -nc --argjson f "$fid" '{familyId:$f,deviceType:"ALL"}')")
  fb=$(body_of "$resp")
  [[ "$(code_of "$fb")" == "0" ]] || { note "family $fid: error $(msg_of "$fb")"; continue; }
  cnt=$(jq '.content.content | length' <<<"$fb")
  nul=$(jq '[.content.content[] | select(.spaceId == null)] | length' <<<"$fb")
  total=$((total + cnt)); nullspace=$((nullspace + nul))
  note "family $fid: $cnt devices, $nul with spaceId=null"
  jq -r '.content.content[] | "      device \(.deviceId)  type=\(.deviceType)  spaceId=\(.spaceId)"' <<<"$fb"
done

section "Summary for #95"
echo "  • Total devices across families: $total"
echo "  • Devices with spaceId == null:  $nullspace"
if (( nullspace > 0 )); then
  echo "  → 'Aggregate across families' WOULD find unassigned devices."
else
  echo "  → No spaceId=null devices found via family-scoped calls; the"
  echo "    'unassigned devices' feature cannot work via this endpoint →"
  echo "    favor removing it / silencing the bodyless call."
fi

# ---- broad read-only endpoint coverage (from openapi.yaml) ------------------
# Probes a representative set of documented read endpoints and prints code +
# a one-line `content` shape. Uses the first family ($FID) as spaceId/familyId
# (they share the same numeric id in this API) and the first device for
# device-scoped calls. WRITE/control endpoints are listed but NOT called.
section "Spec endpoint coverage (read-only) — space/family $FID"

YEAR=$(date +%Y); MONTH=$(date +%m); DAY=$(date +%d)
MONTH_INT=$((10#$MONTH)); DAY_INT=$((10#$DAY))   # 10# avoids octal on 08/09
TODAY="$YEAR-$MONTH-$DAY"
FIRST_DEVICE_ID=$(jq -r '.content.content[0].deviceId // empty' <<<"${abody:-}" 2>/dev/null)
sid=$(jq -nc --argjson f "$FID" '{spaceId:$f}')
fidbody=$(jq -nc --argjson f "$FID" '{familyId:$f}')

note "account / system"
probe POST /user/info            '{}' "POST /user/info"
probe POST /v1.5/message/summary '{}' "POST /v1.5/message/summary"
probe GET  /health/status        ''   "GET  /health/status"

note "space-level"
probe POST /v1.5/space/index                    "$sid" "POST /v1.5/space/index"
probe POST /v1.1/space/soc                       "$sid" "POST /v1.1/space/soc"
probe POST /v1.6/tariff/index                    "$sid" "POST /v1.6/tariff/index"
probe POST /v1.6/chargingBox/checkSpaceStrategy  "$sid" "POST /v1.6/chargingBox/checkSpaceStrategy"
probe POST /v1.6/rabot/state                     "$sid" "POST /v1.6/rabot/state"
probe POST /v1.6/rabot/day/price "$(jq -nc --argjson f "$FID" --arg d "$TODAY" '{showTax:true,spaceId:$f,day:$d,showStrategy:false}')" "POST /v1.6/rabot/day/price"
probe POST /v1.6/space/local/infoV2              "$sid" "POST /v1.6/space/local/infoV2"

note "strategy"
probe POST /v1.8/strategy/my/list       "$sid"     "POST /v1.8/strategy/my/list"
probe POST /v1.7/strategy/device/status "$sid"     "POST /v1.7/strategy/device/status"
probe POST /v1.1/space/currentStrategy  "$fidbody" "POST /v1.1/space/currentStrategy  (legacy)"
probe POST /v1.1/space/strategyHistory  "$fidbody" "POST /v1.1/space/strategyHistory  (legacy)"

note "statistics (space-scoped)"
probe POST /v1.1/space/statistics/static          "$sid" "POST /v1.1/space/statistics/static"
probe POST /v1.1/space/statistics/dynamic/power    "$(jq -nc --argjson f "$FID" --argjson y "$YEAR" --argjson m "$MONTH_INT" --argjson d "$DAY_INT" '{spaceId:$f,year:$y,month:$m,day:$d}')" "POST /v1.1/space/statistics/dynamic/power"
probe POST /v1.1/space/statistics/dynamic/earning  "$(jq -nc --argjson f "$FID" --argjson y "$YEAR" --argjson m "$MONTH_INT" '{spaceId:$f,year:$y,month:$m}')" "POST /v1.1/space/statistics/dynamic/earning"

note "device-scoped"
if [[ -n "$FIRST_DEVICE_ID" ]]; then
  note "using deviceId=$FIRST_DEVICE_ID"
  probe GET  "/device/$FIRST_DEVICE_ID"      ''  "GET  /device/{deviceId}"
  probe POST /v1.1/statistics/static/device  "$(jq -nc --argjson d "$FIRST_DEVICE_ID" '{deviceId:$d}')" "POST /v1.1/statistics/static/device"
  probe POST /statistics/instantPower        "$(jq -nc --argjson d "$FIRST_DEVICE_ID" --arg y "$YEAR" --arg m "$MONTH" --arg da "$DAY" '{deviceId:$d,year:$y,month:$m,day:$da}')" "POST /statistics/instantPower"
  probe POST /v1.3/statistics/instantPower/batteryIO "$(jq -nc --argjson d "$FIRST_DEVICE_ID" --arg y "$YEAR" --arg m "$MONTH" --arg da "$DAY" '{deviceId:$d,year:$y,month:$m,day:$da}')" "POST /v1.3/statistics/instantPower/batteryIO"
else
  note "no devices in family $FID — skipping device-scoped probes"
fi

section "Write/control endpoints (NOT called — reference only)"
note "POST /v1.7/battery/updateLocalModeConfig          {enable, deviceSn}"
note "POST /v2/remoteControl/power                      {deviceId, maxOutputPower}"
note "POST /device/remoteControlRecord/latest           {deviceId}"
note "POST /v1.6/tariffStrategy/add                     {familyId, lowPriceStrategy, highPriceStrategy, …}"
note "POST /v1.6/local/mode/deye/localSmart/updateFlag  {spaceId, enable, inverterSnList}"
note "POST /v1.7/device/dtu/checkFwVersion              {curFirmwareVersion}"
