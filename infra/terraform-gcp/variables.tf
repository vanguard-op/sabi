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

variable "root_domain" {
  description = "Root domain whose subdomains host the environment; the apex is untouched (D-032)."
  type        = string
  default     = "ahmadkhidir.com"
}

variable "artifact_registry_repo_id" {
  description = "Artifact Registry repository id for the service images."
  type        = string
  default     = "sabi"
}

variable "db_tier" {
  description = "Cloud SQL machine tier. Shared-core keeps HDD storage available (General purpose series)."
  type        = string
  default     = "db-f1-micro"
}

variable "db_allocated_storage" {
  description = "Allocated storage (GiB) for the Postgres instance."
  type        = number
  default     = 10
}

variable "db_disk_type" {
  description = "Cloud SQL data disk type. HDD is required by the route."
  type        = string
  default     = "PD_HDD"

  validation {
    condition     = contains(["PD_HDD", "PD_SSD"], var.db_disk_type)
    error_message = "db_disk_type must be PD_HDD or PD_SSD."
  }
}

# Whether to create the Cloud Run workloads (services, jobs, their IAM, and the
# domain mappings). False by default so the bootstrap apply can create the
# platform — Artifact Registry, Cloud SQL, secrets, network — before any image
# exists; Cloud Run rejects an image that is not yet pushed, so the workloads are
# created by the second apply once the images are in the registry (D-036).
variable "deploy_workloads" {
  description = "Create the Cloud Run services, jobs, IAM, and domain mappings."
  type        = bool
  default     = false
}

# Private-service sizing. These default to zero so the environment costs nothing
# while stopped; the `up` workflow raises them when it deploys (D-033).
variable "api_min_instances" {
  description = "Minimum Cloud Run instances for the API gateway."
  type        = number
  default     = 0
}

variable "api_max_instances" {
  description = "Maximum Cloud Run instances for the API gateway."
  type        = number
  default     = 4
}

variable "ai_max_instances" {
  description = "Maximum Cloud Run instances for the AI service."
  type        = number
  default     = 3
}

variable "payments_max_instances" {
  description = "Maximum Cloud Run instances for the payment module."
  type        = number
  default     = 3
}

variable "console_max_instances" {
  description = "Maximum Cloud Run instances for the operations console."
  type        = number
  default     = 2
}

variable "container_image_tag" {
  description = "Image tag deployed by the lifecycle workflows; set by the `up` workflow, never a real secret."
  type        = string
  default     = "latest"
}
