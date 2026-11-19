#!/bin/sh
# Per-instance vpnc wrapper for the multi-instance OpenConnect plugin.
#
# Goal on this router: the physical WAN default route must stay put, so mihomo
# fake-ip policy routing is never disturbed.  Each instance has its own tunnel
# device and its own saved WAN gateway file.
#
# TUNDEV is provided by openconnect when it calls this script.  We map it back
# to the instance id via a map file written by run_instances.py.

export INTERNAL_IP4_DNS=

IFACE="${OC_IFACE:-}"

WAN_GW_FILE=""
[ -n "$IFACE" ] && WAN_GW_FILE="/var/run/openconnect_${IFACE}.wan_gw"

restore_wan_default()
{
	[ -n "$WAN_GW_FILE" ] || return 0
	[ -s "$WAN_GW_FILE" ] || return 0
	_wan_gw=$(awk 'NR==1{print $1}' "$WAN_GW_FILE")
	_wan_if=$(awk 'NR==2{print $1}' "$WAN_GW_FILE")
	[ -n "$_wan_gw" ] || return 0
	_cur_gw=$(netstat -rn -f inet | awk '$1 == "default" { print $2; exit }')
	_cur_if=$(netstat -rn -f inet | awk '$1 == "default" { print $NF; exit }')
	if [ "$_cur_gw" != "$_wan_gw" ] || { [ -n "$_wan_if" ] && [ "$_cur_if" != "$_wan_if" ]; }; then
		route delete default >/dev/null 2>&1
		if [ -n "$_wan_if" ]; then
			route add default "$_wan_gw" -ifp "$_wan_if" >/dev/null 2>&1 || \
			    route add default "$_wan_gw" >/dev/null 2>&1
		else
			route add default "$_wan_gw" >/dev/null 2>&1
		fi
	fi
}

/usr/local/sbin/vpnc-script
rc=$?

# FreeBSD group names may not end in a digit, so make pf see the tunnel by
# renaming the kernel-assigned tunN to the configured instance interface name.
if [ "$reason" = "connect" ] && [ -n "$TUNDEV" ] && [ -n "$IFACE" ] && [ "$TUNDEV" != "$IFACE" ]; then
	ifconfig "$TUNDEV" name "$IFACE" 2>/dev/null
fi

case "$reason" in
connect|reconnect|attempt-reconnect|disconnect)
	restore_wan_default
	;;
esac

# On disconnect, destroy our tunnel interface so a later restart can rename a
# fresh tunN back to $IFACE without hitting "File exists".
if [ "$reason" = "disconnect" ] && [ -n "$IFACE" ]; then
	ifconfig "$IFACE" destroy 2>/dev/null
fi

exit $rc
