# Cloud Run services. Each service is a container image built from its existing
# service root and pushed to Artifact Registry by the `up` workflow. Cloud Run
# serves directly; TLS comes from Cloud Run domain mapping (D-032), never a load
# balancer.
#
# Private services (ai, payments) are reached only through the API gateway and are
# created without public unauthenticated access; the gateway's service account is
# the only principal granted run.invoker on them (see iam.tf).
#
# The private services are a separate resource from the public ones because the
# API gateway's environment names the private service URLs. Referencing a sibling
# inside one for_each resource would be a cycle; splitting them makes the
# dependency one-directional (gateway -> private services).

locals {
  # Private services: never reachable from the internet, invoked only by the
  # gateway's service account.
  private_services = {
    ai = {
      name      = "ai"
      image_key = "ai"
      port      = 8001
      sa        = "ai"
    }
    payments = {
      name      = "payments"
      image_key = "payments"
      port      = 8002
      sa        = "payments"
    }
  }

  # Public services: reachable from the internet. The gateway serves the client
  # and channels; the console serves staff. Reached directly, not through the
  # private services.
  public_services = {
    api = {
      name      = "api"
      image_key = "api"
      port      = 8000
      sa        = "api"
    }
    console = {
      name      = "console"
      image_key = "console"
      port      = 8080
      sa        = "console"
    }
  }

  # Per-service log level and environment; the one place non-secret runtime
  # configuration is stated.
  common_env = {
    ENVIRONMENT = var.environment
    LOG_LEVEL   = "info"
  }

  # Secret references: Cloud Run mounts these from Secret Manager at revision
  # start. The subset per service matches the IAM grants in iam.tf, so a service
  # is never handed a secret it cannot read.
  secret_env = {
    SESSION_SECRET          = google_secret_manager_secret.app["SESSION_SECRET"].secret_id
    RECOVERY_CODE_PEPPER    = google_secret_manager_secret.app["RECOVERY_CODE_PEPPER"].secret_id
    MANDATE_SIGNING_KEY     = google_secret_manager_secret.app["MANDATE_SIGNING_KEY"].secret_id
    GEMINI_API_KEY          = google_secret_manager_secret.app["GEMINI_API_KEY"].secret_id
    PAYMENT_RAIL_CREDENTIAL = google_secret_manager_secret.app["PAYMENT_RAIL_CREDENTIAL"].secret_id
    DATABASE_URL            = google_secret_manager_secret.app["DATABASE_URL"].secret_id
    PAYMENTS_DATABASE_URL   = google_secret_manager_secret.app["PAYMENTS_DATABASE_URL"].secret_id
  }

  api_secret_env = {
    SESSION_SECRET        = local.secret_env.SESSION_SECRET
    RECOVERY_CODE_PEPPER  = local.secret_env.RECOVERY_CODE_PEPPER
    DATABASE_URL          = local.secret_env.DATABASE_URL
    PAYMENTS_DATABASE_URL = local.secret_env.PAYMENTS_DATABASE_URL
  }

  payments_secret_env = {
    MANDATE_SIGNING_KEY   = local.secret_env.MANDATE_SIGNING_KEY
    PAYMENTS_DATABASE_URL = local.secret_env.PAYMENTS_DATABASE_URL
  }

  ai_secret_env = {
    GEMINI_API_KEY = local.secret_env.GEMINI_API_KEY
  }
}

# Session and rate-limit store selection for the API gateway, environment-driven
# so no code change is needed to move between environments. Staging runs with no
# Memorystore (D-032), so the stores must be an explicit in-memory choice or the
# settings validator refuses the first boot; production supplies a cache_url, so
# "auto" resolves to redis there. Only the API gateway keeps session state.
locals {
  store_env = var.environment == "staging" ? {
    SESSION_STORE_BACKEND    = "memory"
    RATE_LIMIT_STORE_BACKEND = "memory"
  } : {}
}

# The gateway's environment, resolved after the private services exist. Kept in
# its own local so it can name their Cloud Run URLs without a cycle.
#
locals {
  api_env = merge(
    {
      AI_BASE_URL       = google_cloud_run_v2_service.private_services["ai"].uri
      PAYMENTS_BASE_URL = google_cloud_run_v2_service.private_services["payments"].uri
      # WebAuthn staging relying party (route staging config).
      WEBAUTHN_RP_ID   = local.services["api"].host
      WEBAUTHN_RP_NAME = "Sabi"
      WEBAUTHN_ORIGIN  = "https://${local.services["api"].host}"
      # Association files served from this origin (FEAT-001). Android needs the
      # app package and every signing-certificate SHA-256; iOS needs the
      # <TeamID>.<bundle> app id. Empty values make the file 404 rather than
      # advertise an app the origin cannot vouch for.
      ANDROID_PACKAGE_NAME      = var.android_package_name
      ANDROID_CERT_FINGERPRINTS = jsonencode(var.android_cert_fingerprints)
      APPLE_APP_ID              = var.apple_app_id
    },
    local.store_env,
  )
}

# --- Private services ------------------------------------------------------------

resource "google_cloud_run_v2_service" "private_services" {
  for_each = local.private_services

  name                = "${local.prefix}-${each.value.name}"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = local.service_account_emails[each.value.sa]

    # Direct VPC egress to the private-IP Cloud SQL instance; external calls use
    # the internet without a VPC hop.
    vpc_access {
      network_interfaces {
        network    = data.google_compute_network.main.id
        subnetwork = data.google_compute_subnetwork.run.id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    max_instance_request_concurrency = 80

    scaling {
      min_instance_count = 0
      max_instance_count = (
        each.key == "ai" ? var.ai_max_instances : var.payments_max_instances
      )
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}/${each.value.image_key}:${var.container_image_tag}"

      ports {
        container_port = each.value.port
      }

      dynamic "env" {
        for_each = merge(
          local.common_env,
          each.key == "payments" ? { RAIL_BACKEND = "disabled" } : {},
        )
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = each.key == "ai" ? local.ai_secret_env : local.payments_secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      startup_probe {
        http_get {
          path = "/health"
          port = each.value.port
        }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 12
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_version.payments_database_url,
    google_secret_manager_secret_version.placeholder,
    google_project_iam_member.payments_sql_client,
  ]
}

# --- Public services -------------------------------------------------------------

resource "google_cloud_run_v2_service" "public_services" {
  for_each = local.public_services

  name                = "${local.prefix}-${each.value.name}"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = local.service_account_emails[each.value.sa]

    vpc_access {
      network_interfaces {
        network    = data.google_compute_network.main.id
        subnetwork = data.google_compute_subnetwork.run.id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    max_instance_request_concurrency = 80

    scaling {
      min_instance_count = each.key == "api" ? var.api_min_instances : 0
      max_instance_count = (
        each.key == "api" ? var.api_max_instances : var.console_max_instances
      )
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}/${each.value.image_key}:${var.container_image_tag}"

      ports {
        container_port = each.value.port
      }

      dynamic "env" {
        for_each = merge(
          local.common_env,
          each.key == "api" ? local.api_env : {},
        )
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = each.key == "api" ? local.api_secret_env : {}
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      startup_probe {
        http_get {
          path = "/health"
          port = each.value.port
        }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 12
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_version.payments_database_url,
    google_secret_manager_secret_version.placeholder,
    google_project_iam_member.api_sql_client,
  ]
}
