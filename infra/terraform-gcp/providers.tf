provider "google" {
  project = var.project_id
  region  = var.region

  default_labels = local.labels
}

locals {
  # Staging environment naming. Kept beside the AWS stack (infra/terraform/) so
  # the existing AWS baseline is not touched; this stack is the hosted staging
  # environment of D-032/D-033.
  prefix = "${var.project}-${var.environment}"

  labels = {
    project     = var.project
    environment = var.environment
    managed-by  = "terraform"
  }

  # Every hosted environment serves on a subdomain of sabi.ahmadkhidir.com; the
  # apex ahmadkhidir.com is not touched (D-032).
  base_domain = "sabi.${var.root_domain}"

  # Stable Cloud Run service names, computed without referencing the resources so
  # IAM and domain mappings can name a service without depending on its
  # definition. `up` workflow and outputs use the same prefix rule.
  service_names = {
    for k, v in {
      api      = { name = "api" }
      ai       = { name = "ai" }
      payments = { name = "payments" }
      console  = { name = "console" }
    } : k => "${local.prefix}-${v.name}"
  }

  # The Cloud Run services deployed by this stack. The AI service and the
  # payment module are reached only through the API gateway, so they are created
  # without public unauthenticated invocation (architecture.md, "API Gateway /
  # Backend-for-Frontend", "Payment Module"; route note on private services).
  services = {
    api = {
      name      = "api"
      host      = "api.${local.base_domain}"
      public    = true
      image_key = "api"
      port      = 8000
    }
    ai = {
      name      = "ai"
      host      = "ai.${local.base_domain}"
      public    = false
      image_key = "ai"
      port      = 8001
    }
    payments = {
      name      = "payments"
      host      = "pay.${local.base_domain}"
      public    = false
      image_key = "payments"
      port      = 8002
    }
    console = {
      name      = "console"
      host      = "console.${local.base_domain}"
      public    = true
      image_key = "console"
      port      = 8080
    }
  }
}
