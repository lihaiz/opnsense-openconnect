#!/bin/sh
# Thin runner started under daemon(8) for one OpenConnect instance.
# args: <iface>
# Re-opens the secret file on every (re)start so a crash-restart gets a fresh
# password on stdin.
IFACE="$1"
[ -n "$IFACE" ] || exit 1
CONF="/usr/local/etc/openconnect/${IFACE}.conf"
SECRET="/usr/local/etc/openconnect/${IFACE}.secret"
SERVER_FILE="/usr/local/etc/openconnect/${IFACE}.server"
[ -s "$SERVER_FILE" ] || exit 1
SERVER=$(cat "$SERVER_FILE")
export OC_IFACE="$IFACE"
exec /usr/local/sbin/openconnect \
    --script=/usr/local/opnsense/scripts/OPNsense/Openconnect/vpnc-instance.sh \
    --config="${CONF}" "https://${SERVER}" < "${SECRET}"
