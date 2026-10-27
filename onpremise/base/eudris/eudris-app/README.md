# Application rollout

The Deployment uses one replica with `RollingUpdate`, `maxUnavailable: 0`,
`maxSurge: 1` and `minReadySeconds: 10`. The cluster must have capacity for a
second pod during an update. The old pod stays available until the new pod
has passed readiness and remained ready for 10 seconds.

Deploy these manifests together with an image built from the matching application
changes: Spring Boot Actuator provides `/actuator/health/liveness` and
`/actuator/health/readiness` on port 8080. Older images do not provide these probes.
The production overlay image tag must point to the new build.

Startup is allowed up to approximately 5 minutes. Readiness controls traffic;
liveness restarts an unhealthy process after startup. Probe groups use application
availability and do not call external registry APIs.

Termination allows 45 seconds: a 5-second preStop delay gives routing updates time
to propagate, then Spring Boot gracefully completes in-flight requests with a
30-second shutdown phase timeout.

Validate the rendered configuration with `kubectl kustomize deploy/overlays/prod`.
After applying through the normal delivery process, observe
`kubectl rollout status deployment/eudris-app -n eudris` and verify the old pod
remains until the new pod is ready. Actual rollout behavior must be checked in
the target cluster; local tests only verify manifests and HTTP probe behavior.
