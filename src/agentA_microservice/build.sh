#!/usr/bin/env bash
set -euo pipefail

# Força BuildKit + modo inline cache + nunca cria imagem base nomeada
export DOCKER_BUILDKIT=1
export BUILDKIT_INLINE_CACHE=1

docker buildx build \
  --load \                              # coloca a imagem no docker images local
  --cache-to=type=inline \              # importante!
  --cache-from=type=inline \
  --tag agent-a:latest \
  --tag agent-a:$(date +%Y%m%d-%H%M)-$(whoami) \
  -f Dockerfile \
  .