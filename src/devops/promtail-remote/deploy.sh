#!/bin/bash
# Deploy Promtail to all remote VMs

VMS=(
  "10.255.32.134"   # Agent A
  "10.255.32.32"    # Agent B
  "10.255.32.128"   # Agent C
  "10.255.32.104"   # Decision Engine
  "10.255.32.82"    # Data Module
  "10.255.32.143"   # Kafka
  "10.255.32.100"   # API Gateway
)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for vm in "${VMS[@]}"; do
  echo "=== Deploying Promtail to $vm ==="
  
  # Create promtail directory
  ssh pei_user@$vm "mkdir -p ~/promtail"
  
  # Copy files
  scp "$SCRIPT_DIR/docker-compose.yml" pei_user@$vm:~/promtail/
  scp "$SCRIPT_DIR/promtail-config.yml" pei_user@$vm:~/promtail/
  
  # Start Promtail
  ssh pei_user@$vm "cd ~/promtail && docker compose up -d"
  
  echo "✅ Promtail deployed to $vm"
done

echo ""
echo "=== Deployment Complete ==="
echo "Check logs in Grafana → Explore → Loki"
