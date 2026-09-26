terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.110"
    }
  }
}

provider "azurerm" {
  features {}
}

data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "this" {
  name     = "rg-${var.workload}-${var.environment}-${var.region_short}"
  location = var.location

  tags = local.tags
}

resource "azurerm_storage_account" "this" {
  name                     = "st${var.workload}${var.environment}${var.region_short}${var.instance}"
  resource_group_name      = azurerm_resource_group.this.name
  location                 = azurerm_resource_group.this.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  tags = local.tags
}

resource "azurerm_key_vault" "this" {
  name                        = "kv${var.workload}${var.environment}${var.region_short}${var.instance}"
  location                    = azurerm_resource_group.this.location
  resource_group_name         = azurerm_resource_group.this.name
  enabled_for_disk_encryption = true
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  soft_delete_retention_days  = 7
  purge_protection_enabled    = false

  sku_name = "standard"

  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id

    key_permissions = [
      "Get",
    ]

    secret_permissions = [
      "Get",
    ]

    storage_permissions = [
      "Get",
    ]
  }
}
resource "azurerm_service_plan" "app_plan" {
  name                = "asp-webapp-demo"
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_resource_group.this.location
  os_type             = "Linux"
  sku_name            = "F1" # Production ready Tier. Use F1 for Free, B1 for Basic
}

# 4. Create the Linux Web App
resource "azurerm_linux_web_app" "web_app" {
  name                = "app${var.workload}${var.environment}${var.region_short}${var.instance}" # Must be globally unique
  resource_group_name = azurerm_resource_group.this.name
  location            = azurerm_service_plan.app_plan.location
  service_plan_id     = azurerm_service_plan.app_plan.id

  site_config {

    always_on = false
    # Configure your runtime environment (e.g., Node, Python, .NET, Docker)
    application_stack {
      node_version = "20-lts"
    }
  }

  app_settings = {
    "WEBSITE_RUN_FROM_PACKAGE" = "1"
    "ENVIRONMENT"              = "Production"
  }

}

locals {
  tags = {
    Environment = var.environment
    Owner       = var.owner
    CostCenter  = var.cost_center
  }
}
