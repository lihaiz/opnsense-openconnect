# OPNsense OpenConnect Multi-Instance Client

A generic multi-instance OpenConnect / SSL VPN client add-on for OPNsense.
It keeps the native OPNsense GUI workflow, while allowing several OpenConnect
connections to run in parallel with independent interfaces, PID files, logs,
and dynamic Source NAT based on the routes each VPN server actually pushes.

## Features

- GUI-managed multiple OpenConnect instances.
- Two protocol backends:
  - **OpenConnect** — Cisco AnyConnect, Juniper, Pulse, GlobalProtect, F5,
    Fortinet, and Array.
  - **UniSpoke** (`secoclient`) — Huawei SecoClient / SVN SSL VPN, supporting
    both the **Legacy** and **V1** UniVPN protocols with native TUN mode.
- Independent tunnel interface names and runtime files per instance.
- Preserves the physical WAN default route (split tunnel friendly).
- Generates Source NAT from the routes actually pushed by each server.
- No hardcoded VPN endpoint, credential, interface, LAN network, or remote
  subnet in the source tree.
- Dashboard Services status understands multi-instance operation: the service
  is running when at least one configured instance is online.

### UniSpoke backend (Huawei SecoClient / SVN)

This package bundles
[UniSpoke](https://github.com/NixaVulpi/UniSpoke), a standalone Go client that
implements both the **Legacy** and **V1** UniVPN protocols and creates its own
TUN adapter. Select `Huawei SecoClient (UniSpoke)` as the protocol for such a
gateway; mode and transport auto-detect, and can be forced per instance when a
gateway is misjudged.

## Installation

### One-command install (recommended)

On the OPNsense target, as root:

```sh
fetch -o /tmp/opnsense-openconnect-install.sh https://github.com/lihaiz/opnsense-openconnect/releases/download/v1.2.0/opnsense-openconnect-v1.2.0-install.sh
sh /tmp/opnsense-openconnect-install.sh
```

or with `curl`:

```sh
curl -fsSL -o /tmp/opnsense-openconnect-install.sh https://github.com/lihaiz/opnsense-openconnect/releases/download/v1.2.0/opnsense-openconnect-v1.2.0-install.sh
sh /tmp/opnsense-openconnect-install.sh
```

The installer is self-contained: it installs the package dependencies
(`os-openconnect`, `openconnect`, `vpnc-scripts`), copies the custom scripts and
the bundled `unispoke` FreeBSD binary, prepares `/conf/config.xml`, reloads
configd, and starts the manager. You do not need to download or unpack anything
else.

### Verify the download (optional)

```sh
sha256 /tmp/opnsense-openconnect-install.sh
# 09C033D013856E97279732B46223BFF0AB13C1063A4A55EB09FADED42C34306E
```

### Build from source (alternative)

```sh
git clone https://github.com/lihaiz/opnsense-openconnect.git
cd opnsense-openconnect
python3 build.py --one-file
sh dist/opnsense-openconnect.tar.sh
```

or copy the `pkg/` directory to the target and run `sh pkg/install.sh`.

Then add instances in `Services -> OpenConnect`. Source NAT is generated
automatically after each connection establishes and pushed routes appear.

## Verification

```sh
/usr/local/opnsense/scripts/OPNsense/Openconnect/run_instances.py status
pfctl -sn | grep 'nat on ocvpn'
```

## Security notes

- VPN credentials are entered in the OPNsense GUI and stored in that device's
  configuration; do not commit configuration backups to this repository.
- The installer does not create VPN instances or NAT rules by itself.
- Dynamic NAT is skipped when no local IPv4 network can be detected.

## 中文说明

把本机上跑通的 "OpenConnect (AnyConnect/SSL VPN) 客户端多实例" 方案打包，方便移植到
其它 OPNsense 机器。本方案是对官方单实例插件 os-openconnect 的重度定制版。

## 能力
- GUI: Services -> OpenConnect 里可增删多个实例，每个实例独立
  server / user / password / authgroup / 接口名(interface) / 协议。
- 两种协议后端：
  - **OpenConnect**：Cisco AnyConnect、Juniper、Pulse、GlobalProtect、F5、
    Fortinet、Array。
  - **UniSpoke**（协议选项 `secoclient`）：Huawei SecoClient / SVN SSL VPN，
    同时支持华为 UniVPN 的 **Legacy** 与 **V1** 两种协议，自带原生 TUN 模式。
    华为 SVN 网关（含老式 Legacy 与 V1）请选 `Huawei SecoClient (UniSpoke)`，
    mode/transport 自动探测，需要时可逐实例强制指定。
- 每个实例用**自己的接口名**，由 vpnc-instance.sh 把内核分配的 tunN 改名成该接口名，
  让 pf/NAT 能识别接口（UniSpoke 后端直接按该接口名创建 TUN，无需改名）。
- 启动脚本**保留物理 WAN 默认路由**，所以 mihomo 翻墙、百度直连都不受影响（split tunnel）。
- **NAT 是动态的**：run_instances.py 每次启停后，从 netstat -rn -f inet 读取每个隧道接口
  当前承载的远端网段（即 VPN 服务端实际推送的路由），据此生成/更新 Source NAT
  （Firewall -> Source NAT，OPNsense.Firewall.Filter.snatrules.rule；源=内网网段，
  目的=推送网段，接口=对应隧道接口）。**不写死任何远端网段**，换任意实例/服务端都会自动生效。
- run_instances.py 内置 cleanup_legacy()：开机/每次启停都会清掉官方单实例遗留
  (run.sh 守护、tun30000/ocvpn0 空壳接口、旧 openconnect.pid/log)。
- 主页 Services 状态支持多实例：只要任一实例在线就显示 running；状态来自
  `/var/run/openconnect.pid` 聚合 PID 文件，全部停止时该文件自动删除。

## 依赖（目标机需先装）
- 官方插件 os-openconnect（提供 GUI 骨架 + version + rc.d + actions 的包归属）
- openconnect（隧道二进制）
- vpnc-scripts（vpnc-script）
  安装: pkg install os-openconnect openconnect vpnc-scripts
  或 GUI: System -> Firmware -> Plugins 搜 openconnect。

> UniSpoke 二进制（华为 SecoClient/SVN 后端）已随本包内置（`pkg/bin/unispoke`，
> FreeBSD amd64），安装时自动放到 `/usr/local/sbin/unispoke`，无需单独安装。

## 本包内容
- pkg/custom/  真正生效的定制文件（覆盖到目标机对应路径）
  - run_instances.py    多实例管理器（start/stop/restart/status/sync + cleanup_legacy + 动态 NAT）
  - run-instance.sh     daemon 包装，导出 OC_IFACE
  - run-unispoke.sh     UniSpoke 后端 daemon 包装（密码走 UNISPOKE_PASSWORD 环境变量）
  - vpnc-instance.sh    openconnect 的 --script，做 tunN->interface 改名 + 保留 WAN 默认路由
  - rc.d/opnsense-openconnect   启动入口
  - actions_openconnect.conf    configd action（GUI 按钮 / API 调用）
  - inc/openconnect.inc         OPNsense 服务注册（Services 状态使用聚合 PID）
  - templates/...               rc.conf.d 开关模板
  - GUI: instances.volt, dialogInstance.xml, forms/instances.xml（实例增删改查界面）
- pkg/bin/unispoke     内置的 UniSpoke FreeBSD amd64 二进制（华为 SecoClient/SVN 后端）
- pkg/config/  参考片段（说明文件，安装器不写入实例/NAT）
- install.sh   一键：拷 custom 文件 -> 准备 config -> configd 重载 -> 启动
- pkg/apply_config.py  通用安装器：不写任何实例/NAT/网段（LAN 网段自动识别）

## 安装步骤（目标机 root，SSH）

### 一键安装（推荐）

在 OPNsense 上以 root 执行下面任一条命令即可。安装脚本是自包含的：会自动安装依赖
（os-openconnect、openconnect、vpnc-scripts）、拷贝定制脚本、准备 /conf/config.xml、
重载 configd 并启动，无需手动传包。

fetch（FreeBSD 原生）：

```sh
fetch -o /tmp/opnsense-openconnect-install.sh https://github.com/lihaiz/opnsense-openconnect/releases/download/v1.2.0/opnsense-openconnect-v1.2.0-install.sh
sh /tmp/opnsense-openconnect-install.sh
```

或 curl：

```sh
curl -fsSL -o /tmp/opnsense-openconnect-install.sh https://github.com/lihaiz/opnsense-openconnect/releases/download/v1.2.0/opnsense-openconnect-v1.2.0-install.sh
sh /tmp/opnsense-openconnect-install.sh
```

安装前校验下载文件（可选）：

```sh
sha256 /tmp/opnsense-openconnect-install.sh
# 09C033D013856E97279732B46223BFF0AB13C1063A4A55EB09FADED42C34306E
```

### 从源码安装（备选）

```sh
git clone https://github.com/lihaiz/opnsense-openconnect.git
cd opnsense-openconnect
python3 build.py --one-file
sh dist/opnsense-openconnect.tar.sh
```

或把 `pkg/` 目录拷到目标机后执行：`sh pkg/install.sh`。

### 添加实例并验证

1. 在 GUI 的 Services -> OpenConnect 添加实例（server/user/password/interface/协议）。
   Source NAT 会自动按该实例推送的路由生成，无需手写网段。
2. 验证：
   - `/usr/local/opnsense/scripts/OPNsense/Openconnect/run_instances.py status`
   - `ifconfig <interface>` 有隧道 IP
   - `pfctl -sn | grep <interface>` 能看到动态生成的 NAT 规则

## 移植注意事项（务必按目标机实际改）
- **LAN 网段**：无需手动设置。run_instances.py 的 _lan_net() 会从 config.xml 的 <interfaces>/<lan> 自动识别本机内网段。
- **接口名**：FreeBSD 接口组名不能以数字结尾，改名靠 vpnc-instance.sh 完成；每个实例单独命名。
- **authgroup**：ocserv 需要指定认证组。多实例连同同一 ocserv 通常受并发限制（常=1），
  多实例请用不同用户名。
- 只改了脚本/配置，不改 openconnect 二进制（用系统 pkg 提供的）。
