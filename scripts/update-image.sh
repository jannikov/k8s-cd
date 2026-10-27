#!/usr/bin/env bash
# Run only in the dedicated k8s-cd checkout created by actions/checkout.
set -euo pipefail
: "${PROJECT:?PROJECT is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"
case "$PROJECT" in
  eudris-app) app=eudris ;;
  reporter-api|reporter-ui) app=reporter ;;
  *) echo "Unknown project: $PROJECT" >&2; exit 1 ;;
esac
cd "$(dirname "$0")/.."
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
for attempt in 1 2 3 4 5; do
  # Start from the latest remote state on every retry, preserving concurrent
  # updates to the other Reporter image even when they touch the same file.
  git fetch origin main
  git checkout -B main origin/main
  manifest=$(python3 scripts/set-image-tag.py "$PROJECT" "$IMAGE_TAG")
  kubectl kustomize "onpremise/live/$app" > /dev/null
  git add -- "$manifest"
  if git diff --cached --quiet; then
    echo "$PROJECT already uses $IMAGE_TAG"
    exit 0
  fi
  git commit -m "Update $PROJECT image to $IMAGE_TAG"
  if git push origin HEAD:main; then
    exit 0
  fi
  if [ "$attempt" -lt 5 ]; then sleep "$attempt"; fi
done
echo "Could not publish the image update after five attempts" >&2
exit 1
