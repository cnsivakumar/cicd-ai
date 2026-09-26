# AI-Assisted Azure CI/CD with MCP, n8n, Terraform and Azure DevOps

## Introduction

This project demonstrates an AI-assisted Azure CI/CD workflow combining **Azure DevOps, Terraform, MCP (Model Context Protocol), n8n, and Azure Container Apps**.

The goal is to introduce an automated validation layer before Terraform deployment. The MCP server validates Azure resource naming requirements, n8n orchestrates the validation workflow, and Azure DevOps controls Terraform deployment.

## Objective

The solution will:

1. Provision Azure infrastructure using Terraform.
2. Validate Azure resource names before deployment.
3. Host a custom MCP server in Azure Container Apps.
4. Use n8n Cloud as the workflow/orchestration layer.
5. Send validation requests from Azure DevOps to n8n.
6. Let n8n invoke the MCP validation service.
7. Return the validation result to Azure DevOps.
8. Continue with Terraform deployment only when validation passes.
9. Fail the pipeline when validation fails.

## Architecture

```text
Azure DevOps Pipeline
        |
        | HTTP POST
        v
    n8n Cloud
        |
        | HTTP Request
        v
MCP Validation Server
(Azure Container Apps)
        |
        | Azure Resource Manager
        v
Azure Resource Name Validation
        |
        +-------- PASS --------+
        |                      |
        +-------- FAIL         |
                 |             |
                 v             v
          n8n Response     Continue Pipeline
                 |             |
                 +-------------+
                         |
                         v
                 Terraform Plan
                         |
                         v
                 Terraform Apply
```

# 1. Prerequisites

The following components are required:

- Azure subscription
- Azure Resource Group
- Azure Container Registry (ACR)
- Azure Container Apps Environment
- Azure Container App for the MCP server
- Azure Storage Account for Terraform remote state
- Azure DevOps project/repository
- Azure DevOps service connection
- Appropriate Azure RBAC permissions
- n8n Cloud account

## Azure resources

Example names:

```text
Resource Group:             rg-ai-cicd-dev
Container Registry:         acrAICICD01
Container Apps Environment: cae-ai-cicd-dev
Storage Account:            terraformstgacc01
Blob Container:             terraformstate
Terraform State Key:        dev.terraform.tfstate
```

## n8n Cloud

Create an n8n Cloud account.

For this lab, n8n is used as the workflow orchestration layer.

Basic workflow:

```text
Webhook
   |
   v
HTTP Request
   |
   v
Respond to Webhook
```

> n8n trial availability and limits can change, so verify the current plan when creating the account.

# 2. Azure Identity and RBAC

Use identity-based authentication rather than storing Azure credentials in source code.

Recommended options:

- Workload Identity Federation (OIDC) for Azure DevOps
- Managed Identity for Azure Container Apps
- Azure RBAC with least privilege

## Terraform deployment identity

The identity used by Terraform needs permissions to create/update the resources defined in the Terraform code.

Assign permissions at the smallest practical scope.

## Terraform state identity

The identity used to access the Terraform state storage should have:

```text
Storage Blob Data Contributor
```

at the storage account or appropriate container scope.

## MCP Container App identity

Use a managed identity for the MCP Container App.

Grant only the permissions required by the MCP operations.

> `Reader` permission on a Container App is not automatically sufficient to deploy or update the Container App. Deployment permissions and runtime Azure permissions are separate concerns.

# 3. Repository Structure

Recommended repository structure:

```text
ai-azure-cicd/
|
+-- mcp-server/
|   +-- app.py
|   +-- requirements.txt
|   +-- Dockerfile
|
+-- terraform/
|   +-- main.tf
|   +-- variables.tf
|   +-- outputs.tf
|   +-- providers.tf
|   +-- backend.tf
|
+-- scripts/
|   +-- terraform-plan-json.sh
|
+-- azure-pipelines.yml
|
+-- skills.md
|
+-- README.md
```

# 4. MCP Server

The MCP server is a custom Python service built using FastMCP.

The initial tool validates whether an Azure resource name is available.

Example tool:

```text
check_resource_name_availability
```

## Example `app.py`

```python
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from azure.identity import DefaultAzureCredential
from azure.mgmt.resource.resources import ResourceManagementClient


mcp = FastMCP("Azure-Validator-Server")


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")


@mcp.tool()
async def check_resource_name_availability(
    subscription_id: str,
    resource_name: str,
    resource_type: str
) -> str:

    try:
        credential = DefaultAzureCredential()

        client = ResourceManagementClient(
            credential,
            subscription_id
        )

        result = client.providers.check_name_availability(
            {
                "name": resource_name,
                "type": resource_type
            }
        )

        if result.name_available:
            return (
                f"Success: The name '{resource_name}' is AVAILABLE "
                f"for resource type '{resource_type}'."
            )

        return (
            f"Unavailable: The name '{resource_name}' is taken. "
            f"Reason: {result.reason}. "
            f"Message: {result.message}"
        )

    except Exception as e:
        return f"Error executing check: {str(e)}"


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8000,
        stateless_http=True
    )
```

> FastMCP APIs can change between versions. If your installed version does not accept `stateless_http` in `run()`, use the configuration supported by that version.

## `requirements.txt`

Example:

```text
fastmcp>=4,<5
azure-identity
azure-mgmt-resource
```

For production, pin exact versions after testing.

# 5. Dockerfile

Example:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8000

CMD ["python", "app.py"]
```

Configure the Azure Container App to expose port:

```text
8000
```

# 6. MCP Health Check

Before connecting n8n, verify the Container App is running.

Endpoint:

```text
GET /health
```

Expected response:

```text
OK
```

This helps distinguish Container App deployment issues from n8n workflow issues.

# 7. Azure Resource Name Validation

The MCP tool receives:

```text
subscription_id
resource_name
resource_type
```

Example:

```json
{
  "subscription_id": "<subscription-id>",
  "resource_name": "myterraformstorage01",
  "resource_type": "Microsoft.Storage/storageAccounts"
}
```

Possible response:

```text
Success: The name 'myterraformstorage01' is AVAILABLE
```

or:

```text
Unavailable: The name 'myterraformstorage01' is taken
```

## Production consideration

Azure name-availability behavior is provider-specific. For a production implementation, consider provider-specific tools such as:

```text
check_storage_account_name
check_key_vault_name
check_container_registry_name
check_web_app_name
```

# 8. n8n Workflow

Recommended n8n workflow:

```text
Webhook
   |
   v
HTTP Request
   |
   v
Respond to Webhook
```

## Webhook request

Azure DevOps can send:

```json
{
  "repository": "ai-azure-cicd",
  "branch": "refs/heads/main",
  "commit": "$(Build.SourceVersion)",
  "environment": "dev",
  "resource_name": "myterraformstorage01",
  "resource_type": "Microsoft.Storage/storageAccounts"
}
```

## HTTP Request node

The HTTP Request node calls the MCP validation service.

The request contains the resource information received from Azure DevOps.

## Respond to Webhook

### PASS

```json
{
  "decision": "PASS",
  "message": "Validation successful",
  "checks": {
    "naming": "PASS"
  }
}
```

### FAIL

```json
{
  "decision": "FAIL",
  "message": "Azure resource name is unavailable",
  "checks": {
    "naming": "FAIL"
  }
}
```

# 9. Azure DevOps Pipeline

The pipeline is responsible for:

1. Checkout source code.
2. Build the MCP Docker image.
3. Push the image to ACR.
4. Deploy/update the MCP Container App.
5. Call the n8n webhook.
6. Read the validation response.
7. Stop the pipeline when validation fails.
8. Run Terraform init.
9. Run Terraform validate.
10. Run Terraform plan.
11. Run Terraform apply.

## Calling n8n

```yaml
- bash: |
    set -e

    HTTP_RESPONSE=$(curl -sS       -w "\n%{http_code}"       -X POST       "$(N8N_WEBHOOK_URL)"       -H "Content-Type: application/json"       -d '{
        "repository": "$(Build.Repository.Name)",
        "branch": "$(Build.SourceBranch)",
        "commit": "$(Build.SourceVersion)",
        "environment": "dev"
      }')

    HTTP_CODE=$(echo "$HTTP_RESPONSE" | tail -n 1)
    RESPONSE_BODY=$(echo "$HTTP_RESPONSE" | sed '$d')

    echo "HTTP Status: $HTTP_CODE"
    echo "n8n Response:"
    echo "$RESPONSE_BODY"

    echo "$RESPONSE_BODY" > n8n-response.json

    DECISION=$(echo "$RESPONSE_BODY" | jq -r '.decision')

    echo "Validation decision: $DECISION"

    echo "##vso[task.setvariable variable=N8N_DECISION]$DECISION"

  displayName: "Call n8n Validation"
  env:
    N8N_WEBHOOK_URL: $(N8N_WEBHOOK_URL)
```

Store the webhook URL as a secret pipeline variable.

## Validation decision

```yaml
- bash: |
    if [ "$(N8N_DECISION)" != "PASS" ]; then
      echo "n8n validation failed."
      exit 1
    fi

    echo "n8n validation passed."
    echo "Continuing with Terraform deployment."

  displayName: "Check Validation Result"
```

Result:

```text
PASS -> Terraform continues
FAIL -> Pipeline fails
```

# 10. Terraform Remote Backend

Example `backend.tf`:

```hcl
terraform {
  backend "azurerm" {
    use_oidc         = true
    use_azuread_auth = true

    tenant_id = "<TENANT-ID>"

    storage_account_name = "terraformstgacc01"
    container_name       = "terraformstate"
    key                  = "dev.terraform.tfstate"
  }
}
```

Replace `<TENANT-ID>` with the actual Microsoft Entra tenant ID.

Do not commit client secrets or passwords.

For Azure DevOps Workload Identity Federation, configure the Terraform AzureRM backend authentication consistently with the Azure DevOps service connection and the Terraform version being used.

# 11. Terraform Workflow

Recommended lifecycle:

```text
terraform init
       |
       v
terraform fmt
       |
       v
terraform validate
       |
       v
terraform plan
       |
       v
terraform apply
```

## Terraform Init and Validate

```yaml
- task: AzureCLI@3
  displayName: "Terraform Init and Validate"
  inputs:
    connectionType: "azureRM"
    azureSubscription: "sc-azure-ai-cicd"
    scriptType: "bash"
    scriptLocation: "inlineScript"
    inlineScript: |
      set -e

      cd terraform

      terraform init

      terraform fmt -check

      terraform validate
```

> `azureSubscription` is the Azure DevOps service connection name, not the Azure subscription ID.

## Terraform Plan

```yaml
- task: AzureCLI@3
  displayName: "Terraform Plan"
  inputs:
    connectionType: "azureRM"
    azureSubscription: "sc-azure-ai-cicd"
    scriptType: "bash"
    scriptLocation: "inlineScript"
    inlineScript: |
      set -e

      cd terraform

      terraform plan -out=tfplan

      terraform show tfplan
```

Publish `tfplan` as a pipeline artifact when plan and apply run in separate stages.

## Terraform Apply

```yaml
- task: AzureCLI@3
  displayName: "Terraform Apply"
  inputs:
    connectionType: "azureRM"
    azureSubscription: "sc-azure-ai-cicd"
    scriptType: "bash"
    scriptLocation: "inlineScript"
    inlineScript: |
      set -e

      cd terraform

      terraform apply -auto-approve tfplan
```

Using the saved plan ensures that the apply operation uses the reviewed plan.

# 12. Recommended Pipeline Stages

```text
Stage 1
-------
Build & Validate
       |
       v
MCP / n8n Validation
       |
       v
PASS?
  |
  +---- NO ---> Stop
  |
 YES
  |
  v

Stage 2
-------
Terraform Plan
       |
       v
Plan Artifact
       |
       v

Stage 3
-------
Approval
       |
       v
Terraform Apply
```

This provides a clean separation between validation, planning and deployment.

# 13. `skills.md`

Use `skills.md` as a governance/instruction layer for the AI-assisted workflow.

Example:

```markdown
# Azure Terraform Governance Rules

## Naming

- Resource names must follow the organization's naming convention.
- Resource names must be globally unique where Azure requires uniqueness.
- Do not generate random names unless explicitly required.

## Location

- Use approved Azure regions only.
- Default development region: East US.

## Security

- Do not create public resources unless explicitly approved.
- Prefer managed identities.
- Do not store credentials in Terraform code.
- Do not expose secrets in pipeline logs.

## Terraform

- Run terraform fmt.
- Run terraform validate.
- Run terraform plan before apply.
- Do not automatically apply if validation fails.

## Azure

- Use Azure RBAC.
- Follow least-privilege principles.
- Use remote Terraform state.
```

> `skills.md` should not be the only enforcement mechanism. Azure Policy, RBAC and security scanning should provide technical enforcement.

# 14. Terraform Plan JSON

Terraform can generate machine-readable plan information:

```bash
terraform show -json tfplan > tfplan.json
```

Possible future flow:

```text
Terraform Plan
      |
      v
terraform show -json
      |
      v
Plan JSON
      |
      v
AI / MCP Analysis
      |
      v
PASS / FAIL
```

# 15. Security Considerations

Recommended practices:

- Use Workload Identity Federation instead of long-lived service principal secrets.
- Use managed identity for the MCP Container App.
- Store Terraform state remotely.
- Assign `Storage Blob Data Contributor` only where required.
- Use least-privilege Azure RBAC.
- Store n8n webhook URLs as secret pipeline variables.
- Never commit secrets, passwords or access tokens.
- Restrict the MCP endpoint where possible.
- Enable logging and monitoring.
- Consider Azure Policy and Defender for Cloud for additional controls.

# 16. Why MCP?

MCP provides a structured way to expose reusable capabilities as tools.

Instead of putting all Azure validation logic directly into the CI/CD pipeline, the pipeline can call reusable MCP tools.

Example:

```text
Azure DevOps
     |
     v
    n8n
     |
     v
    MCP
     |
     +---- check resource name
     |
     +---- security validation
     |
     +---- policy validation
     |
     +---- cost validation
```

Additional tools can be introduced without significantly changing the Azure DevOps pipeline.

# 17. Why n8n?

n8n provides a visual workflow orchestration layer.

It can connect:

- Azure DevOps
- MCP services
- HTTP APIs
- AI models
- Notifications
- Approval workflows
- External systems

For this lab, n8n orchestrates the workflow while Azure DevOps remains responsible for Terraform execution.

# 18. Complete End-to-End Workflow

```text
Developer
    |
    v
Git Push
    |
    v
Azure DevOps
    |
    +-----------------------------+
    |                             |
    v                             |
Build MCP Image                   |
    |                             |
    v                             |
Push Image to ACR                 |
    |                             |
    v                             |
Deploy MCP Container App          |
    |                             |
    v                             |
Call n8n Webhook -----------------+
    |
    v
n8n Workflow
    |
    v
HTTP Request
    |
    v
MCP Server
    |
    v
Azure Resource Manager
    |
    v
Resource Validation
    |
    +---------- PASS -----------+
    |                           |
    |                           v
    |                    n8n Response
    |                           |
    |                           v
    |                    Azure DevOps
    |                           |
    |                           v
    |                    Terraform Init
    |                           |
    |                           v
    |                    Terraform Validate
    |                           |
    |                           v
    |                    Terraform Plan
    |                           |
    |                           v
    |                    Terraform Apply
    |
    +---------- FAIL ----------+
                                |
                                v
                         Pipeline Failed
```

# 19. Future Enhancements

## AI Agent

Add an AI Agent in n8n to analyze Terraform changes.

```text
Terraform Plan
      |
      v
Plan JSON
      |
      v
AI Agent
      |
      +---- Security analysis
      |
      +---- Cost analysis
      |
      +---- Naming analysis
      |
      +---- Architecture analysis
      |
      v
Recommendation
```

## Security Scanning

Possible integrations:

- Checkov
- Trivy
- SonarQube
- Microsoft Defender for Cloud
- Azure Policy

Example:

```text
Terraform
   |
   +---- terraform validate
   |
   +---- Checkov
   |
   +---- Trivy
   |
   +---- Azure Policy
   |
   +---- MCP validation
   |
   v
PASS / FAIL
```

## Pull Request Validation

```text
Pull Request
     |
     v
Azure DevOps
     |
     v
Terraform Plan
     |
     v
AI / MCP Validation
     |
     v
PR Status
```

# 20. Technology Stack

| Technology | Purpose |
|---|---|
| Azure DevOps | Source control and CI/CD |
| Terraform | Infrastructure as Code |
| Azure | Cloud platform |
| Azure Container Apps | MCP server hosting |
| Azure Container Registry | Docker image registry |
| Azure Blob Storage | Terraform remote state |
| MCP / FastMCP | Tool-based validation service |
| n8n Cloud | Workflow orchestration |
| Python | MCP server implementation |
| Azure SDK | Azure resource validation |
| Workload Identity Federation | Azure DevOps authentication |
| Managed Identity | Azure workload authentication |
| `skills.md` | AI/governance instructions |

# 21. Expected Result

## Valid resource

```text
Developer
   |
   v
Azure DevOps
   |
   v
n8n
   |
   v
MCP
   |
   v
Validation = PASS
   |
   v
Terraform Plan
   |
   v
Terraform Apply
   |
   v
Azure Resources Created
```

## Invalid resource

```text
Developer
   |
   v
Azure DevOps
   |
   v
n8n
   |
   v
MCP
   |
   v
Validation = FAIL
   |
   v
Pipeline Stops
```

Terraform Apply is not executed when validation fails.

# 22. Conclusion

This project demonstrates a practical pattern for combining **AI-assisted workflows, MCP, n8n, Terraform, Azure DevOps and Azure**.

Responsibilities are separated as follows:

- **Azure DevOps** controls CI/CD and Terraform execution.
- **Terraform** manages infrastructure.
- **MCP** exposes reusable Azure validation capabilities.
- **n8n** orchestrates the workflow.
- **Azure Container Apps** hosts the MCP service.
- **Azure RBAC and managed identities** provide secure access.
- **`skills.md`** provides governance and instructions for AI-assisted decisions.

The architecture can be extended into a broader **AI-powered Platform Engineering** solution with security, cost, compliance, architecture and Terraform plan analysis.
