# k8s-cd

GitOps configuration for the single-node moonlight k3s cluster. Application
repositories build images and update their tags here; Argo CD deploys from `main`.

## Ownership and layout

| Application | Configuration | Purpose |
| --- | --- | --- |
| `k8s-cd` | `onpremise/live/argoapps` | Registers the child Applications in namespace `cd` |
| `eudris` | `onpremise/live/eudris` | Eudris workloads, ingress and Certificate |
| `reporter` | `onpremise/live/reporter` | Reporter API/UI, ingress and Certificate |
| `postgres` | `onpremise/live/postgres` | Shared PostgreSQL in namespace `db` |
| `keycloak` | `onpremise/live/keycloak` | Keycloak using its own database in shared PostgreSQL |
| `ci-runners` | `onpremise/live/ci-runners` | GitHub runners, workspace PVC and RBAC |
| `nexus` | `onpremise/live/nexus` | Nexus storage, registry and separate HTTPS UI proxy |
| `cert-manager` | `onpremise/live/cert-manager` and Application Helm source | Pinned chart v1.18.2 and ClusterIssuer |

Reusable manifests live under `onpremise/base`. Child Applications use auto-sync
and self-heal with automatic pruning disabled; PVCs have additional deletion
protection. Deployment history retains two previous ReplicaSets.

`rpi-k3s-cluster` owns node/k3s setup, initial Argo CD installation and GitOps
registration, Rancher, credential Secrets and database/user preparation. It seeds
cert-manager only on fresh clusters before Rancher starts. Application manifests,
image tags and cert-manager Certificate/Issuer definitions belong here. Generated
TLS private keys stay in Kubernetes Secrets; credentials never belong in Git.
Argo CD and Rancher certificate configuration has not yet been migrated here.

## Service addresses

| Service | Address | Access |
| --- | --- | --- |
| Keycloak | [keycloak.moonlight.local:30081](https://keycloak.moonlight.local:30081/) | Direct HTTPS NodePort; self-signed certificate |
| Argo CD | [argocd.moonlight.local:30080](https://argocd.moonlight.local:30080/) | Existing HTTPS endpoint |
| Rancher | [rancher.moonlight.local:32037](https://rancher.moonlight.local:32037/) | Existing HTTPS endpoint |
| Nexus UI | [nexus.moonlight.local:31443](https://nexus.moonlight.local:31443/) | HTTPS proxy; self-signed certificate |
| Nexus registry / CI | [nexus.moonlight.local:31081](http://nexus.moonlight.local:31081/) | HTTP; existing push/pull endpoint |
| Eudris | [eudris.duckdns.org](https://eudris.duckdns.org/) | Application Ingress |
| Reporter | [oun.me](https://oun.me/) | Application Ingress; API under `/api` |
| PostgreSQL | `postgres.db.svc.cluster.local:5432` | Cluster-internal; separate databases/users per project |

Local names must resolve to `192.168.88.237` through local DNS or the client's
hosts file. Local NodePorts are accessible from the LAN or a connected VPN;
internet reachability also depends on router forwarding/tunnels. Hubble has no
confirmed endpoint in this configuration.

Nexus HTTPS UI does not change CI registry traffic. Workflows and k3s continue
using `192.168.88.237:31081`; do not replace that URL with HTTPS without migrating
client trust and registry configuration.

## Certificates

cert-manager manages Eudris/Reporter certificates through `letsencrypt-prod` and
Keycloak/Nexus certificates through their local SelfSigned issuers. Local
self-signed certificates require separate client trust. Keycloak serves TLS
directly; Nexus terminates TLS in its additional nginx proxy, which reloads
certificates after rotation.

The read-only audit on **2026-10-27** found an expired certificate in Argo CD's
`cd/argocd-secret` (expired 2026-09-02), without `argocd.moonlight.local` in its
DNS names. Replacement/automatic renewal remains outstanding. Rancher's internal
certificate includes its local hostname and expires 2027-09-14; it is issued by
Rancher's internal CA, not cert-manager. These findings describe stored cluster
certificates, not a direct TLS handshake verification of every endpoint.

## Bootstrap and prerequisites

Argo CD must already be installed. From `rpi-k3s-cluster/ansible`, register the
repository and bootstrap its Applications:

```sh
ansible-playbook playbook.yml --tags argocd-apps
```

This prepares credential Secrets before creating the `k8s-cd` Application. It
does not reinstall Argo CD. On fresh clusters Ansible creates the database
namespace/Secrets, then GitOps starts PostgreSQL; Keycloak preparation waits for
it and creates its database and role. For adoption of an existing database or
first-time Keycloak preparation, use the documented Ansible commands in the
[infrastructure README](https://github.com/jannikov/k3s-moonlight/blob/main/README.md).

Review [the migration procedure](docs/platform-migration.md) before transferring
resource ownership. Do not delete PVCs or uninstall an adopted Helm release.

## Build workflow integration

After Kaniko succeeds, the Eudris and Reporter workflows check out this repository
on `main` into `.k8s-cd` and run:

```sh
PROJECT=eudris-app IMAGE_TAG=your-built-image-tag bash .k8s-cd/scripts/update-image.sh
```

Supported projects: `eudris-app`, `reporter-api`, `reporter-ui`. The script validates
the overlay and retries concurrent pushes. The existing `GH_PAT` in each source
repository's `prod` environment needs Contents read/write access to `k8s-cd`;
the source repository's `GITHUB_TOKEN` does not grant cross-repository writes.
Legacy source-repository `deploy/` directories are migration snapshots.

## Validation and rollback

```sh
for overlay in onpremise/live/*; do
  kubectl kustomize "$overlay" > /dev/null
done
python3 -m unittest discover -s tests
bash -n scripts/update-image.sh
```

CI also renders the pinned cert-manager Helm chart. To roll back an image,
revert its tag commit here. Database schema changes need a separate recovery
plan; reverting a manifest is not a database restore.
