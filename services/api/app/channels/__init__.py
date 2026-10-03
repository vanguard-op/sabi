"""USSD and SMS channel gateway for feature-phone users (FEAT-010, C-036 to C-038).

The gateway is the channel's entry point into the same account and the same
payment loop the app uses (architecture.md, "USSD/SMS Channel Gateway"). It
resolves a channel address to an existing account link, drives a short USSD
session, and records SMS delivery. USSD sessions are time-bound and resume a
pending payment rather than restarting it (FEAT-010, NFR-006).

Payment execution and SMS delivery live outside this module: the isolated
payment module and the notification service are reached through the ports in
``app.channels.ports``, bound on ``app.state`` by the deployment. Nothing here
reads a payment table or an SMS provider directly.
"""
