# Bundled UniSpoke binary

This directory ships a FreeBSD amd64 build of UniSpoke 0.3.3.

- Upstream: https://github.com/NixaVulpi/UniSpoke
- License: MIT (see THIRD_PARTY_NOTICES.md at the repository root)

## Source patch applied

Upstream UniSpoke had no FreeBSD TUN implementation. The following files were
added under `internal/vpn/` (build tag `freebsd`) to enable `-vpn` mode on
OPNsense/FreeBSD:

- `configure_freebsd.go` — assign VIP/netmask, MTU, and pushed routes via
  `ifconfig` + `route add -net ... -interface <iface>`.
- `tun_offset_freebsd.go` — FreeBSD tun carries a 4-byte address-family header,
  so read/write offset is 4.

The build-tag guards on `configure_other.go`, `tun_offset_other.go` and
`tun_offset_other_test.go` were extended to exclude `freebsd`.

## Rebuild

```sh
GOOS=freebsd GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -o unispoke ./cmd/unispoke
```
