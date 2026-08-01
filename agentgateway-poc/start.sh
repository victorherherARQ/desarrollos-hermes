#!/bin/bash
# inject_key.sh — reads MINIMAX_API_KEY from ~/.hermes/.env and injects into config.yaml
set -a
source ~/.hermes/.env
set +a
KEY=$MINIMAX_API_KEY
sed -i "s|YOUR_MINIMAX_API_KEY|$KEY|g" config.yaml
echo "API key injected. Starting agentgateway..."
./agentgateway -f config.yaml
