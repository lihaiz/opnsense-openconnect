#!/usr/local/bin/python3
"""Multi-instance OpenConnect manager for OPNsense.

Enumerates the enabled instances from config.xml and manages one openconnect
client per instance: its own conf/secret, tunnel device, ocvpn group member,
pidfile, log and saved WAN default route.  Each instance keeps the physical
WAN default route intact (see vpnc-instance.sh).

Usage: run_instances.py (start|stop|restart|status)
"""
import os
import re
import glob
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

CONFDIR = '/usr/local/etc/openconnect'
RUNNER = '/usr/local/opnsense/scripts/OPNsense/Openconnect/run-instance.sh'
VPNC = '/usr/local/opnsense/scripts/OPNsense/Openconnect/vpnc-instance.sh'
BIN = '/usr/local/sbin/openconnect'
UNISPOKE_BIN = '/usr/local/sbin/unispoke'
UNISPOKE_RUNNER = '/usr/local/opnsense/scripts/OPNsense/Openconnect/run-unispoke.sh'
TUN_BASE = 30000
CONFIG_XML = '/conf/config.xml'
def _lan_net():
    '''Derive the LAN source subnet for Source NAT from config.xml.
    Looks for the <lan> interface (and any other physical, non-tunnel
    IPv4 interface) and returns the first CIDR it finds. Returns None when
    no local network can be detected; NAT reconciliation is then skipped.
    '''
    nets = []
    if os.path.exists(CONFIG_XML):
        try:
            root = ET.parse(CONFIG_XML).getroot()
            iface_el = root.find('interfaces')
            if iface_el is not None:
                for node in iface_el:
                    ip = node.find('ipaddr')
                    sn = node.find('subnet')
                    if ip is None or sn is None:
                        continue
                    ip = (ip.text or '').strip()
                    sn = (sn.text or '').strip()
                    if not ip or not sn or not sn.isdigit():
                        continue
                    typ = node.find('type')
                    typ = (typ.text or '').strip() if typ is not None else ''
                    ifname = node.tag
                    if typ in ('none', 'group') or ifname == 'lo0':
                        continue
                    try:
                        nets.append((ifname, ip, int(sn)))
                    except ValueError:
                        continue
        except Exception:
            pass

    def _cidr(ip, sn):
        import ipaddress
        try:
            return str(ipaddress.ip_network('%s/%d' % (ip, sn), strict=False))
        except Exception:
            return None

    for ifname, ip, sn in nets:
        if ifname == 'lan':
            c = _cidr(ip, sn)
            if c:
                return c
    for ifname, ip, sn in nets:
        c = _cidr(ip, sn)
        if c:
            return c
    return None





def _routed_nets(iface):
    '''Return the remote subnets currently routed through <iface>, parsed from
    the live IPv4 routing table.  These are the split-tunnel routes the VPN
    server pushed and vpnc-script installed on connect.'''
    nets = set()
    try:
        out = subprocess.run('netstat -rn -f inet', shell=True,
                             capture_output=True, text=True).stdout
    except OSError:
        return nets
    for line in out.splitlines():
        parts = line.split()
        # destination  gateway  flags  netif
        if len(parts) >= 4 and parts[-1] == iface and '/' in parts[0]:
            nets.add(parts[0])
    return nets


def nat_desc(iface):
    # Keep the description unique per tunnel interface: sync_nat() uses
    # it as a fallback match key, so a shared constant across instances
    # could bind a rule to the wrong tunnel.
    return 'LAN to remote via OpenConnect tunnel %s MASQ' % iface


def wait_for_routes(targets, timeout=25):
    '''Poll the routing table until every tunnel in <targets> either has at
    least one pushed route or <timeout> seconds elapse.  Replaces a blind
    fixed sleep so NAT is written against a settled (or definitively empty)
    route table, which makes slow-connecting servers reliable and fast ones
    return immediately.'''
    deadline = time.time() + timeout
    pending = set(targets)
    while pending and time.time() < deadline:
        done = set(i for i in pending if _routed_nets(i))
        pending -= done
        if pending:
            time.sleep(2)


def sync_nat(instances):
    """Reconcile the Source NAT rule for each OpenConnect instance with its
    enabled state.  Returns True if config.xml was modified.

    Only the new Source NAT schema (OPNsense.Firewall.Filter.snatrules) is
    touched; legacy <nat><outbound><rule> entries for our interfaces are
    removed so they can never trigger the Migration assistant again.
    """
    if not os.path.exists(CONFIG_XML):
        return False
    root = ET.parse(CONFIG_XML).getroot()
    changed = False

    def ensure(parent, tag):
        node = parent.find(tag)
        if node is None:
            node = ET.SubElement(parent, tag)
        return node

    def set_text(node, tag, value):
        c = node.find(tag)
        if c is None:
            c = ET.SubElement(node, tag)
        if (c.text or '') != value:
            c.text = value
            return True
        return False

    # remove legacy outbound rules bound to any of our tunnel interfaces
    nat = root.find('nat')
    if nat is not None:
        outbound = nat.find('outbound')
        if outbound is not None:
            ifaces = set(inst['iface'] for inst in instances)
            for old in list(outbound.findall('rule')):
                it = old.find('interface')
                iface = (it.text or '').strip() if it is not None else ''
                if iface in ifaces:
                    outbound.remove(old)
                    changed = True

    fw = ensure(ensure(ensure(root, 'OPNsense'), 'Firewall'), 'Filter')
    snat = ensure(fw, 'snatrules')

    routed = {}
    for inst in instances:
        if not inst['enabled'] or not inst['server'] or not inst['user']:
            continue
        nets = _routed_nets(inst['iface'])
        if nets:
            routed[inst['iface']] = nets
    lan_net = _lan_net()

    # Without a detectable local source network there is no safe source-net
    # to use; skip creating rules, while cleanup below still removes stale ones.
    if lan_net is None:
        routed = {}

    desired = set(routed)
    for iface in sorted(routed):
        # find existing rule by interface, else by our description
        rule = None
        for r in snat.findall('rule'):
            it = r.find('interface')
            riface = (it.text or '').strip() if it is not None else ''
            if riface == iface:
                rule = r
                break
        if rule is None:
            for r in snat.findall('rule'):
                d = r.find('description')
                if d is not None and (d.text or '') == nat_desc(iface):
                    rule = r
                    break
        if rule is None:
            rule = ET.SubElement(snat, 'rule')
            rule.set('uuid', 'ocvpn-%s' % iface)
            ET.SubElement(rule, 'enabled')
            ET.SubElement(rule, 'nonat')
            ET.SubElement(rule, 'nosync')
            ET.SubElement(rule, 'sequence')
            ET.SubElement(rule, 'interface')
            ET.SubElement(rule, 'ipprotocol')
            ET.SubElement(rule, 'protocol')
            ET.SubElement(rule, 'source_net')
            ET.SubElement(rule, 'source_not')
            ET.SubElement(rule, 'source_port')
            ET.SubElement(rule, 'destination_net')
            ET.SubElement(rule, 'destination_not')
            ET.SubElement(rule, 'destination_port')
            ET.SubElement(rule, 'target')
            ET.SubElement(rule, 'target_port')
            ET.SubElement(rule, 'poolopts')
            ET.SubElement(rule, 'poolopts_sourcehashkey')
            ET.SubElement(rule, 'staticnatport')
            ET.SubElement(rule, 'log')
            ET.SubElement(rule, 'categories')
            ET.SubElement(rule, 'tag')
            ET.SubElement(rule, 'tagged')
            ET.SubElement(rule, 'endpoint-independent')
            ET.SubElement(rule, 'description')
            ET.SubElement(rule, 'audit')
            changed = True
        if set_text(rule, 'enabled', '1'): changed = True
        if set_text(rule, 'nonat', '0'): changed = True
        if set_text(rule, 'nosync', '0'): changed = True
        if set_text(rule, 'sequence', '1'): changed = True
        if set_text(rule, 'interface', iface): changed = True
        if set_text(rule, 'ipprotocol', 'inet'): changed = True
        if set_text(rule, 'protocol', 'any'): changed = True
        if set_text(rule, 'source_net', lan_net): changed = True
        if set_text(rule, 'source_not', '0'): changed = True
        if set_text(rule, 'destination_net', ','.join(sorted(routed[iface]))): changed = True
        if set_text(rule, 'destination_not', '0'): changed = True
        if set_text(rule, 'staticnatport', '0'): changed = True
        if set_text(rule, 'log', '0'): changed = True
        if set_text(rule, 'endpoint-independent', '0'): changed = True
        if set_text(rule, 'description', nat_desc(iface)): changed = True

    # remove any Source NAT rule bound to our tunnel interfaces that is no
    # longer wanted (instance disabled, missing server/user, or deleted).
    known = set(inst['iface'] for inst in instances)
    for r in list(snat.findall('rule')):
        it = r.find('interface')
        iface = (it.text or '').strip() if it is not None else ''
        if iface and iface not in desired and (iface in known or iface.startswith('ocvpn')):
            snat.remove(r)
            changed = True

    if changed:
        tree = ET.ElementTree(root)
        tree.write(CONFIG_XML, encoding='utf-8', xml_declaration=True)
    return changed

def text(node, tag):
    c = node.find(tag)
    return (c.text or '').strip() if c is not None else ''


def load_instances():
    """Return list of dicts for every <instance> under OPNsense/openconnect."""
    if not os.path.exists(CONFIG_XML):
        return []
    root = ET.parse(CONFIG_XML).getroot()
    oc = root.find('OPNsense/openconnect/instances')
    out = []
    idx = 0
    if oc is None:
        return out
    for inst in oc.findall('instance'):
        iface = text(inst, 'interface')
        if not iface:
            iface = 'ocvpn%d' % (idx + 1)
        tun = 'tun%d' % (TUN_BASE + idx)
        out.append({
            'uuid': inst.get('uuid') or ('%02d' % idx),
            'enabled': text(inst, 'enabled') == '1',
            'name': text(inst, 'name') or iface,
            'server': text(inst, 'server'),
            'user': text(inst, 'user'),
            'password': text(inst, 'password'),
            'servercert': text(inst, 'servercert'),
            'hash': text(inst, 'hash') or 'sha256',
            'group': text(inst, 'group'),
            'clientcertificate': text(inst, 'clientcertificate'),
            'tokenmode': text(inst, 'tokenmode'),
            'tokensecret': text(inst, 'tokensecret'),
            'allowinsecure': text(inst, 'allowinsecure') == '1',
            'mode': text(inst, 'mode'),
            'transport': text(inst, 'transport'),
            'protocol': text(inst, 'protocol') or 'anyconnect',
            'iface': iface,
            'tun': tun,
        })
        idx += 1
    return out


def render_conf(inst):
    lines = ['user=%s' % inst['user']] if inst['user'] else []
    lines += ['quiet', 'syslog', 'no-dtls',
              'non-inter', 'passwd-on-stdin']
    if inst['servercert']:
        lines.append('servercert=%s:%s' % (inst['hash'], inst['servercert']))
    # AnyConnect servers that offer a group selection need an explicit answer
    # in non-interactive mode.  The upstream single-instance plugin's default
    # was "all", so keep that behaviour unless the user configured a group.
    # (Huawei gateways are handled by the UniSpoke backend, not openconnect.)
    lines.append('authgroup=%s' % (inst['group'] or 'all'))
    if inst['clientcertificate']:
        lines.append('certificate=%s/%s_cert.pem' % (CONFDIR, inst['iface']))
        lines.append('sslkey=%s/%s_key.pem' % (CONFDIR, inst['iface']))
    if inst['tokenmode'] and inst['tokensecret']:
        lines.append('token-mode=%s' % inst['tokenmode'])
        lines.append('token-secret=%s' % inst['tokensecret'])
    if inst['allowinsecure']:
        lines.append('allow-insecure-crypto')
    if inst['protocol']:
        lines.append('protocol=%s' % inst['protocol'])
        if inst['protocol'] == 'anyconnect':
            lines.append('useragent=AnyConnect')
    return '\n'.join(lines) + '\n'



def render_unispoke_conf(inst):
    # UniSpoke is a standalone binary: only user plus optional mode/transport/
    # insecure flags are meaningful.  The password is passed via a .secret file
    # and UNISPOKE_PASSWORD env var, never on the command line.
    lines = ['user=%s' % inst['user']] if inst['user'] else []
    if inst.get('mode'):
        lines.append('mode=%s' % inst['mode'])
    if inst.get('transport'):
        lines.append('transport=%s' % inst['transport'])
    if inst['allowinsecure']:
        lines.append('insecure=1')
    return '\n'.join(lines) + '\n'

def write_instance_files(inst):
    os.makedirs(CONFDIR, exist_ok=True)
    conf = os.path.join(CONFDIR, '%s.conf' % inst['iface'])
    secret = os.path.join(CONFDIR, '%s.secret' % inst['iface'])
    server = os.path.join(CONFDIR, '%s.server' % inst['iface'])
    with open(conf, 'w') as f:
        f.write(render_unispoke_conf(inst) if is_unispoke(inst) else render_conf(inst))
    with open(secret, 'w') as f:
        f.write(inst['password'] + '\n')
    with open(server, 'w') as f:
        f.write(inst['server'] + '\n')
    os.chmod(secret, 0o600)
    os.chmod(server, 0o600)
    return conf, secret, server


def sh(cmd):
    return subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL)


def wan_default():
    out = subprocess.run('netstat -rn -f inet', shell=True,
                         capture_output=True, text=True).stdout
    gw = iface = ''
    for line in out.splitlines():
        parts = line.split()
        if parts and parts[0] == 'default' and len(parts) >= 4:
            if not parts[-1].startswith('tun'):
                gw = parts[1]
                iface = parts[-1]
                break
    return gw, iface



def is_unispoke(inst):
    return inst['protocol'] == 'secoclient'


def register_interfaces():
    """Register dynamic tunnel interfaces into config.xml <interfaces>.

    pf's interface mapping is built from config.xml <interfaces>; the
    openconnect_interfaces() plugin hook only populates that section when
    plugins_interfaces() runs (pluginctl -i / write_config).  Without this the
    Source NAT rules on ocvpn* are dropped with "Interface ... not found".
    Called directly (not through configctl) to avoid deadlocking configd, since
    this manager can be invoked from inside a configd action.
    """
    subprocess.run('/usr/local/sbin/pluginctl -i',
                   shell=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)


def reload_filter():
    """Reload pf so Source NAT enable/disable changes take effect.

    Register the dynamic tunnel interfaces first (see register_interfaces),
    then reload the filter.  Called directly (not through configctl) to avoid
    deadlocking configd, since this manager can be invoked from inside a
    configd action.
    """
    register_interfaces()
    subprocess.run('/usr/local/etc/rc.filter_configure skip_alias',
                   shell=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)


def ensure_tun(inst):
    # Destroy any stale interface holding our target name (leftover from a
    # previous run that renamed tunN -> <iface>). Otherwise the later rename
    # fails with "File exists" and NAT/routing break after a manual stop/start.
    # The actual tun device is allocated by openconnect itself (no interface=
    # in the config), then renamed to <iface> by vpnc-instance.sh.
    sh('ifconfig %s destroy >/dev/null 2>&1' % inst['iface'])
    # Also destroy the boot-time dummy tun30000 shell that the legacy
    # single-instance rc created at startup (renamed to ocvpn0 in old
    # setups, now left as an empty no-IP shell). openconnect allocates
    # its own tunN, so this stale shell is pure noise; killing it here
    # keeps ifconfig clean after every start.
    if inst.get('tun'):
        sh('ifconfig %s destroy >/dev/null 2>&1' % inst['tun'])


def cleanup_legacy():
    # The single-instance version of this plugin used run.sh + openconnect.conf
    # and created a boot-time dummy tun30000 -> renamed ocvpn0 (with
    # `group ocvpn`).  That script is gone now; any leftover daemon/iface is a
    # no-IP empty shell.  Reconcile it away on every start so ifconfig stays
    # clean across reboots.
    sh("pkill -9 -f 'daemon.*Openconnect/run.sh' >/dev/null 2>&1")
    sh("pkill -9 -f '%s .*/openconnect.conf' >/dev/null 2>&1" % BIN)
    sh('ifconfig ocvpn0 destroy >/dev/null 2>&1')
    sh('ifconfig tun30000 destroy >/dev/null 2>&1')
    for f in ('/var/run/openconnect.log', '/usr/local/etc/openconnect.conf',
              '/dev/ocvpn0'):
        try:
            os.remove(f)
        except OSError:
            pass


def pidfile(inst):
    return '/var/run/openconnect.%s.pid' % inst['iface']


def logfile(inst):
    return '/var/run/openconnect.%s.log' % inst['iface']


def running(inst):
    pf = pidfile(inst)
    if not os.path.exists(pf):
        return None
    try:
        pid = int(open(pf).read().strip())
    except Exception:
        return None
    try:
        os.kill(pid, 0)
        return pid
    except OSError:
        return None


def running_pids(instances):
    """Return [(instance, pid), ...] for every live OpenConnect instance."""
    return [(inst, pid) for inst in instances for pid in [running(inst)] if pid]


def sync_service_pidfile(instances):
    """Keep the aggregate pidfile consumed by OPNsense's Services widget.

    The core checker expects a concrete file and uses pgrep -nF, so it cannot
    consume per-instance wildcard pidfiles. Write all live child PIDs (one per
    line), or remove the file when all instances are down. The widget then
    means one or more instances are running, without core OPNsense changes.
    """
    path = '/var/run/openconnect.pid'
    pids = [pid for _inst, pid in running_pids(instances)]
    try:
        if pids:
            with open(path, 'w') as f:
                f.write(''.join('%d\n' % pid for pid in pids))
        elif os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def stop_instance(inst):
    pf = pidfile(inst)
    pid = running(inst)
    # daemon(8) -r would respawn the child, so kill the supervisor first.
    # The pidfile holds the child pid; the daemon master is its parent.
    if pid:
        try:
            out = subprocess.run('ps -o ppid= -p %d' % pid, shell=True,
                                 capture_output=True, text=True).stdout
            ppid = int(out.strip().split()[0])
            if ppid > 1:
                sh('kill -TERM %d' % ppid)
        except Exception:
            pass
        sh('kill -TERM %d' % pid)
        for _ in range(15):
            try:
                os.kill(pid, 0)
                time.sleep(1)
            except OSError:
                break
        sh('kill -KILL %d' % pid)
    # fallback: match the full child command line (contains <iface>.conf)
    sh("pkill -f '%s .*%s.conf'" % (BIN, inst['iface']))
    # UniSpoke child runs as `unispoke ... -vpn-name <iface> ...`
    if is_unispoke(inst):
        sh("pkill -f '%s .*-vpn-name %s'" % (UNISPOKE_BIN, inst['iface']))
        sh("pkill -f '%s .*-vpn-name=%s'" % (UNISPOKE_BIN, inst['iface']))
        sh("ifconfig %s destroy >/dev/null 2>&1" % inst['iface'])
    # kill any leftover daemon wrappers for this instance (stale from reloads)
    sh("pkill -f 'daemon.*run-instance.sh.*%s'" % inst['iface'])
    sh("pkill -f 'daemon.*run-unispoke.sh.*%s'" % inst['iface'])
    sh("pkill -f '%s .*%s.conf'" % (BIN, inst['iface']))
    if os.path.exists(pf):
        os.remove(pf)
    # keep physical WAN default if this instance stole it
    gw_file = '/var/run/openconnect_%s.wan_gw' % inst['iface']
    if os.path.exists(gw_file):
        gw = wan_default()[0]
        saved = open(gw_file).read().split('\n')
        want = saved[0] if saved else ''
        if want and gw != want:
            sh('route delete default >/dev/null 2>&1')
            sh('route add default %s >/dev/null 2>&1' % want)


def start_instance(inst):
    write_instance_files(inst)
    ensure_tun(inst)
    gw, gwi = wan_default()
    gw_file = '/var/run/openconnect_%s.wan_gw' % inst['iface']
    with open(gw_file, 'w') as f:
        f.write('%s\n%s\n' % (gw, gwi))
    if os.path.exists(logfile(inst)):
        os.remove(logfile(inst))
    runner = UNISPOKE_RUNNER if is_unispoke(inst) else RUNNER
    cmd = "daemon -r -R 30 -p %s -o %s %s %s" % (
        pidfile(inst), logfile(inst), runner, inst['iface'])
    sh(cmd)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('start', 'stop', 'restart',
                                                 'status', 'sync'):
        print('usage: run_instances.py (start|stop|restart|status)')
        return 1
    action = sys.argv[1]
    instances = load_instances()
    cleanup_legacy()

    # Tear down first for stop/restart so the post-action NAT reconcile sees the
    # real (post-connect) routing table instead of a stale one.
    if action in ('stop', 'restart'):
        for inst in instances:
            stop_instance(inst)

    if action in ('start', 'restart'):
        started = 0
        for inst in instances:
            if not inst['enabled']:
                continue
            if not inst['server'] or not inst['user']:
                continue
            if running(inst):
                stop_instance(inst)
            start_instance(inst)
            started += 1
        wait_for_routes([i['iface'] for i in instances if i['enabled']
                       and i['server'] and i['user']])
        sync_service_pidfile(instances)
        print('%d instance(s) started' % started)

    if action == 'sync':
        started = 0
        active_ifaces = set()
        for inst in instances:
            active_ifaces.add(inst['iface'])
            conf_path = os.path.join(CONFDIR, '%s.conf' % inst['iface'])
            new_conf = render_unispoke_conf(inst) if is_unispoke(inst) else render_conf(inst)
            old_conf = None
            if os.path.exists(conf_path):
                with open(conf_path) as f:
                    old_conf = f.read()
            pid = running(inst)
            if not inst['enabled'] or not inst['server'] or not inst['user']:
                if pid:
                    stop_instance(inst)
                continue
            if pid and old_conf == new_conf:
                # untouched and healthy: leave it alone
                continue
            if pid:
                stop_instance(inst)
            start_instance(inst)
            started += 1
        # stop instances that disappeared from the config entirely
        for conf in glob.glob(os.path.join(CONFDIR, '*.conf')):
            iface = os.path.splitext(os.path.basename(conf))[0]
            if iface not in active_ifaces:
                ghost = dict(instances[0]) if instances else {
                    'iface': iface, 'tun': '', 'uuid': '', 'server': '',
                }
                ghost['iface'] = iface
                stop_instance(ghost)
        wait_for_routes([i['iface'] for i in instances if i['enabled']
                       and i['server'] and i['user']])
        sync_service_pidfile(instances)
        print('%d instance(s) synced' % started)

    if action in ('start', 'stop', 'restart', 'sync'):
        # Reconcile Source NAT AFTER tunnels are up/down, so the destination
        # follows the routes the VPN server actually pushed (and the rule is
        # removed when an instance is down or disabled).  Always re-register
        # the dynamic tunnel interfaces and reload pf afterwards: the NAT
        # rules only take effect once config.xml <interfaces> contains the
        # ocvpn* entries, which is refreshed by register_interfaces().
        sync_nat(instances)
        reload_filter()
        return 0

    # status
    live = dict((inst['iface'], pid) for inst, pid in running_pids(instances))
    for inst in instances:
        pid = live.get(inst['iface'])
        state = 'running as pid %d' % pid if pid else 'not running'
        print('%-10s %-28s %s' % (inst['iface'], inst['server'], state))
    sync_service_pidfile(instances)
    if not instances:
        print('openconnect: no instances configured')
    return 0


if __name__ == '__main__':
    sys.exit(main())
