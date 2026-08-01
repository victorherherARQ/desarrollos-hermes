#!/bin/bash
set -e

KEYCLOAK_URL="http://localhost:8180"
KEYCLOAK_ADMIN="admin"
KEYCLOAK_ADMIN_PASSWORD="admin"
REALM_NAME="ciba-realm"
IMPORT_FILE="/opt/keycloak/data/import/ciba-realm.json"
MAX_RETRIES=60
RETRY_INTERVAL=5

echo "Waiting for Keycloak to be available at ${KEYCLOAK_URL}..."

retry_count=0
until curl -sf "${KEYCLOAK_URL}/health/ready" > /dev/null 2>&1 || \
     curl -sf "${KEYCLOAK_URL}/realms/master" > /dev/null 2>&1; do
    retry_count=$((retry_count + 1))
    if [ $retry_count -ge $MAX_RETRIES ]; then
        echo "Keycloak did not become available in time. Exiting."
        exit 1
    fi
    echo "Attempt ${retry_count}/${MAX_RETRIES}: Keycloak not ready, waiting ${RETRY_INTERVAL}s..."
    sleep $RETRY_INTERVAL
done

echo "Keycloak is up! Proceeding with realm configuration..."

# Login to Keycloak admin
echo "Logging into Keycloak admin..."
/opt/keycloak/bin/kcadm.sh config credentials --server "${KEYCLOAK_URL}" --realm master --user "${KEYCLOAK_ADMIN}" --password "${KEYCLOAK_ADMIN_PASSWORD}" --client admin-cli

# Create or update the realm
echo "Creating/updating realm '${REALM_NAME}'..."
if /opt/keycloak/bin/kcadm.sh get realms/${REALM_NAME} 2>/dev/null; then
    echo "Realm '${REALM_NAME}' already exists. Updating..."
    /opt/keycloak/bin/kcadm.sh update realms/${REALM_NAME} -s enabled=true -s CIBAEnabled=true -s backchannelTokenDeliveryMode=poll -s expiresIn=300 -s backchannelAuthRequestSigningAlg=PS256 -f "${IMPORT_FILE}"
else
    echo "Creating new realm '${REALM_NAME}'..."
    /opt/keycloak/bin/kcadm.sh create realms -f "${IMPORT_FILE}"
fi

echo "Realm '${REALM_NAME}' configuration complete!"
echo ""
echo "CIBA client credentials:"
echo "  Client ID: ciba-agent"
echo "  Client Secret: ciba-agent-secret"
echo ""
echo "Test user:"
echo "  Username: testuser"
echo "  Password: testuser"
