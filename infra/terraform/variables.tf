variable "project" {
  description = "Resource name prefix."
  type        = string
  default     = "sabi"
}

variable "environment" {
  description = "Deployment environment (architecture.md, Environments)."
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "region" {
  description = "Managed cloud region (D-005). Africa region; NDPA transfer position assessed at Foundation."
  type        = string
  default     = "af-south-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the environment VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "db_instance_class" {
  description = "RDS instance class for the primary Postgres store."
  type        = string
  default     = "db.t4g.medium"
}

variable "db_allocated_storage" {
  description = "Allocated storage (GiB) for the primary Postgres store."
  type        = number
  default     = 20
}

variable "db_multi_az" {
  description = "Run the primary Postgres store across AZs (higher environments)."
  type        = bool
  default     = false
}

variable "db_deletion_protection" {
  description = "Block accidental deletion of the primary Postgres store."
  type        = bool
  default     = false
}

variable "redis_node_type" {
  description = "ElastiCache node type for the cache."
  type        = string
  default     = "cache.t4g.micro"
}
