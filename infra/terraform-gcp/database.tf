# Cloud SQL Postgres 16 instance carrying both stores as separate databases:
# the primary store and the isolated payment records store. The payment store is
# a separate database from the primary, satisfying the isolation the API's
# settings validator enforces.
#
# Edition is pinned to ENTERPRISE with a shared-core tier because HDD storage is
# only available on the general purpose shared/dedicated core machine series;
# Postgres 16 otherwise defaults to ENTERPRISE_PLUS, whose Hyperdisk storage has
# no HDD option. The route requires HDD storage.

resource "google_sql_database_instance" "main" {
  name             = "${local.prefix}-pg"
  region           = var.region
  database_version = "POSTGRES_16"

  # The instance is created and destroyed by the lifecycle workflows, so
  # Terraform's own deletion guard is off; the `stop` workflow suspends the
  # instance instead (D-033).
  deletion_protection = false



  settings {
    # Enterprise edition: HDD storage is only available on the general purpose
    # shared/dedicated core machine series. Postgres 16 otherwise defaults to
    # ENTERPRISE_PLUS, whose Hyperdisk storage has no HDD option, and the route
    # requires HDD (google_sql_database_instance settings.edition).
    edition           = "ENTERPRISE"
    tier              = var.db_tier
    disk_type         = var.db_disk_type
    disk_size         = var.db_allocated_storage
    disk_autoresize   = false
    availability_type = "ZONAL"
    activation_policy = "ALWAYS"

    # Private IP only: no public address and no authorized networks.
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.main.id
    }

    # NFR-023: encryption at rest. Google-managed keys are the default; backups
    # inherit the instance's encryption.
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "03:00"
      transaction_log_retention_days = 7

      backup_retention_settings {
        retained_backups = 7
      }
    }

    # Minor-version patches applied automatically, never a major upgrade.
    maintenance_window {
      day  = 7 # Sunday
      hour = 4
    }
  }

  # The SQL Admin API and the private-services peering must be live first.
  depends_on = [
    google_project_service.required,
    google_service_networking_connection.private_services,
  ]
}

# Primary store: users, credentials, catalogue, providers, capabilities, cases,
# receipts.
resource "google_sql_database" "primary" {
  name     = "sabi"
  instance = google_sql_database_instance.main.name
}

# Isolated payment records store: its own database and transaction boundary
# (architecture.md, "Payment Module").
resource "google_sql_database" "payments" {
  name     = "sabi_payments"
  instance = google_sql_database_instance.main.name
}

# Application user for both databases. The password is generated here and written
# to Secret Manager; it never appears in a committed file or in a log (NFR-024).
resource "random_password" "db" {
  length  = 32
  special = false
}

resource "google_sql_user" "app" {
  name     = "sabi"
  instance = google_sql_database_instance.main.name
  password = random_password.db.result
}

# Full connection strings, stored in Secret Manager because each embeds the
# database password. Cloud Run mounts the whole value as an environment variable
# at revision start, so the password never appears in the launch spec or state
# as plaintext. The host is the instance's private IP on the VPC.
locals {
  db_host = google_sql_database_instance.main.private_ip_address
  db_user = google_sql_user.app.name
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.app["DATABASE_URL"].id
  secret_data = "postgresql+psycopg://${local.db_user}:${random_password.db.result}@${local.db_host}:5432/${google_sql_database.primary.name}"
}

resource "google_secret_manager_secret_version" "payments_database_url" {
  secret      = google_secret_manager_secret.app["PAYMENTS_DATABASE_URL"].id
  secret_data = "postgresql+psycopg://${local.db_user}:${random_password.db.result}@${local.db_host}:5432/${google_sql_database.payments.name}"
}
