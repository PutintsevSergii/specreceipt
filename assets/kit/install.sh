#!/bin/sh
# One command installs harness and its supported toolchain into a target project.
set -eu
kit=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$#" -lt 1 ]; then
    echo 'Usage: sh install.sh /path/to/project [adopt options]' >&2
    exit 2
fi
target=$1
shift
exec sh "$kit/scripts/python.sh" --bootstrap "$kit/harness" adopt "$target" --apply "$@"
