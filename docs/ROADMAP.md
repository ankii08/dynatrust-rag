# Atlas4D Roadmap

> **Vision:** Become the "Linux of 4D spatiotemporal data" - a stable, modular platform that others build upon.

---

## Current Release

### v0.3.0 (December 2025) ✅

**"First Public Release"**

- ✅ Core stack stable (PostgreSQL + PostGIS + TimescaleDB + pgvector)
- ✅ Working docker-compose deployment
- ✅ 2 demo scenarios (Mobility + Telecom)
- ✅ Full documentation suite
- ✅ Python SDK v0.2.0 on PyPI (`pip install atlas4d`)
- ✅ RAG-powered Docs Assistant
- ✅ Helm Charts for Kubernetes
- ✅ 5 Industry Case Studies

---

## Upcoming Releases

### v0.4.0 - Q1 2026

**"Module Ecosystem"**

| Feature | Status | Description |
|---------|--------|-------------|
| Module Spec | 📋 Planned | Define `module.yaml` format |
| Example Module | 📋 Planned | Telco GPON or Wildfire as reference |
| Module CLI | 📋 Planned | `atlas4d module list/install/enable` |
| SDK v0.3.0 | 📋 Planned | Async client (`AsyncClient`) |

### v0.5.0 - Q2 2026

**"Intelligence Layer"**

| Feature | Status | Description |
|---------|--------|-------------|
| WebSocket Streaming | 📋 Planned | Real-time observation updates |
| JS/TS SDK | 📋 Planned | Frontend integration library |
| RAG Phase 2 | 📋 Planned | More docs, better chunking |
| Cloud Templates | 📋 Planned | GKE/EKS/AKS quickstarts |

### v1.0.0 - Q3 2026

**"Production Ready"**

| Feature | Status | Description |
|---------|--------|-------------|
| Multi-tenant | 📋 Planned | Isolated namespaces per tenant |
| Enterprise Auth | 📋 Planned | OIDC/SAML integration |
| HA Deployment | 📋 Planned | PostgreSQL HA, Redis Sentinel |
| SLA & Support | 📋 Planned | Commercial support options |

---

## Atlas4D Modules (v0.4+)

**Goal:** Make Atlas4D Base extensible through domain-specific modules without changing the core.

A module is a self-contained package that can add:

- additional database migrations,
- microservices / workers,
- NLQ / STSQL grammar extensions,
- dashboards or views.

### Module Structure
```
modules/
└── telco-gpon/
    ├── module.yaml          # name, version, dependencies
    ├── migrations/          # SQL migrations
    ├── services/            # Docker services
    ├── nlq/                 # NLQ templates & grammars
    └── ui/                  # Dashboards & views
```

### Planned Milestones

**v0.4.0 - Module Spec + Example**
- Define module layout under `/modules/`
- Document `module.yaml` fields (name, version, migrations, services, nlq templates)
- Ship one example module (Telco GPON or Wildfire Monitoring) as reference

**v0.5.0 - Module Loader**
- CLI / script to enable a module:
  - merge its `docker-compose.module.yml` / Helm values
  - run its DB migrations
- Allow nlq-svc to load NLQ templates from enabled modules

**Later - Module Ecosystem**
- Curated gallery of official modules (NetGuard, Event Risk, Threat Forecasting)
- Community-contributed modules for custom domains
- Module marketplace (free + commercial)

### Core Promise

**Atlas4D stays a stable 4D base layer**, while modules bring domain logic and can evolve independently.

---

## Candidate Official Modules

| Module | Domain | Status |
|--------|--------|--------|
| **Network Guardian** | Telecom / ISP | 🔄 In Development |
| **Event Risk** | Public Safety | 🔄 In Development |
| **Threat Forecasting** | Security | 🔄 In Development |
| **Wildfire Monitor** | Environment | 📋 Planned |
| **Crop Analytics** | Agriculture | 📋 Planned |
| **Counter-UAS** | Defense | 📋 Planned |

---

## Long-term Vision
```
┌─────────────────────────────────────────────────────────────┐
│                    Atlas4D Ecosystem                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│   │   Telco     │  │  Smart City │  │   Defense   │        │
│   │   Module    │  │   Module    │  │   Module    │        │
│   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│          │                │                │                │
│   ┌──────┴────────────────┴────────────────┴──────┐        │
│   │              Atlas4D Base (Core)              │        │
│   │  PostgreSQL + PostGIS + TimescaleDB + pgvector │        │
│   │         NLQ + RAG + STSQL + REST API          │        │
│   └───────────────────────────────────────────────┘        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Contributing to the Roadmap

We welcome community input on the roadmap!

- **Feature requests:** Open an issue with the `enhancement` label
- **Module ideas:** Discuss in GitHub Discussions
- **Priority feedback:** Comment on existing roadmap issues

---

*Last updated: December 2025*
