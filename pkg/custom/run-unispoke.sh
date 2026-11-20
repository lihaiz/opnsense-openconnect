#!/bin/sh
# Thin runner started under daemon(8) for one UniSpoke (Huawei SecoClient/SVN)
# instance.  UniSpoke is a standalone Go client that speaks the Huawei UniVPN
# protocol (Legacy and V1) and creates its own TUN adapter, so it needs no
# vpnc-script.
#
# args: <iface>
# The password is exported via UNISPOKE_PASSWORD so it never appears on the
# process command line.  Server/user/mode/transport/insecure are read from the
# per-instance files written by run_instances.py.
IFACE="$1"
[ -n "$IFACE" ] || exit 1

CONFDIR="/usr/local/etc/openconnect"
SERVER_FILE="$CONFDIR/$IFACE.server"
SECRET_FILE="$CONFDIR/$IFACE.secret"
CONF_FILE="$CONFDIR/$IFACE.conf"

[ -s "$SERVER_FILE" ] || exit 1
[ -s "$SECRET_FILE" ] || exit 1

SERVER=$(cat "$SERVER_FILE")
PASS=$(cat "$SECRET_FILE")
USER=$(grep '^user=' "$CONF_FILE" 2>/dev/null | head -1 | cut -d= -f2-)

[ -n "$SERVER" ] || exit 1
[ -n "$USER" ] || exit 1

export UNISPOKE_PASSWORD="$PASS"

# Safe defaults that work for both Legacy and V1 gateways.
MODE="auto"
TRANSPORT="auto"
INSECURE=""

if [ -s "$CONF_FILE" ]; then
    _m=$(grep '^mode=' "$CONF_FILE" 2>/dev/null | head -1 | cut -d= -f2-)
    case "$_m" in
        legacy|v1) MODE="$_m" ;;
    esac
    _t=$(grep '^transport=' "$CONF_FILE" 2>/dev/null | head -1 | cut -d= -f2-)
    case "$_t" in
        tcp|udp) TRANSPORT="$_t" ;;
    esac
    if grep -q '^insecure=1' "$CONF_FILE" 2>/dev/null; then
        INSECURE="-insecure"
    fi
fi

exec /usr/local/sbin/unispoke \
    -gateway "$SERVER" \
    -user "$USER" \
    -mode "$MODE" \
    -transport "$TRANSPORT" \
    $INSECURE \
    -vpn \
    -vpn-name "$IFACE" \
    -mss 1200 \
    -log-level info \
    -log-format plain
