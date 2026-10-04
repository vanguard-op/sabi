# API enablement. The stack owns the services it needs so a fresh project can be
# built from this configuration alone, rather than depending on an operator having
# enabled each API out-of-band. `disable_on_destroy = false` keeps a `destroy`
# from disabling shared APIs (Cloud Resource Manager in particular) that the
# project continues to need.
#
# Enablement is deliberately a prerequisite for the rest: every resource that
# depends on one of these APIs references the corresponding service resource, so
# Terraform orders creation after the API is live.

locals {
  required_services = toset([
    "cloudresourcemanager.googleapis.com", # project IAM policies and bindings
    "iam.googleapis.com",                  # service accounts and WIF
    "iamcredentials.googleapis.com",       # service-account token minting
    "run.googleapis.com",                  # Cloud Run services, jobs, domain mapping
    "sqladmin.googleapis.com",             # Cloud SQL
    "compute.googleapis.com",              # VPC, subnet, firewall, private services access
    "servicenetworking.googleapis.com",    # private services access peering
    "secretmanager.googleapis.com",        # Secret Manager
    "artifactregistry.googleapis.com",     # image registry
    "cloudbuild.googleapis.com",           # image builds
  ])
}

resource "google_project_service" "required" {
  for_each = local.required_services

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
