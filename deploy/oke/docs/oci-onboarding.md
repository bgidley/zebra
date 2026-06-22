# OCI onboarding — from a brand-new account to a filled `terraform.tfvars`

This is the one-time, mostly-manual setup. Everything after it is scripted
(`make` targets in `deploy/oke`). Allow ~30 minutes.

> You need **tenancy administrator** rights for the IAM steps (compartment,
> group, policy). If someone else administers the tenancy, hand them the
> "Admin steps" section.

## 0. Sign up / sign in
Create an Oracle Cloud account (https://www.oracle.com/cloud/free/) and sign in
to the Console. Note your **home region** (top-right) — you'll need its
identifier (e.g. `uk-london-1`) and its **OCIR key** (e.g. `lhr`). Region ↔ key
map: https://docs.oracle.com/iaas/Content/Registry/Concepts/registryprerequisites.htm

## 1. Admin steps (tenancy admin)

### 1a. Create a compartment
Console → **Identity & Security → Compartments → Create Compartment**.
Name: `zebra`. Copy its **OCID** → `compartment_ocid`.

### 1b. Create a group + user for Terraform
- **Identity → Domains → Default → Groups → Create**: `zebra-admins`.
- **Users → Create**: e.g. `zebra-terraform`; add to `zebra-admins`. Copy the
  user **OCID** → `user_ocid`.

### 1c. Policy for the group
**Identity → Policies → Create Policy** (in the **root** compartment, because
dynamic groups/policies and OKE live at tenancy level):

```
Allow group zebra-admins to manage all-resources in compartment zebra
Allow group zebra-admins to manage cluster-family in tenancy
Allow group zebra-admins to manage dynamic-groups in tenancy
Allow group zebra-admins to manage policies in tenancy
Allow group zebra-admins to manage repos in tenancy
Allow group zebra-admins to read objectstorage-namespaces in tenancy
```

## 2. API signing key (the Terraform user)
Easiest path — let the CLI generate it:

```bash
deploy/oke/scripts/01-oci-auth.sh    # runs `oci setup config`
```

It writes `~/.oci/config` + `~/.oci/oci_api_key.pem` and prints the **public**
key. Then in the Console: **Identity → Users → zebra-terraform → API Keys → Add
API Key → Paste Public Key**. The Console shows the **fingerprint** → `fingerprint`.
(`tenancy_ocid` is shown under **Tenancy details**.)

## 3. OCIR auth token (for pushing images)
**Identity → Users → <you> → Auth Tokens → Generate Token**. Copy it **once** into
`deploy/oke/secrets/registry.env` as `OCIR_TOKEN`. Your `OCI_USERNAME` is
`<namespace>/<username>` (federated users:
`<namespace>/oracleidentitycloudservice/<email>`). Find `<namespace>` with:

```bash
oci os ns get --query data --raw-output
```

## 4. SSH key for nodes
```bash
ssh-keygen -t ed25519 -f ~/.ssh/zebra_oke -C zebra-oke
```
Put the **public** key contents into `ssh_public_key`.

## 5. Fill the inputs
```bash
cp deploy/oke/terraform/terraform.tfvars.example deploy/oke/terraform/terraform.tfvars
# edit: tenancy_ocid, user_ocid, fingerprint, private_key_path, region, region_key,
#       compartment_ocid, ssh_public_key, admin_cidr (your IP /32 — `curl ifconfig.me`)
cp deploy/oke/secrets/registry.env.example deploy/oke/secrets/registry.env   # + OCIR token
cp deploy/oke/secrets/prod.env.example      deploy/oke/secrets/prod.env       # prod Oracle + keys
cp deploy/oke/secrets/claude.env.example    deploy/oke/secrets/claude.env     # agent tokens
# Smoke gets its own ephemeral Oracle schema per run via scripts/e2e_oracle_schema.py
# (same provisioner account as e2e) — no static smoke.env needed anymore.
```

## 6. Hand off to the scripts
```bash
cd deploy/oke
make tooling     # 00 — install oci/kubectl/terraform/kustomize/buildah
make infra       # 10 — terraform apply (creates VCN, OKE, OCIR, IAM)
make kubeconfig  # 20 — kubeconfig + `kubectl get nodes`
make secrets     # 30 — namespaces + k8s Secrets
```
You're now ready to build/push images and deploy (see `deploy/oke/README.md`).
