# Primary database. Postgres 16 with pgvector supports the primary store and the
# retrieval index (D-003). The isolated payment store is a separate database on
# its own instance when the payment loop lands; Phase 1 has no money movement.

resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-${var.environment}"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_security_group" "database" {
  name_prefix = "${var.project}-${var.environment}-db-"
  description = "Postgres reachable from application tasks only."
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Postgres from application tasks"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  tags = { Name = "${var.project}-${var.environment}-db" }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_db_instance" "primary" {
  identifier = "${var.project}-${var.environment}"

  engine         = "postgres"
  engine_version = "16"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_allocated_storage * 5
  storage_type          = "gp3"
  storage_encrypted     = true # NFR-023: AES-256 at rest

  db_name                     = "sabi"
  username                    = "sabi"
  manage_master_user_password = true # credential held in Secrets Manager, never in state or code

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.database.id]
  multi_az               = var.db_multi_az
  publicly_accessible    = false

  backup_retention_period = var.environment == "prod" ? 30 : 7 # NFR-010/011 recovery
  deletion_protection     = var.db_deletion_protection
  skip_final_snapshot     = var.environment != "prod"

  final_snapshot_identifier = var.environment == "prod" ? "${var.project}-${var.environment}-final" : null

  auto_minor_version_upgrade = true
  apply_immediately          = var.environment != "prod"
}
