terraform {
  required_version = ">= 1.10.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.5"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
  }

  # Partial backend. The bucket and prefix are supplied at init time through
  # -backend-config (see envs/staging/backend.hcl.example), so no account id is
  # committed to the repo. State lives in gs://sabi-hq-tfstate (D-034) and that
  # bucket survives a destroy so the environment can be rebuilt (D-033).
  backend "gcs" {}
}
