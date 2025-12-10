# Contributing to Atlas4D

Welcome! We're excited you want to contribute to Atlas4D. Here are the paths you can take.

---

## 🛠️ "I want to help with code"

### Getting Started

1. **Fork the repository**
```bash
   git clone https://github.com/crisbez/atlas4d-base.git
   cd atlas4d-base
```

2. **Run locally**
```bash
   docker compose up -d
   # Wait for services to start
   curl http://localhost:8090/health
```

3. **Pick an issue**
   - Look for `good first issue` labels
   - Check the [Issues](https://github.com/crisbez/atlas4d-base/issues) page

### Good First Code Contributions

- **Add a new demo scenario** - Create SQL seed data for a new use case
- **Improve API endpoints** - Add pagination, filtering, or new endpoints
- **Write tests** - We always need more test coverage
- **Fix bugs** - Check issues labeled `bug`

### Code Guidelines

- Python: Follow PEP 8, use type hints
- SQL: Use lowercase for keywords, uppercase for table names
- Commits: Use [Conventional Commits](https://www.conventionalcommits.org/)
- PRs: Include description, tests if applicable

---

## 📝 "I want to help with documentation"

### Getting Started

1. Documentation lives in `/docs`
2. We use Markdown with clear structure
3. No special tools needed - just edit and submit PR

### Good First Doc Contributions

- **Fix typos or unclear explanations**
- **Add examples** - More code examples help everyone
- **Translate** - Help us reach more developers (Bulgarian, German, etc.)
- **Write tutorials** - Step-by-step guides for specific use cases

### Documentation Structure
```
docs/
├── quickstart/       # Getting started guides
├── architecture/     # Technical specs
├── modules/          # Module documentation
├── deploy/           # Deployment guides
└── community/        # This folder!
```

---

## 💡 "I have an idea for a module"

### Before You Start

1. **Read the Module Model** - [docs/architecture/MODULE_MODEL.md](../architecture/MODULE_MODEL.md)
2. **Check existing modules** - Is there something similar?
3. **Open a discussion** - Share your idea before coding

### Module Ideas We'd Love

- **Aviation/Airspace** - ADS-B tracking, drone detection
- **Maritime** - AIS data, port monitoring
- **Agriculture** - IoT sensors, weather integration
- **Energy** - Grid monitoring, renewable tracking

### Proposing a Module

1. Open an issue with `[Module Proposal]` prefix
2. Include:
   - **Use case** - What problem does it solve?
   - **Data sources** - What data does it need?
   - **NLQ examples** - How would users query it?
   - **Integration** - How does it use Core tables?

---

## 🐛 Reporting Bugs

1. Check if the bug is already reported
2. Use the bug report template
3. Include:
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment (OS, Docker version, etc.)
   - Logs if available

---

## 💬 Getting Help

- **GitHub Issues** - For bugs and feature requests
- **Discussions** - For questions and ideas
- **Email** - office@atlas4d.tech

---

## 🙏 Thank You

Every contribution matters, no matter how small. Whether you fix a typo, add an example, or build a whole new module - you're helping build something meaningful.

**Let's build the future of spatiotemporal data together!**
