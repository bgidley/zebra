# Public Zebra Commons relay — owner runbook (#231, S4)

How to bring up the public Commons relay and offer a first workflow from prod. The code shipped
off by default: until step 5, prod behaves exactly as before. The deploy job never installs or
starts anything here (`scripts/deploy-podman.sh` copies only `deploy/podman/quadlet/*.container`;
`zebra-agent/tests/test_commons_public_relay.py` checks it). Design:
[zebra-commons-design.md](zebra-commons-design.md) § "Offers (S4) as built"; OpenSpec
`commons-offers`. The private sync relay ([commons-sync-relay-runbook.md](commons-sync-relay-runbook.md))
is separate: its own container, network, volumes, port and operator key.

**Root** marks the only steps that need `sudo`. Everything else runs as `opc` on the prod host.
`<host>` is the public hostname of the Cloudflare Tunnel.

Pieces (all in `deploy/podman/commons-relay/`):

| File | What it is |
|---|---|
| `zebra-commons-relay.container` | strfry (pinned `dockurr/strfry` digest), loopback `127.0.0.1:7779` |
| `strfry.conf` | relay config: no NIP-42 (public reads and writes), 128 KiB events, write policy plugin |
| `write_policy.py` | accepts only `zebra-commons` events of the public kinds (`OFFER`, `ATTEST`, `TRUST`, `GRANT`, `TRADE`, `OUTCOME`, `DEVICE_CERT`, `DEVICE_REVOKE`; `RECEIPT` only from the operator); never `SKILL`, never NIP-70 protected; journals each accepted event for receipts |
| `policy.json.example` | the operator public key |
| `zebra-commons-receipts.container` | receipt signer sidecar (`python -m zebra_agent.commons.receipts --secret-env ZEBRA_COMMONS_OPERATOR_SECRET`, Zebra image) |
| `zebra-commons.network` | private network for the two containers |

## 1. Generate the operator key and set the CI variable

```bash
podman run --rm --entrypoint python localhost/zebra-web:prod -m zebra_agent.commons.receipts \
  --keygen --secret-env ZEBRA_COMMONS_OPERATOR_SECRET
# ZEBRA_COMMONS_OPERATOR_SECRET=nsec1…      <- secret
# ZEBRA_COMMONS_RECEIPT_PUBKEY=<64 hex>     <- public
```

- GitLab → Settings → CI/CD → Variables: add `ZEBRA_COMMONS_OPERATOR_SECRET` (masked, protected,
  not expanded) as the backup of record. The deploy job does not read it, so it never reaches
  `prod.env` or the web containers.
- Write it to the sidecar's env file:
  ```bash
  install -m 600 /dev/null ~/.config/zebra/commons-operator.env
  echo 'ZEBRA_COMMONS_OPERATOR_SECRET=nsec1…' >> ~/.config/zebra/commons-operator.env
  ```
- Use a different key from the sync relay's. Never commit it or paste it in an issue.

## 2. Install and start the relay (Quadlets)

```bash
cd ~/code/zebra   # a checkout at the deployed commit
install -d -m 700 ~/.config/zebra-commons-relay
install -m 644 deploy/podman/commons-relay/strfry.conf ~/.config/zebra-commons-relay/
install -m 755 deploy/podman/commons-relay/write_policy.py ~/.config/zebra-commons-relay/
echo '{"operator_pubkey": "<ZEBRA_COMMONS_RECEIPT_PUBKEY>"}' > ~/.config/zebra-commons-relay/policy.json
sed -i 's#wss://ZEBRA_HOST/commons#wss://<host>/commons#' ~/.config/zebra-commons-relay/strfry.conf
install -m 644 deploy/podman/commons-relay/zebra-commons.network \
  deploy/podman/commons-relay/zebra-commons-relay.container \
  deploy/podman/commons-relay/zebra-commons-receipts.container ~/.config/containers/systemd/
podman pull docker.io/dockurr/strfry@sha256:91c19ac7a361e1b5147ca5cababf135b4efdc3d107496072eda50da9b59038be
systemctl --user daemon-reload
systemctl --user start zebra-commons-relay zebra-commons-receipts
systemctl --user status zebra-commons-relay zebra-commons-receipts
podman logs zebra-commons-relay 2>&1 | grep zebra-commons-policy   # "operator key set"
```

The relay never binds port 8000. `policy.json` is re-read on the next event (no restart).

## 3. Reverse-proxy route `wss://<host>/commons` (root)

Add a path rule **above** the existing hostname rule in `/etc/cloudflared/config.yml` (next to
the `/sync` rule if the sync relay is up; re-running `deploy/podman/setup-tunnel.sh` drops both):

```yaml
ingress:
  - hostname: <host>
    path: ^/commons$
    service: http://127.0.0.1:7779
  - hostname: <host>
    service: http://127.0.0.1:8000
  - service: http_status:404
```

```bash
sudo cloudflared tunnel --config /etc/cloudflared/config.yml ingress validate
sudo systemctl restart cloudflared
```

The rule matches `/commons` exactly: the web app's `/commons/` page (and everything under it)
must keep going to Django, so Zebras use `wss://<host>/commons` with no trailing slash.

## 4. Mirrors (optional)

Pick 1–2 public Nostr relays that accept kinds 30231 / 30228 / 1228 (most do; check their NIP-11
document). They hold copies only: receipts come from the canonical relay alone. A mirror that
refuses an event is logged and skipped; it never stops an offer.

## 5. Turn publishing on for prod

Add to `~/.config/zebra/site.env` (public values, not secrets):

```bash
ZEBRA_COMMONS_ENABLED=1                       # if not already on
ZEBRA_COMMONS_RELAYS=wss://<host>/commons, wss://relay.example.org   # canonical first
ZEBRA_COMMONS_RECEIPT_PUBKEY=<operator pubkey hex>
```

Restart: `systemctl --user restart zebra-web zebra-daemon` (or the next deploy rewrites
`prod.env`). Check: `podman logs zebra-web 2>&1 | grep "Commons publishing on"` shows the
canonical relay, the mirror count and `receipts verified`. Unset `ZEBRA_COMMONS_RELAYS` and
restart to turn it off.

## 6. Manual check (closes #231)

1. Pick a non-system workflow with at least 5 runs that was shaped at home (not on an observed
   device) and has a `commons` block: `/workflows/` → its genealogy shows writer and leak guard.
2. Offer it: `podman exec zebra-web python manage.py commons_offer "<name>"`. It parks on the
   owner's approval (`/tasks/`, "Offer <name> to the public Commons?"), showing the summary,
   stats, actions, golden tasks and YAML. Approve with **Publish it**.
3. The run ends `published` (`commons_offer_result`). Check the relay from anywhere:
   ```bash
   podman exec zebra-web python - <<'PY'
   import asyncio
   from zebra_agent.commons import keys, kinds
   from zebra_agent.commons.client import Filter
   from zebra_agent.commons.nostr import NostrSdkTransport
   from zebra_agent.commons.offer import verify_offer
   from zebra_agent.commons.receipts import receipt_order
   from zebra_agent.commons.relay import RelayCommonsClient

   async def main():
       c = RelayCommonsClient(NostrSdkTransport("wss://<host>/commons"), private=False)
       offers = await c.fetch([Filter(kinds=(kinds.OFFER_KIND,))])
       certs = await c.fetch([Filter(kinds=(kinds.DEVICE_CERT_KIND, kinds.DEVICE_REVOKE_KIND))])
       for o in offers:
           v = verify_offer(o, certs, expected_zebra=keys.npub_decode("<Zebra npub from /commons/>"))
           r = await c.fetch([Filter(kinds=(kinds.RECEIPT_KIND,), events=(o.id,))])
           print(o.id[:12], v.reason, receipt_order(r, "<operator pubkey hex>").get(o.id))
       await c.close()
   asyncio.run(main())
   PY
   ```
   Expect exactly one line, `ok`, and a receipt `seq`.
4. Negative checks: offering the same workflow again is refused ("already offered"); a workflow
   with fewer than 5 runs is refused at `prepare`; `podman logs zebra-commons-relay | grep
   "blocked:"` shows nothing from this Zebra.
5. Post the output on #231 and close it.

## Operations

- Logs: `podman logs zebra-commons-relay` (lines `zebra-commons-policy:`), `podman logs
  zebra-commons-receipts`; prod: `grep "Commons:"` in `podman logs zebra-web` / `zebra-daemon`.
- Every event Zebra published is in the local mirror (`zebra_commons_events`, append-only).
- The receipt journal (`zebra-commons-receipts` volume) is the canonical order: back it up with
  the relay database. An open relay can be spammed with valid public-kind events; rate limits
  are deferred to S5. Neutral device labels: the signing device's cert (label, sphere) is public.
- Stop everything: `systemctl --user stop zebra-commons-receipts zebra-commons-relay` and unset
  `ZEBRA_COMMONS_RELAYS`.
