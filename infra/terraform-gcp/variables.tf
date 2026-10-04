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

# --- Passkey association (FEAT-001) ------------------------------------------
# The RP origin serves /.well-known/assetlinks.json and
# /.well-known/apple-app-site-association so each platform can verify the app
# belongs to the domain. Without a match a ceremony fails with
# `domain-not-associated` before any credential is created.

variable "android_package_name" {
  description = "Android application id the relying-party origin vouches for."
  type        = string
  default     = "ng.sabi.sabi_mobile"
}

variable "android_cert_fingerprints" {
  description = <<-EOT
    SHA-256 fingerprint of every certificate the Android app is signed with
    (debug, upload, and Play App Signing), uppercase, colon-separated. A build
    signed with a key that is not listed here cannot complete a ceremony.
  EOT
  type        = list(string)
  default     = []
}

variable "apple_app_id" {
  description = "Apple app identifier for webcredentials, as <TeamID>.<bundle id>."
  type        = string
  default     = ""
}
