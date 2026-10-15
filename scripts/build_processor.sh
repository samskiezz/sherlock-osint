#!/usr/bin/env bash
set -euo pipefail
sherlock_root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$sherlock_root"
unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS DOCKER_TLS_VERIFY DOCKER_CERT_PATH
docker_socket=/var/run/docker.sock
if [[ "$(uname -s)" == Darwin && -S "$HOME/.docker/run/docker.sock" ]]; then
  docker_socket="$HOME/.docker/run/docker.sock"
fi
if [[ ! -S "$docker_socket" ]]; then
  echo 'Start the local Docker service / Docker Desktop before building the processor.' >&2
  exit 1
fi
docker_arguments=(--host="unix://$docker_socket")
build_arguments=()
if [[ -f /etc/codex/network-policy.json && -f /etc/ssl/certs/ca-certificates.crt ]]; then
  build_arguments+=(--secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt)
fi
docker "${docker_arguments[@]}" info >/dev/null
docker "${docker_arguments[@]}" build "${build_arguments[@]}" -t sherlock-processor:0.4-build processing
docker "${docker_arguments[@]}" build -f processing/Dockerfile.compact -t sherlock-processor:0.4 processing
