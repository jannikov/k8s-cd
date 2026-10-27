# Adopt existing platform resources into Argo CD

This first phase moves ownership without deleting or recreating live resources.
Do not uninstall Nexus/runners or delete their PVCs before adoption.

## Ownership

| Resources | Owner after migration |
| --- | --- |
| Eudris Certificate | Argo CD application `eudris` |
| Reporter Certificate | Argo CD application `reporter` |
| CI workspace PVC, runner Deployments and their ServiceAccount/RBAC | Argo CD application `ci-runners` |
| Nexus Deployment, Service and PVC | Argo CD application `nexus` |
| Namespace `ci`, host directories, registry credentials and runner token Secrets | Ansible |
| cert-manager and ClusterIssuer | Argo CD application `cert-manager`; Ansible seeds cert-manager on fresh clusters |
| Rancher, PostgreSQL, Keycloak | Ansible (later phases) |
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

Rancher remains on Ansible. PostgreSQL/Keycloak need a dedicated data backup and a move
from inline passwords to Secret references before their manifests can be public.
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
