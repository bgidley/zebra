# Public Zebra Commons relay — owner runbook (#231, S4; #232, S5; #233, S6)

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
podman run --rm -v ~/.config/zebra:/out:Z --entrypoint python localhost/zebra-web:prod \
  -m zebra_agent.commons.receipts --keygen --secret-env ZEBRA_COMMONS_OPERATOR_SECRET \
  --out /out/commons-operator.env
# Wrote ZEBRA_COMMONS_OPERATOR_SECRET to /out/commons-operator.env (mode 600)
# ZEBRA_COMMONS_RECEIPT_PUBKEY=<64 hex>     <- public: note it for steps 2 and 5
```

The secret goes straight into the sidecar's env file (`~/.config/zebra/commons-operator.env`,
mode 600) and is never printed; keygen refuses to overwrite an existing file.

- GitLab → Settings → CI/CD → Variables: add `ZEBRA_COMMONS_OPERATOR_SECRET` (masked, protected,
  not expanded) as the backup of record. The deploy job does not read it, so it never reaches
  `prod.env` or the web containers.
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

Re-run the tunnel script. It sees the relay's Quadlet (installed in step 2) and adds the route
above the hostname rule, next to the `/sync` route if the sync relay is installed:

```bash
deploy/podman/setup-tunnel.sh --print-config <host>   # check first: shows ^/commons$ -> 127.0.0.1:7779
deploy/podman/setup-tunnel.sh <host>                  # writes /etc/cloudflared/config.yml, validates, restarts
```

```yaml
ingress:
  - hostname: <host>
    path: ^/commons$
    service: http://127.0.0.1:7779
  - hostname: <host>
    service: http://127.0.0.1:8000
  - service: http_status:404
```

Never edit `config.yml` by hand: the script owns it, and re-running it keeps every installed
relay's route. Force a route on or off with `ROUTE_COMMONS=1|0` (and `ROUTE_SYNC=1|0`).
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

Apply it: `site.env` reaches the containers only through `prod.env`, which only the deploy job rebuilds (with the CI secrets), so a restart alone changes nothing. In GitLab open the **latest** master pipeline and retry its `deploy` job (never an older pipeline: it would roll prod back). Do not run `scripts/deploy-podman.sh` by hand: without the CI variables it would write a `prod.env` without the secrets.

Check: `podman logs zebra-web 2>&1 | grep "Commons publishing on"` shows the
canonical relay, the mirror count and `receipts verified`. Unset `ZEBRA_COMMONS_RELAYS` and
retry the latest deploy job again to turn it off.

## 6. Manual check (closes #231)

1. Pick a non-system workflow with at least 5 runs that was shaped at home (not on an observed
   device) and has a `commons` block: `/workflows/` → its genealogy shows writer and leak guard.
2. Offer it: `podman exec zebra-web python manage.py commons_offer "<name>"`. It parks on the
   owner's approval (`/tasks/`, "Offer <name> to the public Commons?"), showing the summary,
   stats, actions, golden tasks and YAML. Approve with **Publish it**.
3. The run ends `published` (`commons_offer_result`). Check the relay from anywhere:
   ```bash
   podman exec -i zebra-web python - <<'PY'
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

## 7. Second-Zebra check: offers seen, import, attestations (closes #232)

S5 (#232) needs a second Zebra: a dev instance with its **own** identity and database, never prod's
Oracle, never port 8000. Prod (Zebra A) keeps its offer from step 6; the dev instance is Zebra B.

1. **Start Zebra B** (any machine that can reach `wss://<host>/commons`; a checkout of master):
   ```bash
   export DJANGO_SETTINGS_MODULE=zebra_agent_web.e2e_settings   # file SQLite, not Oracle
   export ZEBRA_COMMONS_ENABLED=1 ZEBRA_COMMONS_KEY_DIR=$HOME/.zebra-b/keys
   export ZEBRA_COMMONS_RELAYS=wss://<host>/commons
   export ZEBRA_COMMONS_RECEIPT_PUBKEY=<operator pubkey hex>
   export OPENROUTER_API_KEY=<a dev key>        # the import's scans, ethics gate and gym
   cd zebra-agent-web && uv run python manage.py migrate
   uv run python scripts/build_css.py            # from the repo root
   uv run daphne -b 127.0.0.1 -p 8233 zebra_agent_web.asgi:application &
   uv run python manage.py run_daemon &          # polls the relay every tick
   ```
   Open `http://127.0.0.1:8233/`, finish setup, then `/commons/` → **Start a new Zebra**. The
   "Public Commons" section says publishing is on.
2. **B sees A's offer.** Within a daemon tick (`ZEBRA_DAEMON_POLL_INTERVAL`, 30 s) "Offers I have
   seen" lists A's workflow as `seen`, from A's fingerprint and npub (compare with A's
   `/commons/`), with its stats. The daemon log shows `Commons: saw offer`.
3. **B imports it.** Press **Import this**: the trace of *Commons Import* opens; it runs the
   personal-data scan, ethics review and the golden gym, then parks on "Adopt this imported
   workflow?" in `/tasks/` (the owner). Choose **adopt**. The offer turns `adopted` and shows
   Zebra's verdict ("I adopted it…"); `/workflows/` lists `<name> (from <A fingerprint>)`,
   supervised.
4. **A sees the attestation.** On prod's `/commons/` "My offers" shows `1 adopted` from B's
   fingerprint within a tick (prod's daemon must run with `ZEBRA_COMMONS_RELAYS` set, step 5).
5. **A run attests `worked`.** On B, run a goal the adopted workflow fits (or `/run/` choosing
   it), approve its supervised pre-run task, and let it finish. Within a tick A shows
   `1 worked`. Check the relay holds only labels, hashes and fixed reasons:
   ```bash
   podman exec -i zebra-web python - <<'PY'
   import asyncio
   from zebra_agent.commons import kinds
   from zebra_agent.commons.client import Filter
   from zebra_agent.commons.nostr import NostrSdkTransport
   from zebra_agent.commons.relay import RelayCommonsClient

   async def main():
       c = RelayCommonsClient(NostrSdkTransport("wss://<host>/commons"), private=False)
       for e in await c.fetch([Filter(kinds=(kinds.ATTEST_KIND,))]):
           print(e.tag_values("l"), e.tag_values("x")[0][:12], e.content)
       await c.close()
   asyncio.run(main())
   PY
   ```
   Expect `['adopted'] … {"reason":"owner-approved"}` and `['worked'] … {"reason":"run-succeeded"}`,
   nothing else: no goal, output or name.
6. **Hash rule.** Edit the adopted workflow on B (any saved change), run it again: no new
   attestation appears (the new version has a new hash, which matches no adopted offer).
7. Post the `/commons/` screenshots and the output on #232 and close it. Stop Zebra B and delete
   `$HOME/.zebra-b` and its `db.sqlite3` if it was only for the check.

## 8. Web-of-trust check (closes #233)

S6 (#233) needs three Zebras: prod (Zebra A), Zebra B from §7 and a third dev instance, Zebra C,
started exactly like B (own `ZEBRA_COMMONS_KEY_DIR`, own SQLite file, another port such as 8234,
never 8000). All three run with `ZEBRA_COMMONS_RELAYS` and the receipt key set, and a daemon.

1. **Nothing without relays.** Before setting `ZEBRA_COMMONS_RELAYS` anywhere, `/commons/` on
   prod shows "Zebras I know" saying publishing is off, and `podman logs zebra-web` has no
   `TRUST` line.
2. **B's owner vouches for C.** On B's `/commons/`, "I know this Zebra": paste C's npub (from C's
   `/commons/`), name it "C". B says "I now count it as a Zebra you know and published it."
3. **A's owner vouches for B.** On prod's `/commons/` paste B's npub, name it "B". Within a daemon
   tick (30 s) A lists:
   - B: local trust **0.80**, "you know it", path `B directly: 0.8 = 0.80`;
   - C: local trust **0.58**, path `<C fingerprint> via B: 0.8 × 0.8 × 0.9 = 0.58`, and Zebra's
     line "I trust it through Zebras you know, along the path above."
   Prod's log shows `Commons: published TRUST +0.80` and a `poll {... 'trust': 1 ...}`.
4. **Sybil check.** On C, vouch for a fresh key nobody else knows (any `npub` from
   `uv run python -c "from zebra_agent.commons import keys; print(keys.npub_encode(keys.public_key(keys.generate_secret_key())))"`).
   A shows it at 3 hops (`0.8 × 0.8 × 0.8 × 0.9^2 = 0.41`). Now withdraw C's vouch on B (B's
   **Withdraw my vouch**): within a tick A shows C and the fresh key at 0.00 with "No Zebra you know
   vouches for it", although C still trusts the fresh key. Vouch for C on B again.
5. **Score on offers.** Any offer from C now shows "Import score" above 0; an offer from a Zebra
   no one vouches for shows `Import score 0.00` and "Below my threshold of 0.5: no Zebra you know
   vouches for its publisher." **Import this** still works for the owner.
6. **Experience.** On B, import and run A's offer (§7 steps 3 and 5): B's edge to A moves
   (first `worked` publishes `+0.20`); on A's `/commons/` "Edges" under A shows "Trusted by B".
7. **Withdraw / distrust.** On prod, **Withdraw my vouch** on B: B and C drop to 0 within a tick.
   **Distrust** on C: C shows -0.80 and "You told me not to trust this Zebra".
8. Post the screenshots and log lines on #233 and close it. Stop Zebra C and delete its files.

## Operations

- Logs: `podman logs zebra-commons-relay` (lines `zebra-commons-policy:`), `podman logs
  zebra-commons-receipts`; prod: `grep "Commons:"` in `podman logs zebra-web` / `zebra-daemon`.
- Every event Zebra published is in the local mirror (`zebra_commons_events`, append-only).
- The receipt journal (`zebra-commons-receipts` volume) is the canonical order: back it up with
  the relay database. An open relay can be spammed with valid public-kind events; rate limits
  are deferred to S5. Neutral device labels: the signing device's cert (label, sphere) is public.
- Stop everything: `systemctl --user stop zebra-commons-receipts zebra-commons-relay` and unset
  `ZEBRA_COMMONS_RELAYS`.
