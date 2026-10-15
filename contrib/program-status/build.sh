#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$repo"
# Pin the shared validator; no dependency on a neighbouring source checkout.
engine_rev=4ab9231c28a2f47525145642169eff36734c0887
engine="$repo/.build/program-status-source"
if [ ! -d "$engine/.git" ]; then
    mkdir -p "$repo/.build"
    git clone --branch macos-ime-fix --depth 1 https://github.com/shanghaikid/alacritty.git "$engine"
fi
if ! git -C "$engine" diff-index --quiet HEAD -- 2>/dev/null; then
    printf '%s\n' "Engine source has local edits: $engine" >&2
    exit 1
fi
git -C "$engine" fetch --depth 1 origin "$engine_rev"
git -C "$engine" checkout --detach "$engine_rev"
cargo build --locked --release -p alacritty_status --no-default-features --manifest-path "$engine/Cargo.toml"
archive="$engine/target/release/libalacritty_status.a"
extra_libs='-ldl -lpthread -lm'
if [ "$(uname -s)" = Darwin ]; then
    extra_libs='-framework Security -framework SystemConfiguration -liconv'
    if command -v brew >/dev/null 2>&1; then
        brew_prefix=$(brew --prefix)
        CPPFLAGS="${CPPFLAGS:-} -I$brew_prefix/opt/libevent/include -I$brew_prefix/opt/ncurses/include"
        LDFLAGS="${LDFLAGS:-} -L$brew_prefix/opt/libevent/lib -L$brew_prefix/opt/ncurses/lib"
        export CPPFLAGS LDFLAGS
    fi
fi
sh autogen.sh
./configure --prefix="${PREFIX:-$HOME/.local}" "LIBS=$archive $extra_libs ${LIBS:-}" "$@"
# Configure flags and the pinned archive can change without source mtimes.
make clean
make -j "${JOBS:-$(getconf _NPROCESSORS_ONLN)}"
printf '%s\n' 'Built tmux with OSC 7501. Install the executable into ~/.local/bin when ready.'
