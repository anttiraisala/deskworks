#!/bin/bash
# Run a real GNOME Shell with no screen (a virtual monitor) so that the GNOME Shell extension and a
# Wayland client can be tried in a container. Tested with GNOME Shell 46 on Ubuntu 24.04.
#
#   apt-get install -y --no-install-recommends gnome-shell mutter dbus-x11 libglib2.0-bin \
#       python3-dbusmock python3-dbus foot
#   scripts/gnome-headless.sh start [WxH]     # prints the environment file to source
#   . /tmp/gnome-headless/env
#   scripts/gnome-headless.sh install-extension   # copies and enables cascade-windows' extension, restarts the shell
#   foot --app-id=tp1 sleep 600 &              # a Wayland window to move
#   scripts/gnome-headless.sh stop
#
# Needs: a system bus with a fake org.freedesktop.login1 (python3-dbusmock; the shell refuses to start without
# logind), and a private session bus. Python 3.12 is used for dbusmock because the system python3 may not match
# the python3-dbus package.
set -u
D=/tmp/gnome-headless
ROOT=$(cd "$(dirname "$0")/.." && pwd)
UUID=cascade-windows@anttiraisala.github.io
mkdir -p "$D/run" "$D/home"; chmod 700 "$D/run"
cat > "$D/env" <<ENV
export XDG_RUNTIME_DIR=$D/run XDG_SESSION_TYPE=wayland HOME=$D/home GSETTINGS_BACKEND=dconf
export DBUS_SESSION_BUS_ADDRESS=unix:path=$D/run/bus WAYLAND_DISPLAY=wayland-0
ENV
. "$D/env"

start_shell() {
    pkill -x gnome-shell; sleep 1
    nohup gnome-shell --headless --wayland --no-x11 --virtual-monitor "${1:-1280x720}" > "$D/shell.log" 2>&1 &
    sleep 8
}

case "${1:-}" in
start)
    mkdir -p /run/dbus
    pgrep -f "dbus-daemon --system" >/dev/null || dbus-daemon --system --fork
    pgrep -f "dbusmock --system" >/dev/null || { /usr/bin/python3.12 -m dbusmock --system --template logind > "$D/mock.log" 2>&1 & sleep 3; }
    [ -S "$D/run/bus" ] || dbus-daemon --session --fork --address="$DBUS_SESSION_BUS_ADDRESS"
    start_shell "${2:-}"
    echo "source $D/env"
    ;;
install-extension)
    T=$HOME/.local/share/gnome-shell/extensions/$UUID
    mkdir -p "$T"
    cp -r "$ROOT/cascade-windows/gnome-extension/"{extension.js,metadata.json,lib,icons,schemas} "$T/"
    glib-compile-schemas "$T/schemas"
    gsettings set org.gnome.shell disable-user-extensions false
    gsettings set org.gnome.shell enabled-extensions "['$UUID']"
    start_shell    # extensions are found when the shell starts
    busctl --user list | grep CascadeWindows || { echo "extension did not start; see $D/shell.log"; exit 1; }
    ;;
stop)
    pkill -x gnome-shell
    ;;
*)
    echo "usage: $0 start [WxH] | install-extension | stop"; exit 2;;
esac
