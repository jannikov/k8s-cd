# Adopt existing platform resources into Argo CD

This first phase moves ownership without deleting or recreating live resources.
Do not uninstall Nexus/runners or delete their PVCs before adoption.

## Ownership

| Resources | Owner after migration |
| --- | --- |
| Eudris Certificate | Argo CD application `eudris` |
| Reporter Certificate | Argo CD application `postgres` |
| CI workspace PVC, runner Deployments and their ServiceAccount/RBAC | Argo CD application `ci-runners` |
| Nexus Deployment, Service and PVC | Argo CD application `nexus` |
| Namespace `ci`, host directories, registry credentials and runner token Secrets | Ansible |
| cert-manager and ClusterIssuer | Argo CD application `cert-manager`; Ansible seeds cert-manager on fresh clusters |
| PostgreSQL Deployment, Service, PVC in `db` | Argo CD application `postgres` |
| Rancher, Keycloak | Ansible (later phases) |
| k3s, CNI, node packages and initial Argo CD/bootstrap | Ansible |

The transferred tasks have been removed from the infrastructure playbook.
The CI Namespace remains there because Ansible must create credential Secrets
before GitOps starts. No Secret objects or secret values are added here.

## Before publishing

1. Ensure changes in `rpi-k3s-cluster` and `k8s-cd` are reviewed together.
2. Back up Nexus data using your established backup procedure. Save the live
   resource definitions, especially the bound PVC names and volume references.
3. Confirm `ci` already exists, along with Secrets `kaniko-docker-config`,
   `github-runner-token`, and `eudris-github-runner-token`. Fresh clusters get
   those through Ansible/Vault. No new secret manager is introduced.
4. Confirm cert-manager and ClusterIssuer `letsencrypt-prod` are ready.
5. Compare each rendered overlay with the live cluster before pushing to `main`:

   ```sh
   kubectl diff -k onpremise/live/eudris
   kubectl diff -k onpremise/live/reporter
   kubectl diff -k onpremise/live/ci-runners
   kubectl diff -k onpremise/live/nexus
   ```

   `kubectl diff` returns 1 when there are differences. Check for changes to
   Deployment pod templates: adoption of manifests can restart runners/Nexus
   if the live specs have drifted from the old Ansible definitions. Finish active
   builds before such a rollout. Images are copied as-is, including existing
   `latest` tags; pinning them is a separate change.

## Apply

Publish `k8s-cd/main` only after reviewing the diffs: its existing bootstrap
Application auto-syncs `onpremise/live/argoapps`, creating `ci-runners` and
`nexus`. The existing Eudris/Reporter Applications pick up their Certificates.
This is an active rollout, not just a documentation push.

All four child Applications keep pruning disabled. Both PVCs also carry
`Prune=false,Delete=false`; preserve those protections if changing sync policy.
Existing resource names, namespaces, PVC names, storage sizes, storage classes,
Nexus NodePort, runner credentials references and certificate Secret names are
unchanged. No cascade-deletion finalizers are added to Applications.

After sync, verify Nexus is accessible, both runners are online, the existing
PVCs are Bound, and both Certificates are Ready. Do not delete generated TLS
Secrets or the existing ACME account Secret.

## Rollback

Revert the relevant manifest changes in Git to recover an unwanted spec change.
To hand ownership back to Ansible, first disable auto-sync/self-heal for the
specific Application and remove only its registration without deleting managed
resources; then restore the corresponding Ansible tasks. Do not run Ansible and
Argo CD against competing desired definitions.

## Deferred phases

Rancher remains on Ansible. Keycloak still needs its own migration. PostgreSQL adoption is described below.
Cilium installation/network migration remains a separate Ansible procedure.

## Live preflight checked on 2026-10-27

Read-only checks through Rancher confirmed:

- `ci-workspace-pvc` is Bound, 2Gi, ReadWriteOnce, local-path.
- `nexus-pvc` is Bound, 5Gi, ReadWriteOnce, local-path.
- Both application Certificates and ClusterIssuer `letsencrypt-prod` are Ready.
- The three required CI Secrets exist; values were not read.
- Runner RBAC and Nexus NodePort 31081 match the migrated definitions.
- Live runner init containers also reference their token Secret. Those references
  and the live main-container environment ordering are preserved in Git, rather
  than copying the stale Ansible pod template verbatim.
- Existing image references match (`sonatype/nexus3:latest`,
  `myoung34/github-runner:latest`, `curlimages/curl:latest`).

No cluster changes were made by these checks. A final server-side diff is still
recommended at rollout time; live resources may change after this check. The
historical `kubectl.kubernetes.io/restartedAt` annotation on the Eudris runner
is intentionally not made into a permanent desired timestamp.

## cert-manager adoption

The `cert-manager` Application combines the official Helm chart v1.18.2 with
Git-managed values and ClusterIssuer. Release name and namespace stay
`cert-manager`; existing ACME and certificate Secrets are preserved. The issuer
runs in sync wave 1 after the chart resources are healthy. CRDs retain the chart's
`helm.sh/resource-policy: keep` annotation; automatic pruning is disabled.
Server-side apply avoids the annotation size limit on CRDs.

Ansible only installs the same pinned chart if the controller Deployment is
absent, to satisfy Rancher's dependency before Argo CD starts. It no longer
reconciles existing cert-manager installations or the ClusterIssuer. On a fresh
cluster the issuer arrives through GitOps; certificate issuance may wait for
that first sync. Do not uninstall the old Helm release: Argo CD renders charts
without updating Helm's stored release state, which remains historical.

Before publishing, compare `helm template cert-manager cert-manager
--repo https://charts.jetstack.io --version v1.18.2 --namespace cert-manager
-f onpremise/live/cert-manager/values.yaml` against the live resources. After sync,
verify all three cert-manager Deployments, the webhook, ClusterIssuer and existing
Certificates are healthy. The existing installation was checked at v1.18.2 with
`installCRDs: true`; no chart upgrade is included in this migration.

## Shared PostgreSQL adoption

PostgreSQL is managed by its own `postgres` Application in namespace `db`.
Reporter is a consumer; other projects can use separate databases and users on
the same server. Manifests live in `onpremise/base/postgres` and
`onpremise/live/postgres`.
The endpoint stays `postgres.db.svc.cluster.local:5432`, with image `postgres:15`,
PVC `postgres-pvc`, 5Gi local-path, and the same data mount. Do not change the
namespace or add an overlay-wide namespace transformer. Namespace and credential
Secret remain Ansible-owned. No database passwords are committed here.

Before pushing this change to `main`, run from `rpi-k3s-cluster/ansible`:

```sh
ansible-playbook prepare-reporter-db.yml
```

This playbook checks Vault against the database configuration (inline values
or existing Secret references), creates a private `pg_dumpall` backup of all databases and roles
under `/var/backups/reporter-postgres` on the node, checks the compressed file,
and creates `db/reporter-db-credentials`. A mismatch stops preparation; changing
POSTGRES_PASSWORD does not change the password of an initialized database.
Copy the resulting backup to your protected off-node backup storage before
rollout; the node-local dump alone does not cover node/disk loss. Restore has
not been tested by this migration.

Only then publish the GitOps change. Argo CD will adopt the existing PVC/Service
and restart PostgreSQL once to consume Secret references. `Recreate` prevents a
second database Pod from opening the same data directory during a rollout;
expect brief database downtime. The PVC has `Prune=false,Delete=false`, and the
PostgreSQL Application keeps automated pruning disabled. Do not delete the PVC.
No major-version upgrade or data copy to a new volume is included.

After sync, check `kubectl -n db rollout status deployment/postgres`, PVC Bound,
Reporter database access, and Keycloak if it is deployed against this endpoint.
The live read-only preflight on 2026-10-27 found volume
`pvc-1c98cdf9-c94e-407a-bc9c-9435871d646c`, image `postgres:15`, databases
`postgres` and `reporter`, and no `reporter-db-credentials` Secret yet. Keycloak's
Ansible configuration points to this server, but its database was not present
in that listing. Existing data and names are preserved; initialization of the
Keycloak database remains with Ansible and now waits for GitOps PostgreSQL.

To roll back a bad spec, revert the deployment manifest while retaining the
existing PVC. A Secret reference change is not a database password rotation.
Do not restore a dump over a running database as an automatic rollback action.

### Ownership transfer from Reporter

If Reporter already adopted the database, sync/refresh `reporter` first so it
stops declaring PostgreSQL, then sync `postgres`. Reporter has pruning disabled,
so removing these resources from its source preserves the live Deployment,
Service and PVC. Do not enable pruning or manually delete/prune these resources
during the handoff. Automatic sync can briefly show SharedResourceWarning until
Reporter refreshes; only `postgres` should declare them afterward. This move
changes resource ownership only: database manifests, credentials, PVC and server
address are unchanged. It does not itself require a PostgreSQL restart.

The existing Secret name `reporter-db-credentials` is retained to avoid a Pod
template change. It configures the existing PostgreSQL bootstrap account; it is
not a shared credential to distribute to every project. Provision separate
roles/databases and application Secrets for additional consumers. No new users
or databases are created by the ownership transfer.
