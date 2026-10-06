variable "project" {
  description = "Resource name prefix."
  type        = string
  default     = "sabi"
}

variable "project_id" {
  description = "GCP project id the staging environment is provisioned in (D-032)."
  type        = string
  default     = "sabi-hq"
}

variable "environment" {
  description = "Deployment environment (architecture.md, Environments)."
  type        = string
  default     = "staging"

  validation {
    condition     = contains(["staging", "prod"], var.environment)
    error_message = "environment must be one of: staging, prod."
  }
}

variable "region" {
  description = "GCP region for every resource (D-032)."
  type        = string
  default     = "us-central1"
}
