#!/usr/local/bin/python3
"""Merge the OpenConnect multi-instance config snippets into /conf/config.xml.

Idempotent. This is the GENERIC installer: it does NOT write any VPN instance,
server, user, password, tunnel interface or remote subnet. Instances are added
and edited in the GUI (Services -> OpenConnect), and the runtime manager
(run_instances.py) derives Source NAT automatically from the routes each VPN
server actually pushes. The LAN source subnet is auto-detected too.
"""
import sys, os, time, shutil
import xml.etree.ElementTree as ET

CONFIG = '/conf/config.xml'
MODEL = '/usr/local/opnsense/mvc/app/models/OPNsense/Openconnect/General.xml'

# Extra protocol backends not present in the stock os-openconnect model.
# UniSpoke (Huawei SecoClient/SVN, Legacy + V1) is added as 'secoclient'.
EXTRA_PROTOCOLS = (
    ('secoclient', 'Huawei SecoClient (UniSpoke)'),
)

# LAN subnet is auto-detected by run_instances.py (_lan_net) from the
# <interfaces>/<lan> entry in config.xml. No override is needed here.

def find_or_create(parent, tag):
    node = parent.find(tag)
    if node is None:
        node = ET.SubElement(parent, tag)
    return node

# Extra per-instance OptionFields for the secoclient backend (UniSpoke).
# UniSpoke auto-detects both, so these default to 'auto'; they exist only to
# let an operator force a specific mode/transport when auto-detection misjudges
# a gateway.  The field/option names mirror UniSpoke's CLI flags.
SECOCLIENT_FIELDS = (
    ('mode', 'Gateway mode', (('auto', 'Auto-detect'), ('legacy', 'Legacy'), ('v1', 'V1'))),
    ('transport', 'Data transport', (('auto', 'Auto-detect'), ('udp', 'UDP'), ('tcp', 'TCP/TLS'))),
)


def _option_field(name, label, choices):
    el = ET.Element(name, type='OptionField')
    req = ET.SubElement(el, 'Required')
    req.text = 'N'
    dflt = ET.SubElement(el, 'Default')
    dflt.text = 'auto'
    ov = ET.SubElement(el, 'OptionValues')
    for value, text in choices:
        o = ET.SubElement(ov, value)
        o.text = text
    return el


def patch_model():
    """Add the secoclient protocol option and its per-instance mode/transport
    OptionFields to the stock model.  Idempotent: only inserts what is missing.
    """
    if not os.path.exists(MODEL):
        return False
    tree = ET.parse(MODEL)
    root = tree.getroot()
    changed = False

    # 1) protocol dropdown: drop the stock Huawei UniVPN (experimental) option
    #    (it only speaks the Huawei V1 dialect and is replaced by UniSpoke), and
    #    add the secoclient backend.
    for opt in root.iter('protocol'):
        ov = opt.find('OptionValues')
        if ov is None:
            continue
        for e in list(ov):
            if (e.tag or '') == 'univpn':
                ov.remove(e)
                changed = True
        existing = set((e.tag or '') for e in ov)
        for value, label in EXTRA_PROTOCOLS:
            if value not in existing:
                el = ET.SubElement(ov, value)
                el.text = label
                changed = True

    # 2) instance-level mode/transport OptionFields for UniSpoke
    inst = None
    for e in root.iter('instance'):
        inst = e
        break
    if inst is not None:
        existing = set(e.tag for e in inst)
        for name, label, choices in SECOCLIENT_FIELDS:
            if name not in existing:
                inst.append(_option_field(name, label, choices))
                changed = True

    if changed:
        tree.write(MODEL, encoding='utf-8', xml_declaration=True)
    return changed


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

    if patch_model():
        print('patched model General.xml with extra protocol backends')
    return 0

if __name__ == '__main__':
    sys.exit(main())
