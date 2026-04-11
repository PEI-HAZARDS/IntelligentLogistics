#!/bin/bash
# Quick rebuild of Data Module after code changes

set -e

echo "🔧 Rebuilding Data Module..."
docker-compose build --no-cache data-module

echo "🔄 Restarting Data Module..."
docker-compose up -d data-module

echo "⏳ Waiting 15 seconds for startup..."
sleep 15

echo ""
echo "✅ Data Module rebuilt and restarted!"
echo ""
echo "Check logs:"
echo "  docker logs dm_data_module --tail=30"
echo ""
echo "Ready to test:"
echo "  ./test_all.sh AB-12-CD"
