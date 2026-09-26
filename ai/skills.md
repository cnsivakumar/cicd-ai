# Azure Naming & Governance Skill

This file is the single source of truth for pre-create validation. It is
read by humans AND by the n8n workflow (`n8n/validate-terraform-workflow.json`,
node "Apply Governance Rules"). If you change a rule, update it in **both**
places — see README for the AI-agent upgrade path that removes this duplication.

## 1. Naming conventions

Pattern: `<prefix><workload><env><region-short><instance>` (no separators
inside the prefix group where Azure disallows hyphens, e.g. storage).

| resource_type       | Azure prefix | Regex                          | Example                |
|----------------------|--------------|----------------------------------|-------------------------|
| storage_account       | st           | `^st[a-z0-9]{3,17}$`             | `stinvoiceprodin01`     |
| key_vault              | kv           | `^kv-[a-z0-9-]{1,20}$`           | `kv-invoice-prod-in`    |
| container_registry    | acr          | `^acr[a-zA-Z0-9]{2,47}$`         | `acrinvoiceprod`        |
| web_app                | app          | `^app-[a-z0-9-]{1,20}$`          | `app-invoice-api-prod`  |
| sql_server              | sql          | `^sql-[a-z0-9-]{1,20}$`          | `sql-invoice-prod-in`   |
| cosmos_db               | cosmos       | `^cosmos-[a-z0-9-]{1,20}$`       | `cosmos-invoice-prod`   |
| resource_group          | rg           | `^rg-[a-z0-9-]{1,30}$`           | `rg-invoice-prod-in`    |

## 2. Required tags (all resources)

- `Environment` — one of `dev`, `test`, `prod`
- `Owner` — an email address
- `CostCenter` — non-empty

## 3. Region allow-list

- `centralindia`
- `southindia`
- `southeastasia`

(Extend this list deliberately — it exists to stop resources landing in a
region nobody's paying attention to.)

## 4. Pre-create checklist (what "pass" means)

A resource passes validation only if **all** of the following are true:

- [ ] Name matches the naming convention regex for its resource_type
- [ ] Name is confirmed available via Azure's `checkNameAvailability` API
- [ ] `Environment`, `Owner`, `CostCenter` tags are present and valid
- [ ] `region` is in the allow-list

Any failure blocks the pipeline before `terraform apply` runs.
