#!/usr/bin/env python3
import os

# Read the API key from hermes env
api_key = None
with open('/home/vhdez/.hermes/.env') as f:
    for line in f:
        line = line.strip()
        if line.startswith('MINIMAX_API_KEY') and not line.startswith('#'):
            api_key = line.split('=', 1)[1]
            break

if not api_key:
    print("ERROR: MINIMAX_API_KEY not found in ~/.hermes/.env")
    exit(1)

# Read and patch config
with open('/home/vhdez/desarrollos-hermes/agentgateway-poc/config.yaml') as f:
    content = f.read()

content = content.replace('MINI_PLACEHOLDER', api_key)

with open('/home/vhdez/desarrollos-hermes/agentgateway-poc/config.yaml', 'w') as f:
    f.write(content)

print(f"OK: key injected ({len(api_key)} chars, starts with {api_key[:6]})")
