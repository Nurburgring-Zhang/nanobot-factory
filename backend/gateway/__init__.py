"""Nanobot Factory API Gateway.

A lightweight API gateway that:
  - Routes incoming requests to downstream microservices
  - Validates JWT tokens (or allows public auth/login endpoints through)
  - Applies per-IP token-bucket rate limiting
  - Wraps each downstream call in a circuit breaker
  - Emits structured access logs and request IDs for tracing
  - Forwards the proxied request via httpx.AsyncClient

The configuration is driven by ``routes.yaml`` — adding a new microservice
is a one-line change there, no Python edit required.
"""

__version__ = "0.1.0"
