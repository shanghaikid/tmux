# OSC 7501 per-pane status

This branch implements Program Status Protocol revision 0.4, including feature
queries, atomic bounded reports, hierarchy, clearing, inherited app identity,
record replacement and LRU eviction (64 records per pane). It uses the exact
same Rust record engine as our Alacritty fork, linked into the executable.
There is no helper process, notification command or periodic polling.

## Build

On macOS: `brew install rust git autoconf automake pkg-config libevent ncurses utf8proc`.
On other Unix systems install the equivalent development packages. Build:

```sh
git clone --branch osc7501 https://github.com/shanghaikid/tmux.git
cd tmux
contrib/program-status/build.sh
install -m 755 tmux "$HOME/.local/bin/tmux"
```

The script fetches a pinned source revision of the shared engine into `.build`,
uses its committed Cargo.lock and builds a native static archive. A sibling
Alacritty checkout is unnecessary. Set `PREFIX` or pass configure options to
change the install location. This fork currently requires Rust 1.85 or newer.
Use a toolchain compatible with the target macOS version when cross-building.

Add `#{pane_program_status}` to `window-status-format`,
`window-status-current-format` or `pane-border-format`. Our dotfiles include
it beside the existing directory/branch label. Only fixed state/kind/progress
is displayed, for example `[working 42%]` or `[permission]`. Application text
cannot become tmux formatting. Other pane metadata continues to identify the
source pane. The shared engine stores and validates the complete report.

Reports are independent of the screen. RIS clears them; DECSTR and alternate
screen switches preserve them. OSC 133 A and attached-process exit expire
working/blocked/idle, retaining done/error. Display updates use at most one
100 ms one-shot timer per pane, including when a pane emits a report storm.
All buffers receiving a 7501 body are bounded before allocation; an unterminated
oversized report cannot grow `input_buf` or `since_ground`. Invalid, cancelled
or incomplete reports do not partially mutate records. Other OSCs are unchanged.

Capability replies contain constant bytes only. They never include stored
record content. There is no terminal-protocol record readback.

## Existing servers

Replacing tmux does not update an existing server process. Existing sessions
remain running on their current binary. To try this build without interrupting
them, use a new socket:

```sh
tmux -L osc7501 new-session -A -s alacritty
```

The default socket uses the new binary after the old server's sessions finish.
Do not kill an active server just to update the executable.

## Acceptance

`python3 contrib/program-status/acceptance.py` creates its own temporary socket
and pane and only tears down that server. Protocol boundaries and record
semantics are tested in the shared engine and Alacritty parser/terminal tests.
