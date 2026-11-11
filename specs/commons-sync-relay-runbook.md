# Commons private sync relay — owner runbook (#246, S3b-2)

How to bring up skill sync between two deployments of one Zebra (home + work) over the private
relay. The code shipped off by default: until step 6, prod behaves exactly as before. The deploy job
never installs or starts anything here (`scripts/deploy-podman.sh` copies only
`deploy/podman/quadlet/*.container`). Design: [zebra-commons-design.md](zebra-commons-design.md)
§ "Skill sync (S3b-2) as built"; OpenSpec `commons-sync-relay`.

**Root** marks the only steps that need `sudo`. Everything else runs as `opc` on the prod host.
`<host>` is the public hostname of the Cloudflare Tunnel (e.g. `zebra.example.com`).

Pieces (all in `deploy/podman/sync-relay/`):

| File | What it is |
|---|---|
| `zebra-sync-relay.container` | strfry (pinned `dockurr/strfry` digest), loopback `127.0.0.1:7778` |
| `strfry.conf` | relay config: NIP-42 on, 128 KiB events, write policy plugin |
| `write_policy.py` | allow-list + receipt journal (accepts only `SKILL`, `DEVICE_CERT`, `DEVICE_REVOKE`, operator `RECEIPT`) |
| `allowlist.json.example` | registered Zebra keys + operator public key |
| `zebra-sync-receipts.container` | receipt signer sidecar (`python -m zebra_agent.commons.receipts`, Zebra image) |
| `zebra-sync.network` | private network for the two containers |
| `zebra-sync-retention.service` / `.timer` | daily 90-day retention of `SKILL`s and their receipts |

## 1. Generate the operator key and set the CI variables

```bash
podman run --rm -v ~/.config/zebra:/out:Z --entrypoint python localhost/zebra-web:prod \
  -m zebra_agent.commons.receipts --keygen --out /out/sync-operator.env
# Wrote ZEBRA_SYNC_OPERATOR_SECRET to /out/sync-operator.env (mode 600)
# ZEBRA_SYNC_RECEIPT_PUBKEY=<64 hex>     <- public: note it for steps 4 and 5
```

The secret goes straight into the sidecar's env file (`~/.config/zebra/sync-operator.env`,
mode 600) and is never printed; keygen refuses to overwrite an existing file.

- GitLab → Settings → CI/CD → Variables: add `ZEBRA_SYNC_OPERATOR_SECRET` (masked, protected,
  not expanded) as the backup of record. The deploy job does **not** read it (it is not in
  `SECRET_VARS`), so it never reaches `prod.env` or the web containers.
- Never commit it, paste it in an issue, or put it in `site.env`.

## 2. Install and start the relay (Quadlets)

```bash
cd ~/code/zebra   # a checkout at the deployed commit
install -d -m 700 ~/.config/zebra-sync-relay
install -m 644 deploy/podman/sync-relay/strfry.conf ~/.config/zebra-sync-relay/
install -m 755 deploy/podman/sync-relay/write_policy.py ~/.config/zebra-sync-relay/
install -m 644 deploy/podman/sync-relay/allowlist.json.example ~/.config/zebra-sync-relay/allowlist.json
sed -i 's#wss://ZEBRA_HOST/relay/sync#wss://<host>/relay/sync#' ~/.config/zebra-sync-relay/strfry.conf
install -m 644 deploy/podman/sync-relay/zebra-sync.network \
  deploy/podman/sync-relay/zebra-sync-relay.container \
  deploy/podman/sync-relay/zebra-sync-receipts.container ~/.config/containers/systemd/
install -m 644 deploy/podman/sync-relay/zebra-sync-retention.service \
  deploy/podman/sync-relay/zebra-sync-retention.timer ~/.config/systemd/user/
podman pull docker.io/dockurr/strfry@sha256:91c19ac7a361e1b5147ca5cababf135b4efdc3d107496072eda50da9b59038be
systemctl --user daemon-reload
systemctl --user start zebra-sync-relay zebra-sync-receipts
systemctl --user enable --now zebra-sync-retention.timer
systemctl --user status zebra-sync-relay zebra-sync-receipts
podman logs zebra-sync-relay 2>&1 | grep zebra-sync-policy   # "allow-list: 0 Zebra key(s)…"
```

`serviceUrl` in `strfry.conf` must be exactly the URL devices use (`ZEBRA_SYNC_RELAY`), or NIP-42
AUTH fails and every `SKILL` is refused. The relay never binds port 8000.

## 3. Reverse-proxy route `wss://<host>/relay/sync` (root)

Re-run the tunnel script. It sees the relay's Quadlet (installed in step 2) and adds the route
above the hostname rule; it also keeps the `/commons` route if the public relay is installed:

```bash
deploy/podman/setup-tunnel.sh --print-config <host>   # check first: shows ^/relay/sync$ -> 127.0.0.1:7778
deploy/podman/setup-tunnel.sh <host>                  # writes /etc/cloudflared/config.yml, validates, restarts
```

```yaml
ingress:
  - hostname: <host>
    path: ^/relay/sync$
    service: http://127.0.0.1:7778
  - hostname: <host>
    service: http://127.0.0.1:8000
  - service: http_status:404
```

Never edit `config.yml` by hand: the script owns it, and re-running it keeps every installed
relay's route. Force a route on or off with `ROUTE_SYNC=1|0` (and `ROUTE_COMMONS=1|0`).
strfry serves WebSockets on any path, so `/relay/sync` needs no rewrite. If Cloudflare Access
protects `<host>`, the Access bypass app for path `relay` (public relay runbook, step 3) covers
this relay too; NIP-42 and the allow-list still decide who may publish.

## 4. Register the Zebra key on the allow-list

On the deployment that holds the Zebra key, open `/commons/` and copy the Zebra npub; decode it:

```bash
podman exec zebra-web python -c "from zebra_agent.commons import keys; print(keys.npub_decode('npub1…'))"
```

Edit `~/.config/zebra-sync-relay/allowlist.json`:

```json
{"zebra_pubkeys": ["<zebra pubkey hex>"], "operator_pubkey": "<ZEBRA_SYNC_RECEIPT_PUBKEY>"}
```

The policy re-reads it on the next event (no restart). Devices need no entry: a device may
publish `SKILL`s once its `DEVICE_CERT` from a registered Zebra key is on the relay (each device
publishes its own cert before it sends) and until a `DEVICE_REVOKE` for it arrives.

## 5. Turn sync on for prod

Add to `~/.config/zebra/site.env` (public values, not secrets):

```bash
ZEBRA_COMMONS_ENABLED=1            # if not already on
ZEBRA_SYNC_RELAY=wss://<host>/relay/sync
ZEBRA_SYNC_RECEIPT_PUBKEY=<operator pubkey hex>
# optional: ZEBRA_SYNC_DIRECTION=both|send|receive|off
```

Apply it: `site.env` reaches the containers only through `prod.env`, which only the deploy job rebuilds (with the CI secrets), so a restart alone changes nothing. In GitLab open the **latest** master pipeline and retry its `deploy` job (never an older pipeline: it would roll prod back). Do not run `scripts/deploy-podman.sh` by hand: without the CI variables it would write a `prod.env` without the secrets.
Check: `podman logs zebra-daemon 2>&1 | grep "Skill sync on"` shows
the relay, sphere, direction and `receipts verified`. Unset `ZEBRA_SYNC_RELAY` and retry the latest deploy job
to turn it off again; queued events stay in `<library>/.sync/outbox.jsonl` for next time.

## 6. Pair a second deployment (work)

On the work deployment (a dev instance, or another host; never the prod port):

1. Set `ZEBRA_COMMONS_ENABLED=1`, the same `ZEBRA_SYNC_RELAY` and `ZEBRA_SYNC_RECEIPT_PUBKEY`.
2. `/commons/` → copy the pairing code (device npub) and compare the fingerprint.
3. On prod `/commons/` → Pair device: paste the code, sphere `work`, "managed by someone else"
   (observed) for an employer laptop. Copy the `zcert1…` code back to the work device → Import.
4. Restart work. Within a daemon tick both devices publish their certs and learn each other's
   from the relay (`podman logs zebra-daemon | grep "learnt certs"`).

## 7. Manual E2E check (closes #246)

1. **Share arrives.** At work, run a workflow twice (or save one and run the dream cycle);
   approve the `observed_share_approval` task. Within a tick or two it appears in the home
   library (`/workflows/`) with the same content hash, and its genealogy shows "received from
   there". On the relay: `podman logs zebra-sync-relay | grep "write policy blocked"` is empty.
2. **Outage loses nothing.** `systemctl --user stop zebra-sync-relay`; approve another share at
   work (it is queued: `<library>/.sync/outbox.jsonl` has lines); `systemctl --user start
   zebra-sync-relay`; within a tick the outbox empties and the share arrives at home.
3. **Revocation by receipt order.** On prod `/commons/` revoke the work device. Its earlier
   shares stay adopted; a new share from it is refused by the relay ("device has no valid cert")
   and, if replayed, rejected at home (`revoked` in the Skill Receive result).
4. Receipts: `podman logs zebra-sync-receipts` shows "Published N receipt(s)" for each event.

Post the result on #246 and close it.

## Operations

- Logs: `podman logs zebra-sync-relay` (lines `zebra-sync-policy:`), `podman logs zebra-sync-receipts`.
- The receipt journal (`zebra-sync-receipts` volume, `journal.jsonl`) is the canonical order:
  back it up with the relay database. It grows ~200 bytes per event; retention deletes old `SKILL`s
  and their receipts from strfry, not journal lines.
- Refused queued events are kept in `<library>/.sync/outbox.rejected.jsonl` with the reason.
- Stop everything: `systemctl --user stop zebra-sync-receipts zebra-sync-relay` and unset
  `ZEBRA_SYNC_RELAY`.
