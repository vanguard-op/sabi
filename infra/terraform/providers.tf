provider "aws" {
  region = var.region

  default_tags {
    tags = local.tags
  }
}

locals {
  tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  # Two AZs are the minimum for an RDS subnet group. The region is the managed
  # Africa region closest to the Nigeria-primary intent in architecture.md.
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}
