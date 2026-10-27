# k8s-cd

Kubernetes manifests for the moonlight k3s cluster. Application repositories
build images; this repository defines what Argo CD deploys.

## Layout

- `onpremise/base/eudris/` and `onpremise/base/reporter/`: shared manifests.
- `onpremise/live/eudris/` and `onpremise/live/reporter/`: live image tags and overlays.
- `onpremise/live/argoapps/`: existing Argo CD Applications (`cd/eudris`, `cd/reporter`).
- `scripts/update-image.sh`: image update with validation and concurrent-push retries.

Both Applications use auto-sync and self-heal, with automatic pruning disabled.
Deployments retain two previous ReplicaSets. Secrets and TLS certificates remain
managed outside this repository; no secret values are stored here.

## Build workflow integration

After Kaniko succeeds, the Eudris and Reporter workflows check out
`jannikov/k8s-cd` on `main` into a separate `.k8s-cd` directory and run:

```sh
PROJECT=eudris-app IMAGE_TAG=20261026_192137_65376c5a bash scripts/update-image.sh
```

Supported projects: `eudris-app`, `reporter-api`, `reporter-ui`.
The existing `GH_PAT` secret in each application's `prod` environment must have
Contents read/write access to `jannikov/k8s-cd`. The application's `GITHUB_TOKEN`
does not grant cross-repository writes. No token belongs in Git URLs or manifests.

## Initial migration

1. Publish this repository on `main` and ensure validation passes.
2. Ensure Argo CD can read `https://github.com/jannikov/k8s-cd.git`.
3. Compare the rendered overlays against the current application manifests:
   `kubectl kustomize onpremise/live/eudris` and `kubectl kustomize onpremise/live/reporter`.
4. Switch the existing Applications (do not delete/recreate them):

   ```sh
   kubectl apply -k onpremise/live/argoapps
   ```

5. Confirm both Applications are Healthy/Synced, then publish the updated build
   workflows in Eudris and Reporter. Their legacy `deploy/` directories remain
   migration snapshots and are no longer the source for image updates.

The initial tags match the existing production overlays; switching repositories
does not intentionally change image versions. Never apply the entire cluster
Ansible playbook just to switch these two Applications.

## Validation

```sh
kubectl kustomize onpremise/live/argoapps
kubectl kustomize onpremise/live/eudris
kubectl kustomize onpremise/live/reporter
python3 -m unittest discover -s tests
```

To roll back an image, revert its tag commit in this repository. Argo CD will
reconcile the reverted version automatically.
