# Managed secret store (NFR-024). Terraform creates the secret containers and the
# IAM that lets the runtime read them; real values are written out-of-band or by
# the `up` workflow from GitHub secrets, never from the repo and never in state.
#
# The container names mirror the existing .env keys so the runtime environment
# maps one-to-one: a service reads the same variable name locally and in staging.

locals {
  # Application secrets, keyed by the .env variable they populate. Those a fresh
  # environment can generate are filled by Terraform below; the rest (the model
  # API key, the rail credential, the native WebAuthn origins) have no committed
  # default and are written out-of-band or by the `up` workflow from GitHub
  # secrets.
  #
  # The two connection strings live here rather than as plain launch variables
  # because each embeds the database password, and Secret Manager is the only
  # place a password may live (NFR-024).
  app_secrets = toset([
    "SESSION_SECRET",
    "RECOVERY_CODE_PEPPER",
    "MANDATE_SIGNING_KEY",
    "GEMINI_API_KEY",
    "WEBAUTHN_NATIVE_ORIGINS",
    "PAYMENT_RAIL_CREDENTIAL",
    "DATABASE_URL",
    "PAYMENTS_DATABASE_URL",
  ])
}

resource "google_secret_manager_secret" "app" {
  for_each = local.app_secrets

  secret_id = "${local.prefix}-${lower(replace(each.key, "_", "-"))}"
  labels    = local.labels

  replication {
    auto {}
  }
}

# Generated secrets: the values a fresh environment must have and that no human
# needs to see. Terraform generates them once and stores them in Secret Manager.
# They are marked sensitive and never printed.
resource "random_password" "session_secret" {
  length  = 48
  special = false
}

resource "random_password" "recovery_pepper" {
  length  = 48
  special = false
}

resource "random_password" "mandate_key" {
  length  = 48
  special = false
}

locals {
  # Values Terraform can generate. The model API key and rail credential are
  # absent: only a human can supply those, and the `up` workflow writes them
  # from GitHub secrets before it deploys.
  generated_secret_values = {
    SESSION_SECRET       = random_password.session_secret.result
    RECOVERY_CODE_PEPPER = random_password.recovery_pepper.result
    MANDATE_SIGNING_KEY  = random_password.mandate_key.result
  }
}

resource "google_secret_manager_secret_version" "generated" {
  for_each = local.generated_secret_values

  secret      = google_secret_manager_secret.app[each.key].id
  secret_data = each.value
}

# Placeholder versions for the secrets only a human can supply. Cloud Run refuses
# to create a revision that references a secret with no enabled version, so each
# container gets a valid empty value so a fresh environment can boot; the real
# values are written out-of-band (or by the `up` workflow for the model key) and
# become the latest version. An empty model key makes the AI service use its
# keyword fallback; the native-origin list is a JSON array the settings parser
# accepts as empty.
resource "google_secret_manager_secret_version" "placeholder" {
  for_each = {
    GEMINI_API_KEY          = ""
    WEBAUTHN_NATIVE_ORIGINS = "[]"
    PAYMENT_RAIL_CREDENTIAL = ""
  }

  secret      = google_secret_manager_secret.app[each.key].id
  secret_data = each.value
}
