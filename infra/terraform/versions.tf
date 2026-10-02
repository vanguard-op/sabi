terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.67"
    }
  }

  # Partial backend. Supply account-specific values at init time through
  # -backend-config (see envs/*/backend.hcl.example and `make tf-init`), so no
  # bucket or account id is committed to the repo.
  backend "s3" {}
}
