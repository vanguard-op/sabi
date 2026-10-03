"""Staff authentication for the Operations Console (C-039, C-040).

A dedicated email + password + TOTP surface, separate from the end-user passkey
flow: only an operator session kind is ever issued, and every auth event is
audited (NFR-020, NFR-026, NFR-028).
"""
