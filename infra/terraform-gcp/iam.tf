# Runtime identities. Least privilege: one service account per Cloud Run service,
# each granted only the roles its service actually needs.
#
# - The API gateway reads the application secrets, connects to Cloud SQL, and
#   invokes the private AI and payment services.
# - The AI service reads only the model API key.
# - The payment module reads only its signing key and rail credential, and
#   connects to the isolated payment store.
# - The console reads nothing from the secret store; it is a static bundle that
#   talks to the API gateway over HTTPS.

resource "google_service_account" "api" {
  account_id   = "${local.prefix}-api"
  display_name = "Sabi API gateway (${var.environment})"
}

resource "google_service_account" "ai" {
  account_id   = "${local.prefix}-ai"
  display_name = "Sabi AI service (${var.environment})"
}

resource "google_service_account" "payments" {
  account_id   = "${local.prefix}-payments"
  display_name = "Sabi payment module (${var.environment})"
}

resource "google_service_account" "console" {
  account_id   = "${local.prefix}-console"
  display_name = "Sabi operations console (${var.environment})"
}

# --- Secret access ---------------------------------------------------------------
# Per-secret accessor bindings, so a service can read only its own secrets rather
# than the whole project secret set.

locals {
  secret_access = {
    api = [
      "SESSION_SECRET",
      "RECOVERY_CODE_PEPPER",
      "DATABASE_URL",
      "PAYMENTS_DATABASE_URL",
    ]
    ai = [
      "GEMINI_API_KEY",
    ]
    payments = [
      "MANDATE_SIGNING_KEY",
      "PAYMENT_RAIL_CREDENTIAL",
      "PAYMENTS_DATABASE_URL",
    ]
  }

  # Concrete service-account emails, so a binding can name one without a dynamic
  # resource reference.
  service_account_emails = {
    api      = google_service_account.api.email
    ai       = google_service_account.ai.email
    payments = google_service_account.payments.email
    console  = google_service_account.console.email
  }
}

resource "google_secret_manager_secret_iam_member" "accessor" {
  for_each = merge([
    for svc, keys in local.secret_access : {
      for key in keys : "${svc}:${key}" => {
        member = "serviceAccount:${local.service_account_emails[svc]}"
        secret = key
      }
    }
  ]...)

  secret_id = google_secret_manager_secret.app[each.value.secret].id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value.member
}

# --- Cloud SQL access ------------------------------------------------------------
# Both the API and the payment module open their own database through the Cloud
# SQL connector; both need the client role. The connection itself uses IAM, so
# no database password is stored in a launch environment.
resource "google_project_iam_member" "api_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "payments_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.payments.email}"
}

# The console serves a static bundle from the same image and needs nothing else.
resource "google_project_iam_member" "console_artifact_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.console.email}"
}

# --- Service-to-service invocation ----------------------------------------------
# The API gateway invokes the private AI and payment services. Cloud Run's
# run.invoker role is granted on each target service to the gateway account only,
# never to allUsers, so the private services stay unreachable from the internet.
resource "google_cloud_run_v2_service_iam_member" "api_invokes_ai" {
  project  = var.project_id
  location = var.region
  name     = local.service_names["ai"]
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.api.email}"
}

resource "google_cloud_run_v2_service_iam_member" "api_invokes_payments" {
  project  = var.project_id
  location = var.region
  name     = local.service_names["payments"]
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.api.email}"
}

# --- Public invocation -----------------------------------------------------------
# Only the gateway and the console are public: end users and staff reach them
# directly. allUsers is scoped per-service, never project-wide.
resource "google_cloud_run_v2_service_iam_member" "public" {
  for_each = { for k, v in local.services : k => v if v.public }

  project  = var.project_id
  location = var.region
  name     = local.service_names[each.key]
  role     = "roles/run.invoker"
  member   = "allUsers"
}
