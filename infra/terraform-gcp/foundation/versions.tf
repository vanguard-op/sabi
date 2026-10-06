terraform {
  required_version = ">= 1.10.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.5"
    }
  }

  # Partial backend. The bucket and prefix are supplied at init time through
  # -backend-config (see envs/staging/backend.hcl.example). This root is the
  # long-lived network foundation of D-058: `gcp-up` applies it and
  # `gcp-destroy` never deletes it. Its state lives under its own prefix
  # (sabi/staging-foundation) so the workload root of infra/terraform-gcp can
  # be destroyed and rebuilt without touching the network, API enablement,
  # private-services peering, or database firewall.
  backend "gcs" {}
}
