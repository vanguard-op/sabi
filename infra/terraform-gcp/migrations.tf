# Migration and seed jobs. The database has a private IP only, so a GitHub
# runner cannot reach it directly; Alembic runs inside the VPC as a Cloud Run job
# using the same image, secrets, and egress as the service. The `up` workflow
# executes these after `terraform apply` and before traffic (route: "run Alembic
# migrations against the primary store").
#
# One job per store, because each store has its own migration tree and its own
# transaction boundary (the primary store and the isolated payment store). The
# catalogue seed is a third job: it runs against the primary store, so it shares
# that store's transaction boundary but keeps its own entrypoint.

resource "google_cloud_run_v2_job" "migrate_primary" {
  name                = "${local.prefix}-migrate-primary"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.api.email

      vpc_access {
        network_interfaces {
          network    = data.google_compute_network.main.id
          subnetwork = data.google_compute_subnetwork.run.id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}/api:${var.container_image_tag}"

        # Ensure pgvector exists (the retrieval index needs it, D-003), then run
        # `alembic upgrade head` — the same command `make migrate` runs. The
        # extension is installed here because the staged databases are created
        # empty and the migrations do not create extensions.
        command = ["sh", "-c"]
        args = [
          "python -c \"import os,sqlalchemy as sa; c=sa.create_engine(os.environ['DATABASE_URL']).connect(); c.exec_driver_sql('CREATE EXTENSION IF NOT EXISTS vector'); c.commit()\" && alembic upgrade head",
        ]

        env {
          name  = "ENVIRONMENT"
          value = var.environment
        }
        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.app["DATABASE_URL"].secret_id
              version = "latest"
            }
          }
        }
        env {
          name = "PAYMENTS_DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.app["PAYMENTS_DATABASE_URL"].secret_id
              version = "latest"
            }
          }
        }
        # `alembic` imports `app.core.config.get_settings()`, which validates the
        # whole application configuration, not just the database URL. The job
        # therefore carries the same session secrets and explicit store selection
        # the API service does, or the settings validator refuses to build.
        env {
          name = "SESSION_SECRET"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.app["SESSION_SECRET"].secret_id
              version = "latest"
            }
          }
        }
        env {
          name = "RECOVERY_CODE_PEPPER"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.app["RECOVERY_CODE_PEPPER"].secret_id
              version = "latest"
            }
          }
        }
        dynamic "env" {
          for_each = local.store_env
          content {
            name  = env.key
            value = env.value
          }
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_version.generated,
  ]
}

# The version-controlled catalogue load (D-048/D-049). Mirrors `migrate_primary`
# exactly: the same `api` image and tag, service account, VPC egress, and
# environment, because `scripts.seed_catalogue` imports the same settings
# validator (`app.core.config.get_settings`) and opens the same primary store. It
# runs on every `up`; the loader upserts by `name + collecting_body`, so a re-run
# creates nothing (idempotent). Keeping it Terraform-managed means a `destroy`
# removes it and a fresh `up` recreates it, unlike the ad-hoc job it replaces.
resource "google_cloud_run_v2_job" "seed_catalogue" {
  name                = "${local.prefix}-seed-catalogue"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.api.email

      vpc_access {
        network_interfaces {
          network    = data.google_compute_network.main.id
          subnetwork = data.google_compute_subnetwork.run.id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}/api:${var.container_image_tag}"

        # Runs from the image's working directory (`/srv/services/api`, set by
        # api.Dockerfile), so `--file data/catalogue.json` resolves to the
        # version-controlled catalogue the image already contains.
        command = ["python", "-m", "scripts.seed_catalogue"]
        args    = ["--file", "data/catalogue.json"]

        env {
          name  = "ENVIRONMENT"
          value = var.environment
        }
        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.app["DATABASE_URL"].secret_id
              version = "latest"
            }
          }
        }
        # `scripts.seed_catalogue` imports `app.core.config.get_settings()`, which
        # validates the whole application configuration, not just the database
        # URL. The job therefore carries the same session secrets and explicit
        # store selection the API service and `migrate_primary` do, or the
        # settings validator refuses to build.
        env {
          name = "SESSION_SECRET"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.app["SESSION_SECRET"].secret_id
              version = "latest"
            }
          }
        }
        env {
          name = "RECOVERY_CODE_PEPPER"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.app["RECOVERY_CODE_PEPPER"].secret_id
              version = "latest"
            }
          }
        }
        dynamic "env" {
          for_each = local.store_env
          content {
            name  = env.key
            value = env.value
          }
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_version.generated,
  ]
}

resource "google_cloud_run_v2_job" "migrate_payments" {
  name                = "${local.prefix}-migrate-payments"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.payments.email

      vpc_access {
        network_interfaces {
          network    = data.google_compute_network.main.id
          subnetwork = data.google_compute_subnetwork.run.id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }

      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}/payments:${var.container_image_tag}"

        command = ["alembic"]
        args    = ["upgrade", "head"]

        env {
          name  = "ENVIRONMENT"
          value = var.environment
        }
        env {
          name = "PAYMENTS_DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.app["PAYMENTS_DATABASE_URL"].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [google_secret_manager_secret_version.payments_database_url]
}
