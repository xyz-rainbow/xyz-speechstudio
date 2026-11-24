# Homelab CI (ARC on k3s + macOS self-hosted)

| Job | `runs-on` | Where |
| --- | --- | --- |
| Frontend / Python / Rust Linux | `arc-xyz-speechstudio` | ARC AutoscalingRunnerSet in `arc-runners` |
| Rust macOS | `self-hosted,macOS,k3s` | Mac del homelab (fuera del pod Linux) |
| Rust Windows | `windows-latest` | Solo `workflow_dispatch` + `use_github_hosted` |

## Apply Linux ARC scale set

```bash
kubectl apply -f ci/k3s/autoscaling-runner-set.yaml
kubectl -n arc-systems get pods -l actions.github.com/scale-set-name=arc-xyz-speechstudio
kubectl get autoscalingrunnerset -n arc-runners arc-xyz-speechstudio
```

Reuses existing `gh-arc-pat` + `arc-deployer` (same pattern as `arc-reverse-anything`).

## macOS runner

On the Mac:

```bash
./config.sh --url https://github.com/xyz-rainbow/xyz-speechstudio \
  --token "$REG_TOKEN" \
  --labels self-hosted,macOS,k3s \
  --name speechstudio-macos
./run.sh
```

`ssh-homelab.conf` is gitignored.
