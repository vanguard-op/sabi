"""Identity verification for regulated payments (FEAT-002, C-020..C-022).

Verifies a user's NIN or BVN against the national identity provider once and
stores a KYC status that gates regulated payments while discovery stays open.
Exposes ``router`` for auto-discovery by the application factory.
"""
