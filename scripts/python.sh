#!/bin/sh
# Bootstrap only on installation; ordinary commands reuse the prepared runtime.
set -eu
bootstrap=no
if [ "${1:-}" = --bootstrap ]; then bootstrap=yes; shift; fi
if [ "${2:-}" = adopt ]; then
    for arg in "$@"; do [ "$arg" != --apply ] || bootstrap=yes; done
fi
runtime=${HARNESS_RUNTIME_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/harness/runtime}
export HARNESS_RUNTIME_DIR="$runtime"
PATH="$runtime/bin:$runtime/node/bin:$PATH"
export PATH
if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys;sys.exit(sys.version_info < (3,11))' 2>/dev/null; then
    exec python3 "$@"
fi
if [ "$bootstrap" != yes ]; then
    echo 'Python 3.11+ is missing. Run sh install.sh /path/to/project to prepare it automatically.' >&2
    exit 1
fi
case "$(uname -s)" in Darwin|Linux) ;; *) echo 'Use macOS, Linux or WSL.' >&2; exit 1;; esac
mkdir -p "$runtime/bin"
if ! command -v uv >/dev/null 2>&1; then
    download=$(mktemp)
    trap 'rm -f "$download"' EXIT HUP INT TERM
    if command -v curl >/dev/null 2>&1; then
        curl --fail --location --proto '=https' --proto-redir '=https' --connect-timeout 15 --max-time 180 https://astral.sh/uv/install.sh -o "$download"
    elif command -v wget >/dev/null 2>&1; then
        wget --https-only --timeout=30 -O "$download" https://astral.sh/uv/install.sh
    else
        echo 'A system HTTPS downloader (curl or wget) is required to bootstrap Python.' >&2
        exit 1
    fi
    UV_UNMANAGED_INSTALL="$runtime/bin" sh "$download" >&2
    rm -f "$download"
    trap - EXIT HUP INT TERM
fi
export UV_PYTHON_INSTALL_DIR="$runtime/python"
export UV_PYTHON_BIN_DIR="$runtime/bin"
export UV_CACHE_DIR="$runtime/uv-cache"
uv python install 3.12 >&2
python_path=$(uv python find --managed-python 3.12)
ln -sf "$python_path" "$runtime/bin/python3"
exec "$runtime/bin/python3" "$@"
