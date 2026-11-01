#!/bin/sh
# Smoke test of the maps-web image: builds it, runs it next to two stub
# backends (oxigraph, mak-link-handler) on a throwaway network, and checks
# hosts, paths, login and headers. Needs Docker. Run from the repo root:
#   sh infra/web/smoke-test.sh
set -eu

IMG=maps-web:smoke
NET=maps-web-smoke
CURL="docker run --rm --network $NET curlimages/curl:8.11.1 -s"
fail=0

cleanup() { docker rm -f smoke-web smoke-oxigraph smoke-mak-link-handler >/dev/null 2>&1 || true; docker network rm $NET >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

docker pull -q curlimages/curl:8.11.1 >/dev/null
docker build -q -f infra/web/Dockerfile -t $IMG . >/dev/null
docker network create $NET >/dev/null
# Stubs answer with their name and the path they received.
stub() {  # stub <name> <port>
  conf=$(printf ':%s {\n\trespond "%s {uri}"\n}\n' "$2" "$1")
  docker run -d --name "smoke-$1" --network $NET --network-alias "$1" -e CONF="$conf" $IMG \
    sh -c 'printf "%s\n" "$CONF" > /tmp/Caddyfile && caddy run --config /tmp/Caddyfile' >/dev/null
}
stub oxigraph 7878
stub mak-link-handler 8000
docker run -d --name smoke-web --network $NET $IMG >/dev/null
sleep 2

# status <expected> <curl args...>
status() {
  want=$1; shift
  got=$($CURL -o /dev/null -w '%{http_code}' "$@" || true)
  if [ "$got" = "$want" ]; then echo "ok   $want $*"; else echo "FAIL $got (want $want) $*"; fail=1; fi
}
# body <expected substring> <curl args...>
body() {
  want=$1; shift
  if $CURL "$@" | grep -qF -- "$want"; then echo "ok   ~'$want' $*"; else echo "FAIL no '$want' in $*"; fail=1; fi
}
# header <expected header line substring> <curl args...>
header() {
  want=$1; shift
  if $CURL -D - -o /dev/null "$@" | grep -qiF -- "$want"; then echo "ok   [$want] $*"; else echo "FAIL no header '$want' in $*"; fail=1; fi
}

W=http://smoke-web
status 200 $W/
status 200 $W/health
status 404 $W/no-such-file
status 404 $W/admin/
status 301 -H Host:genjson.mapsofmaking.org $W/
header 'Location: https://home.mapsofmaking.org/' -H Host:genjson.mapsofmaking.org $W/
header 'Location: https://home.mapsofmaking.org/?resume=1' -H Host:genjson.mapsofmaking.org "$W/?resume=1"
status 200 -H Host:mothersand.mapsofmaking.org $W/
status 403 -X POST $W/sparql/update
status 204 -X OPTIONS $W/sparql/update
body 'oxigraph /query?query=ASK' "$W/sparql/query?query=ASK"
body 'mak-link-handler /api/space/x/raw' $W/api/space/x/raw
status 301 -H Host:genjson.mapsofmaking.org $W/anything
status 301 -H Host:genjson.mapsofmaking.org $W/api/geocode
header 'Location: https://home.mapsofmaking.org/?resume=1' -H Host:genjson.mapsofmaking.org "$W/old/path?resume=1"
header 'Location: https://home.mapsofmaking.org/' -H Host:genjson.mapsofmaking.org $W/old/path
body 'mak-link-handler /claim/abc' $W/claim/abc
header 'Content-Security-Policy: frame-ancestors *' -H Host:test.mapsofmaking.org $W/
header "'unsafe-eval'" -H Host:mothersand.mapsofmaking.org $W/
header 'Access-Control-Allow-Origin: *' $W/sparql/query
header 'X-Content-Type-Options: nosniff' $W/

status 200 $W/ns/mom
status 200 $W/ns/iop
status 200 $W/ns/crosswalks/mom-to-okw
status 200 $W/ns/sup.ttl
status 404 $W/ns/nothing
header 'Content-Type: text/turtle' $W/ns/mom
header 'Access-Control-Allow-Origin: *' $W/ns/core
body '@prefix mom: <https://mapsofmaking.org/ns/mom#>' $W/ns/mom

exit $fail
