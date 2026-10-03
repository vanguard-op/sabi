# Migration jobs. The database has a private IP only, so a GitHub runner cannot
# reach it directly; Alembic runs inside the VPC as a Cloud Run job using the
# same image, secrets, and egress as the service. The `up` workflow executes
# these after `terraform apply` and before traffic (route: "run Alembic
# migrations against the primary store").
#
# One job per store, because each store has its own migration tree and its own
# transaction boundary (the primary store and the isolated payment store).

resource "google_cloud_run_v2_job" "migrate_primary" {
  # Created only once the api image exists (D-036); Cloud Run jobs, like
  # services, reject an image that is not yet in Artifact Registry.
  count = var.deploy_workloads ? 1 : 0

  name                = "${local.prefix}-migrate-primary"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.api.email

      vpc_access {
        network_interfaces {
          network    = google_compute_network.main.id
          subnetwork = google_compute_subnetwork.run.id
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
      }
    }
  }

  depends_on = [google_secret_manager_secret_version.database_url]
}

resource "google_cloud_run_v2_job" "migrate_payments" {
  # See migrate_primary: gated on the images existing (D-036).
  count = var.deploy_workloads ? 1 : 0

  name                = "${local.prefix}-migrate-payments"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.payments.email

      vpc_access {
        network_interfaces {
          network    = google_compute_network.main.id
          subnetwork = google_compute_subnetwork.run.id
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
