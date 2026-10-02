output "vpc_id" {
  description = "Environment VPC id."
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "Public subnet ids, for the future load balancer."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet ids, for data stores and application compute."
  value       = aws_subnet.private[*].id
}

output "application_security_group_id" {
  description = "Security group to attach to application compute."
  value       = aws_security_group.app.id
}

output "database_endpoint" {
  description = "Primary Postgres endpoint (host:port)."
  value       = aws_db_instance.primary.endpoint
}

output "database_master_secret_arn" {
  description = "ARN of the AWS-managed RDS master credential secret."
  value       = aws_db_instance.primary.master_user_secret[0].secret_arn
}

output "cache_primary_endpoint" {
  description = "Redis primary endpoint address."
  value       = aws_elasticache_replication_group.main.primary_endpoint_address
}

output "app_secret_arn" {
  description = "ARN of the application secret container; populate values out-of-band."
  value       = aws_secretsmanager_secret.app.arn
}
