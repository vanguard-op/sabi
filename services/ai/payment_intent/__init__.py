"""Payment-intent extraction feature package (FEAT-005, FEAT-009, MQ-001).

The model-backed slice of the payment loop that turns a free-form request into the
amount and payee Sabi confirms before authorisation (FEAT-005) and that the payment
record later carries into status, dispute, and refund handling (FEAT-009). Amount,
payee, and reference are grounded in the catalogue and never invented (MQ-001). The
package is auto-discovered and its router mounted at ``/v1`` by :mod:`app.main`.
"""

from __future__ import annotations
