#!/usr/bin/env bash
# Sandbox escape probe (#172): run by `zebra_builder.py --probe` in place of sandbox-run, with
# the same podman command. Reports what the sandbox can see and do to /out/probe.json; the
# builder compares it with what is allowed (check_probe).
set -uo pipefail
exec python3 - <<'PY'
import json, os, re

report = {"uid": os.getuid()}
status = open("/proc/self/status").read()
report["cap_eff"] = re.search(r"CapEff:\s*(\S+)", status).group(1)
report["no_new_privs"] = re.search(r"NoNewPrivs:\s*(\S+)", status).group(1)
report["env_names"] = sorted(os.environ)
report["token_seen"] = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")

# Mounts backed by a host filesystem (not proc, sysfs, tmpfs or the overlay root).
host_fs = {"xfs", "ext4", "btrfs", "ext3", "zfs", "nfs", "nfs4", "fuse.sshfs"}
mounts = set()
for line in open("/proc/self/mountinfo"):
    left, _, right = line.partition(" - ")
    if right.split()[0] in host_fs and left.split()[4] != "/":
        mounts.add(left.split()[4])
report["host_mounts"] = sorted(mounts)

candidates = ["/home/opc", "/home/opc/.config/zebra", "/home/opc/.config/glab-cli",
              "/root/.config/zebra", "/run/user/1000", "/host", "/var/lib/containers"]
report["host_paths_visible"] = [p for p in candidates if os.path.exists(p)]
report["podman_socket"] = any(os.path.exists(p) for p in [
    "/run/podman/podman.sock", "/var/run/docker.sock", "/run/user/1000/podman/podman.sock"])


def can_write(directory):
    path = os.path.join(directory, ".zebra-probe")
    try:
        with open(path, "w") as fh:
            fh.write("x")
        os.unlink(path)
        return True
    except OSError:
        return False


report["writable_outside"] = [d for d in ["/", "/usr", "/etc", "/usr/local/bin"] if can_write(d)]
report["workspace_writable"] = can_write("/workspace")

with open("/out/probe.json", "w") as fh:
    json.dump(report, fh)
PY
