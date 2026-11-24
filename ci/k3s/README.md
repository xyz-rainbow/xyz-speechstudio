# Homelab CI (k3s + self-hosted runners)

Speech Studio CI targets **self-hosted** runners labeled `k3s` so GitHub-hosted minutes stay unused.

| Job | Labels | Where |
| --- | --- | --- |
| Frontend / Python / Rust Linux | `self-hosted,linux,k3s` | Pod/Deployment on k3s (`github-actions-runner.yaml`) |
| Rust macOS | `self-hosted,macOS,k3s` | Physical/VM Mac in the homelab (not a Linux pod) |
| Rust Windows | GitHub-hosted | Only `workflow_dispatch` + `use_github_hosted` |

## Linux runner on k3s

```bash
# From a machine with gh + kubectl to the cluster:
TOKEN=$(gh api -X POST repos/xyz-rainbow/xyz-speechstudio/actions/runners/registration-token --jq .token)
kubectl create namespace ci --dry-run=client -o yaml | kubectl apply -f -
kubectl -n ci create secret generic gha-runner-token --from-literal=token="$TOKEN" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f ci/k3s/github-actions-runner.yaml
```

Registration tokens expire (~1h). If the pod restarts after expiry and lost `.runner`, mint a fresh token and update the secret, then restart the Deployment.

## macOS runner (homelab)

On the Mac (labels must include `macOS` and `k3s`):

```bash
# download actions/runner for darwin, then:
./config.sh --url https://github.com/xyz-rainbow/xyz-speechstudio \
  --token "$TOKEN" \
  --labels self-hosted,macOS,k3s \
  --name speechstudio-macos
./run.sh
```

`ssh-homelab.conf` is local-only (gitignored).
