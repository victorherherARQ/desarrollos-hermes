#!/bin/bash
# inject_key.sh — reads MINIMAX_API_KEY from ~/.hermes/.env and injects into config.yaml
KEY=$(grep "^MINIMAX_API_KEY" ~/.hermes/.env | grep -v "^#" | cut -d= -f2-)
echo "Key length: ${#KEY}"
sed -i "s|MINI_PLACEHOLDER|$KEY|g" config.yaml
grep "apiKey" config.yaml
