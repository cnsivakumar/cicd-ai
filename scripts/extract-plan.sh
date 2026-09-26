#!/usr/bin/env bash
# Runs terraform plan, then extracts every resource about to be CREATED into
# a simplified JSON payload for the n8n validation webhook.
#
# Usage: ./extract-plan.sh > payload.json
set -euo pipefail

for v in ARM_CLIENT_ID ARM_CLIENT_SECRET ARM_TENANT_ID ARM_SUBSCRIPTION_ID; do
  if [ -z "${!v:-}" ]; then
    echo "ERROR: $v is not set. Export ARM_CLIENT_ID/ARM_CLIENT_SECRET/ARM_TENANT_ID/ARM_SUBSCRIPTION_ID" >&2
    echo "       before running this script (see the pipeline's terraform-auth variable group)." >&2
    exit 1
  fi
done

cd "$(dirname "$0")/../terraform"

terraform init -input=false -no-color -backend-config="use_azuread_auth=true" >/dev/null
terraform plan -input=false -out=tfplan -no-color >/dev/null
terraform show -json tfplan > plan.json


# Map Terraform azurerm_* types to the resource_type keys the MCP server
# and skills.md use. Extend this map as you add resource types.
jq '
  def type_map:
    {
      "azurerm_storage_account":      "storage_account",
      "azurerm_key_vault":            "key_vault",
      "azurerm_container_registry":   "container_registry",
      "azurerm_linux_web_app":        "web_app",
      "azurerm_windows_web_app":      "web_app",
      "azurerm_mssql_server":         "sql_server",
      "azurerm_cosmosdb_account":     "cosmos_db"
    };
  {
    resources: [
      .resource_changes[]
      | select(.change.actions == ["create"])
      | select(.type as $t | type_map | has($t))
      | {
          address: .address,
          resource_type: (type_map[.type]),
          name: .change.after.name,
          tags: (.change.after.tags // {}),
          region: (.change.after.location // null)
        }
    ]
  }
' plan.json

rm -f tfplan plan.json