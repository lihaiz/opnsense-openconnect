#!/bin/sh
# One-shot auto installer for the OpenConnect multi-instance plugin (OPNsense).
# Self-contained: installs pkg deps, copies custom files, prepares config,
# reloads configd/interfaces, then starts the manager.
#
# Usage (as root on an OPNsense box):   sh install.sh
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
CUST="$HERE/custom"
SCRIPTDIR=/usr/local/opnsense/scripts/OPNsense/Openconnect
GUI=/usr/local/opnsense/mvc/app
PY=/usr/local/bin/python3

echo "== 0/5 install dependencies =="
pkg install -y os-openconnect openconnect vpnc-scripts >/dev/null 2>&1 || \
    pkg install -y os-openconnect openconnect vpnc-scripts

echo "== 1/5 copy custom scripts + UniSpoke backend =="
mkdir -p "$SCRIPTDIR"
install -m 0755 "$CUST/run_instances.py" "$SCRIPTDIR/run_instances.py"
install -m 0755 "$CUST/run-instance.sh"  "$SCRIPTDIR/run-instance.sh"
install -m 0755 "$CUST/run-unispoke.sh"  "$SCRIPTDIR/run-unispoke.sh"
install -m 0755 "$CUST/vpnc-instance.sh" "$SCRIPTDIR/vpnc-instance.sh"
install -m 0755 "$CUST/rc.d/opnsense-openconnect" /usr/local/etc/rc.d/opnsense-openconnect
install -m 0644 "$CUST/actions_openconnect.conf"  /usr/local/opnsense/service/conf/actions.d/actions_openconnect.conf
install -m 0755 "$HERE/bin/unispoke" /usr/local/sbin/unispoke

echo "== 2/5 copy GUI overlays + rc.conf.d template =="
mkdir -p /usr/local/etc/inc/plugins.inc.d
install -m 0644 "$CUST/inc/openconnect.inc" /usr/local/etc/inc/plugins.inc.d/openconnect.inc
install -m 0644 "$CUST/gui/instances.volt"     "$GUI/views/OPNsense/Openconnect/instances.volt"
install -m 0644 "$CUST/gui/instances.xml"      "$GUI/controllers/OPNsense/Openconnect/forms/instances.xml"
install -m 0644 "$CUST/gui/dialogInstance.xml" "$GUI/controllers/OPNsense/Openconnect/forms/dialogInstance.xml"
mkdir -p /usr/local/opnsense/service/templates/OPNsense/Openconnect
install -m 0644 "$CUST/templates/openconnect"  /usr/local/opnsense/service/templates/OPNsense/Openconnect/openconnect
install -m 0644 "$CUST/templates/+TARGETS"     /usr/local/opnsense/service/templates/OPNsense/Openconnect/+TARGETS

echo "== 3/5 prepare config (LAN_NET only; add instances in GUI) =="
"$PY" "$HERE/apply_config.py"

echo "== 4/5 reload configd + interfaces (GUI + interface) =="
configctl configd restart >/dev/null 2>&1 || true
configctl interface reconfigure >/dev/null 2>&1 || true

echo "== 5/5 start manager =="
if [ ! -f "$SCRIPTDIR/run_instances.py" ]; then
    echo "ERROR: manager was not installed at $SCRIPTDIR/run_instances.py" >&2
    exit 1
fi
"$PY" "$SCRIPTDIR/run_instances.py" start
sleep 8
"$PY" "$SCRIPTDIR/run_instances.py" status

echo
echo "Done. GUI: Services -> OpenConnect -> add an instance."
echo "Source NAT follows the routes each VPN server pushes (no hardcoded subnet)."
