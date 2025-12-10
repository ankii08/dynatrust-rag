# Atlas4D Base Security Guide

This document describes the security posture of the **Atlas4D Base** repository and the minimum steps required to harden a deployment for real-world use.

Atlas4D Base ships with a **developer-friendly, demo-oriented** configuration.  
It is **not production-ready out of the box**.

---

## 1. Demo vs Production

- The default `docker-compose.yml` and example `.env` files are designed for:
  - local development,
  - single-node demos,
  - sandbox environments.

- In **production** you MUST:
  - change all default passwords,
  - restrict exposed ports,
  - enable TLS termination (HTTPS),
  - configure proper access control in front of the APIs.

---

## 2. Database Hardening (PostgreSQL)

- Use a **strong password** for the PostgreSQL superuser. Never keep the default from `.env.example`.
- Create a dedicated application user (e.g. `atlas4d_app`) with:
  - `CONNECT` on the `atlas4d` database,
  - `USAGE` on the `atlas4d` schema,
  - `SELECT/INSERT/UPDATE` only where needed.
- Avoid using the `postgres` superuser from application services.
- Restrict DB access in `pg_hba.conf` to:
  - internal networks and/or
  - specific application hosts.
- Enable regular backups and point-in-time recovery (PITR) according to your RPO/RTO.

---

## 3. API & Network

- By default, bind internal services to `127.0.0.1` or a private network only.
- Place Atlas4D behind a **reverse proxy** (Nginx, Traefik, etc.) that:
  - terminates TLS (HTTPS),
  - enforces CORS policy,
  - can apply basic rate limiting.
- Expose only the minimal set of endpoints publicly:
  - public API,
  - frontend,
  - NLQ / RAG (if intended for external use).
- Keep admin / internal endpoints (health, metrics, internal APIs) on **private networks** only.

---

## 4. Docker & Host Security

- Run containers as a **non-root user** where possible (`user: "1000:1000"` or similar).
- Mount only the volumes that are strictly required.
- Keep the host OS updated (kernel, Docker engine, security patches).
- Limit SSH access to the host:
  - key-based auth,
  - no direct root login,
  - optional jump host / VPN.

---

## 5. Secrets Management

- Do **not** commit real secrets to Git.
  - `.env.example` is provided only as a template with placeholders.
- For production environments, prefer:
  - Docker secrets,
  - Kubernetes Secrets,
  - or an external secret manager (Vault, AWS/GCP secrets, etc.).
- Rotate credentials regularly (DB users, API keys, SSH keys).

---

## 6. Observability Stack (Optional)

If you enable Prometheus / Grafana / Loki / etc.:

- Protect Grafana with a strong admin password and, ideally, SSO or OAuth.
- Avoid exposing Prometheus and Loki directly to the public internet.
- Treat logs as potentially sensitive:
  - avoid logging secrets,
  - restrict access to log storage.

---

## 7. RAG / LLM Safety Notes

If you run NLQ / RAG components:

- Treat RAG inputs as **untrusted user input**.
- Consider rate limiting and basic abuse protection (to avoid prompt flooding / DoS).
- Make sure the RAG index **does not contain private / customer data** unless you are in a trusted, access-controlled environment.

---

## 8. Demo Checklist

For a **public demo instance**, at minimum:

- [ ] Changed all default passwords and secrets.
- [ ] Limited exposed ports via firewall / security groups.
- [ ] Enabled HTTPS on the public domain.
- [ ] Restricted access to admin endpoints (health, metrics, dashboards).
- [ ] Configured log rotation and disk limits.
- [ ] Documented how often the demo data is reset.

---

This document is intentionally high-level.  
For production deployments, always align Atlas4D with your organisation's security policies and regulatory requirements.
