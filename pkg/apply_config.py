#!/usr/local/bin/python3
"""Merge the OpenConnect multi-instance config snippets into /conf/config.xml.

Idempotent. This is the GENERIC installer: it does NOT write any VPN instance,
server, user, password, tunnel interface or remote subnet. Instances are added
and edited in the GUI (Services -> OpenConnect), and the runtime manager
(run_instances.py) derives Source NAT automatically from the routes each VPN
server actually pushes. The LAN source subnet is auto-detected too.
"""
import sys, time, shutil
import xml.etree.ElementTree as ET

CONFIG = '/conf/config.xml'

# LAN subnet is auto-detected by run_instances.py (_lan_net) from the
# <interfaces>/<lan> entry in config.xml. No override is needed here.

def find_or_create(parent, tag):
    node = parent.find(tag)
    if node is None:
        node = ET.SubElement(parent, tag)
    return node

def main():
    ts = time.strftime('%Y%m%d-%H%M%S')
    shutil.copy2(CONFIG, CONFIG + '.bak-pkg-' + ts)
    print('backed up config.xml ->', CONFIG + '.bak-pkg-' + ts)

    tree = ET.parse(CONFIG)
    root = tree.getroot()

    # Ensure the plugin config tree exists (empty; GUI manages instances).
    opnsense = find_or_create(root, 'OPNsense')
    oc = find_or_create(opnsense, 'openconnect')
    find_or_create(oc, 'instances')
    oc.set('version', '1.1.0')

    # Remove any legacy outbound NAT rules bound to our tunnel interfaces so
    # they can never trigger the Migration assistant. Runtime Source NAT is
    # managed dynamically by run_instances.py (snatrules), not here.
    nat = root.find('nat')
    if nat is not None:
        outbound = nat.find('outbound')
        if outbound is not None:
            for old in list(outbound.findall('rule')):
                it = old.find('interface')
                iface = (it.text or '').strip() if it is not None else ''
                if iface.startswith('ocvpn'):
                    outbound.remove(old)

    tree.write(CONFIG, encoding='utf-8', xml_declaration=True)
    print('config.xml prepared. Add instances in the GUI; LAN net is auto-detected.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
