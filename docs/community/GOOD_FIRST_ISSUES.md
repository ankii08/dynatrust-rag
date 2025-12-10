# Good First Issues

Ideas for newcomers to contribute. Create these as GitHub Issues!

---

## 📝 Documentation

### 1. Add Python SDK examples
**Difficulty:** Easy  
**File:** `sdk/python/README.md`  
**Task:** Add more usage examples (filtering, pagination, error handling)

### 2. Improve Quick Start troubleshooting
**Difficulty:** Easy  
**File:** `docs/quickstart/QUICK_START.md`  
**Task:** Add common problems and solutions section

### 3. Translate ONE_PAGER to Bulgarian
**Difficulty:** Easy  
**File:** `docs/site/ONE_PAGER_BG.md` (new)  
**Task:** Translate the one-pager to Bulgarian

---

## 🐍 Python/SDK

### 4. Add SDK version check
**Difficulty:** Medium  
**File:** `sdk/python/atlas4d/client.py`  
**Task:** Add `client.version()` to check API version compatibility

### 5. Add async client option
**Difficulty:** Medium  
**Files:** `sdk/python/atlas4d/async_client.py` (new)  
**Task:** Create async version using `httpx` async

---

## 🗄️ SQL/Database

### 6. Add demo scenario: Weather station
**Difficulty:** Medium  
**File:** `sql/seed/demo_weather.sql` (new)  
**Task:** Create demo data for weather monitoring use case

### 7. Optimize observations query
**Difficulty:** Medium  
**File:** `sql/schema/observations.sql`  
**Task:** Add partial index for recent observations

---

## 🧪 Testing

### 8. Add API Gateway tests
**Difficulty:** Medium  
**File:** `services/api-gateway/tests/` (new)  
**Task:** Add pytest tests for core endpoints

### 9. Add SDK integration tests
**Difficulty:** Medium  
**File:** `sdk/python/tests/` (new)  
**Task:** Add tests that run against live API

---

## 🎨 Frontend

### 10. Improve mobile responsiveness
**Difficulty:** Easy  
**File:** `services/frontend/src/`  
**Task:** Fix map controls on mobile screens

---

## How to Claim an Issue

1. Comment on the issue: "I'd like to work on this"
2. Fork the repo
3. Create a branch: `git checkout -b issue-X-description`
4. Submit PR when ready

---

*Last updated: December 2025*
