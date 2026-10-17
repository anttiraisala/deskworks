#!/bin/sh
# Run the tests of every project in the repository.
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
status=0

echo "== tilepane"
(cd "$root/tilepane" && PYTHONPATH=src:. python3 -m unittest discover -s tests -t .) || status=1

echo "== cascade-windows"
(cd "$root/cascade-windows" && python3 -m unittest discover -s tests) || status=1

if [ -d "$root/deskmap/tests" ]; then
    echo "== deskmap"
    (cd "$root/deskmap" && PYTHONPATH=src:. python3 -m unittest discover -s tests -t .) || status=1
fi

exit $status
