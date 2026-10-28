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
| `argocd-config` | `onpremise/live/argocd-config` | Argo CD server certificate and local hostname |
| `cert-manager` | `onpremise/live/cert-manager` and Application Helm source | Pinned chart v1.18.2 and ClusterIssuer |

Reusable manifests live under `onpremise/base`. Child Applications use auto-sync
and self-heal with automatic pruning disabled; PVCs have additional deletion
protection. Deployment history retains two previous ReplicaSets.

`rpi-k3s-cluster` owns node/k3s setup, initial Argo CD installation and GitOps
registration, Rancher, credential Secrets and database/user preparation. It seeds
cert-manager only on fresh clusters before Rancher starts. Application manifests,
image tags and cert-manager Certificate/Issuer definitions belong here. Generated
TLS private keys stay in Kubernetes Secrets; credentials never belong in Git.
Argo CD server TLS configuration belongs to `argocd-config`; Rancher still
manages its own internal certificates.

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
Keycloak/Nexus/Argo CD certificates through their local SelfSigned issuers. Local
self-signed certificates require separate client trust. Keycloak serves TLS
directly; Nexus terminates TLS in its additional nginx proxy, which reloads
certificates after rotation.

The `argocd-config` Application creates `cd/argocd-server-tls` for
`argocd.moonlight.local` and internal server DNS names. This dedicated Secret
has priority over the expired certificate previously found in `argocd-secret`.
Argo CD hot-reloads it without a restart, including future cert-manager renewals.
The existing `argocd-secret` and its authentication/signing keys are preserved.
After publishing, confirm issuance and the certificate actually served:

```sh
kubectl -n cd wait --for=condition=Ready certificate/argocd-server-tls --timeout=180s
kubectl -n cd get certificate argocd-server-tls
openssl s_client -connect argocd.moonlight.local:30080 -servername argocd.moonlight.local </dev/null 2>/dev/null | openssl x509 -noout -subject -issuer -dates -ext subjectAltName
```

The certificate is self-signed: issuing a fresh certificate fixes expiry and
hostname coverage, but does not automatically establish browser/client trust.
The endpoint stays `https://argocd.moonlight.local:30080/`.
Rancher's internal certificate includes its local hostname and was found valid
until 2027-09-14 during the 2026-10-27 audit; it remains Rancher-managed.

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

Supported projects: `eudris-app`, `reporter-app` (legacy: `reporter-api`, `reporter-ui`). The script validates
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

## Platform upgrades

See [the upgrade procedure](docs/platform-upgrades.md) for pinned Argo CD/Nexus
versions, Nexus offline backup, sequential Rancher upgrades and current chart
availability. Do not publish the Nexus image change before the backup.

## Startup and readiness checks

| Workload | Startup / readiness check |
| --- | --- |
| Eudris | Spring Actuator liveness / readiness endpoints |
| Reporter API | TCP port 80; current image has no mapped HTTP health endpoint |
| Reporter UI | HTTP `/index.html` on port 80 |
| PostgreSQL | `pg_isready` using the configured database and user |
| Keycloak | HTTPS management health endpoints on port 9000 |
| Nexus | HTTP `/service/rest/v1/status`, allowing up to 20 minutes for startup |
| Nexus HTTPS proxy | TCP port 8443; checks the proxy listener independently of Nexus |

Reporter API/PostgreSQL startup checks allow up to ten minutes; Reporter UI and
Nexus proxy allow 150 seconds. Readiness failures remove Pods from Service
endpoints without restarting them. Startup failure eventually restarts the
container. TCP and `pg_isready` do not prove application database queries or
credentials work. Runner Pods consume GitHub jobs rather than serving requests;
no synthetic network probe is added that might interrupt running builds.
Argo CD, Rancher and cert-manager keep their upstream installation/chart probes.
Probe changes update Pod templates and cause rollouts, including a brief
PostgreSQL interruption. Schedule those changes outside active CI/DB maintenance.

## Nexus stored-secret encryption

The Nexus Deployment mounts `ci/nexus-encryption` read-only and sets
`NEXUS_SECRETS_KEY_FILE=/etc/nexus-encryption/secrets.json`. Ansible owns that
Secret; its value is persisted in encrypted Vault, never in GitOps manifests.
Run `ansible-playbook prepare-nexus-encryption.yml` from the infrastructure
Ansible directory before publishing the Deployment change. Nexus restarts to
load the key file, briefly interrupting CI registry traffic.

After a current backup and successful rollout, use `reencrypt-nexus.yml` from
the infrastructure repository to schedule existing-secret re-encryption and
verify task success in Nexus. Keep the updated Vault with protected backups;
PVC backups alone do not contain this external key. See the
[infrastructure instructions](https://github.com/jannikov/k3s-moonlight/blob/main/README.md#nexus-encryption-key).

### Reporter: один контейнер

`reporter-app` содержит ASP.NET API и собранный React UI. Один Deployment и Service обслуживают `https://oun.me`, включая `/api`. PostgreSQL остаётся отдельным приложением.

Сначала опубликуйте изменения `k8s-cd`, затем Reporter. Первая успешная сборка `Build Reporter App` публикует образ `reporter-app` и переключает `onpremise/live/reporter/kustomization.yaml` на объединённый Deployment и новый Service. До этого live-конфигурация использует прежние образы. Повторные сборки меняют только тег объединённого образа.

Argo CD не удаляет старые ресурсы автоматически (`prune: false`). После переключения и проверки приложения выполните Ansible playbook `finish-reporter-app-migration.yml` из `rpi-k3s-cluster/ansible`: он проверит готовность нового Deployment и переключение Ingress перед удалением старых Deployment, Service и неиспользуемого ConfigMap.
