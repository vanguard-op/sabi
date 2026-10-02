# Cache: sessions, rate-limit counters, and hot catalogue entries (architecture.md).
# Encryption in transit and at rest per NFR-022 and NFR-023.

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project}-${var.environment}"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_security_group" "cache" {
  name_prefix = "${var.project}-${var.environment}-cache-"
  description = "Redis reachable from application tasks only."
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Redis from application tasks"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  tags = { Name = "${var.project}-${var.environment}-cache" }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "${var.project}-${var.environment}"
  description          = "Sabi cache: sessions, rate limits, hot catalogue entries."

  engine         = "redis"
  engine_version = "7.1"
  node_type      = var.redis_node_type
  port           = 6379

  num_cache_clusters         = 1
  automatic_failover_enabled = false

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.cache.id]

  at_rest_encryption_enabled = true # NFR-023
  transit_encryption_enabled = true # NFR-022

  tags = { Name = "${var.project}-${var.environment}" }
}
