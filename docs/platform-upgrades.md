# Platform upgrades (2026-10-28)

## Targets and ownership

- Argo CD v3.1.9 -> v3.5.6: initial installation and upgrades remain Ansible-owned.
  Bootstrap is pinned instead of using the moving `stable` manifest URL.
- Nexus 3.83.2-01 (H2) -> 3.97.3: GitOps-owned, pinned by version and multi-arch
  image digest. ARM64 is present in the official image index.
- Rancher 2.12.x -> 2.12.14 -> 2.13.10 -> 2.14.6: planned compatible path for
  Kubernetes 1.33, retaining Helm values. These patch charts were absent from
  both official latest/stable Helm indexes at preparation time, and direct chart
  download returned 404. `upgrade-rancher.yml` fails its availability preflight
  before making changes. Do not substitute older unpatched releases or jump to
  2.15 without checking its Kubernetes matrix.

No upgrade has been applied by preparing these changes. Take backups off-node
before deployment. An archive on the same disk is not disaster recovery; test
restoration in a separate environment. Exported credentials/backups are private.

## Nexus: backup before publishing the image change

Finish running CI jobs and pause new builds. From the infrastructure `ansible`
directory, run:

```sh
ansible-playbook backup-nexus.yml
```

The playbook checks free space, pauses `cd/nexus` reconciliation, stops Nexus,
waits for its Pod to disappear, archives the full local-path PVC, checks gzip
integrity and writes a SHA-256 checksum. It restarts the exact original image by
digest in an `always` block, avoiding an accidental `latest` pull. The preflight
found approximately 12 GiB of blobs and 44 MiB of H2 data. The PVC's requested
5Gi is not its actual local-path usage limit.

Copy the backup and checksum to protected off-node storage. Nexus intentionally
remains paused in Argo CD. Publish the new `k8s-cd/main` manifest, then resume:

```sh
kubectl -n cd annotate application nexus argocd.argoproj.io/skip-reconcile-
kubectl -n ci rollout status deployment/nexus --timeout=1200s
```

If backup fails, keep the old Git manifest and original instance; do not publish
the new image. Before resuming old `latest` configuration, pin it to the captured
original digest. Inspect backup/rescue errors before retrying maintenance.

The upgrade uses `Recreate` so only one Nexus process opens H2. It preserves
PVC, ports 31081/31443 and all credentials. Push/pull is unavailable during the
offline backup and upgrade. After upgrade, check login, repository listing, an
existing image pull and a normal runner build/push. Run Sonatype's required
`Repair - Rebuild repository search` task after crossing 3.85. Do not run the
unrelated Verify and Repair/Data Repair Plan tasks on the old affected version.
The bundled runtime moves to Java 21 after 3.87; carry over any custom JVM trust
configuration if present. Default JVM settings are otherwise unchanged.

A schema upgrade is not reversible by an image tag revert alone: recovery needs
the old image plus the matching complete data backup. Do not overwrite a live
PVC automatically. The H2 export/import threshold for pre-3.69 is not crossed
by this 3.83.2 source.

## Argo CD

```sh
ansible-playbook upgrade-argocd.yml
```

This backs up the k3s datastore/recovery credentials, applies the pinned upstream
installation with server-side apply (required for large ApplicationSet CRDs),
preserves current server Service ports, and waits for controller rollouts. The
custom namespace remains `cd`, with corrected ClusterRoleBinding subjects.
The upgrade does not reinstall applications or rotate credentials/certificates.
Review all upstream minor upgrade notes (3.1->3.2->3.3->3.4->3.5) before execution.
The current source definitions use neither source hydration nor GPG verification.
Argo 3.5 uses Helm 4: the existing cert-manager HTTPS chart source is retained;
any future HTTP OCI chart source needs explicit `insecureOCIForceHttp` config.
The HTTP Nexus image registry is kubelet/CI traffic, not an Argo Helm source.

After upgrade verify every Application renders and syncs, controller health,
server login, logs access and preserved NodePort URLs. Argo CD server TLS is separately managed by the `argocd-config` GitOps
Application; publishing that configuration replaces the expired fallback
certificate via `argocd-server-tls`. An image upgrade alone does not fix TLS.

## Rancher

```sh
ansible-playbook upgrade-rancher.yml
```

Run only after the official target charts become available and the support matrix
is reviewed. The playbook preserves existing Helm values (including service,
TLS and hostname settings), upgrades sequentially and waits at each step.
The original 2.12/2.13/2.14 branch is checked; unknown starting branches stop.
The full bootstrap playbook now skips installing Rancher if its Deployment
already exists. Use the dedicated upgrade, not the entire cluster setup.

## Sources

- https://github.com/argoproj/argo-cd/releases/tag/v3.5.6
- https://argo-cd.readthedocs.io/en/release-3.5/operator-manual/tested-kubernetes-versions/
- https://argo-cd.readthedocs.io/en/stable/operator-manual/upgrading/overview/
- https://help.sonatype.com/en/nexus-repository-upgrade-paths.html
- https://help.sonatype.com/en/sonatype-nexus-repository-3-97-0-release-notes.html
- https://github.com/rancher/rancher/releases
- https://www.suse.com/suse-rancher/support-matrix/all-supported-versions/rancher-v2-14-6/
