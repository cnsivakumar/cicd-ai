variable "workload" {
  type        = string
  description = "The name of the workload or application (e.g., 'myapp'). Used for naming conventions."
  default     = "pop25"
}

variable "environment" {
  type        = string
  description = "The deployment environment (e.g., 'dev', 'test', 'prod')."
  default     = "test"
}

variable "region_short" {
  type        = string
  description = "The short code for the Azure region (e.g., 'eus' for East US, 'wus' for West US)."
  default     = "sea"
}

variable "location" {
  type        = string
  description = "The full Azure region name where resources will be deployed (e.g., 'East US')."
  default     = "southeastasia"
}

variable "instance" {
  type        = string
  description = "The instance number or suffix to ensure storage account name uniqueness (e.g., '001')."
  default     = "001"
}

variable "owner" {
  type        = string
  description = "The team or individual responsible for managing these resources. Applied as a resource tag."
  default     = "siva"
}

variable "cost_center" {
  type        = string
  description = "The billing cost center code assigned to these resources. Applied as a resource tag."
  default     = "CC-8842-IT"
}
