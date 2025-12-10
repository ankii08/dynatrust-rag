# Atlas4D Telecom Profile

**Module:** atlas4d-module-telecom  
**Status:** Reference Implementation  
**Version:** 0.1.0

---

## Overview

The Telecom Profile demonstrates Atlas4D's capabilities for **network infrastructure monitoring** — tracking OLTs, switches, CPE devices, and traffic metrics with LSTM-based predictions.

---

## What's Included

### Database Schema
```sql
-- Network nodes (OLT, switches, CPE)
atlas4d.observations_core WHERE source_type IN ('olt', 'switch', 'cpe')

-- Traffic metrics
atlas4d.observations_core WHERE source_type = 'traffic_metric'

-- Network anomalies
atlas4d.anomalies WHERE anomaly_type IN (
  'high_latency', 'packet_loss', 'link_down', 
  'congestion', 'power_warning'
)
```

### Demo Data

Load with:
```bash
docker compose exec postgres psql -U atlas4d_app -d atlas4d \
  -f /docker-entrypoint-initdb.d/seed/demo_telecom.sql
```

**Contents:**
- 3 OLT nodes (20-40 Gbps capacity)
- 5 Distribution switches
- 20 CPE devices (ONT)
- 50 Traffic metrics
- 6 Network anomalies

### Visualization

Frontend supports "📡 Telecom" scenario with:
- Color-coded markers by node type
- Larger icons for infrastructure (OLT, switches)
- Popup details: capacity, power levels, metrics

---

## NLQ Examples

### Bulgarian 🇧🇬
```
"Покажи претоварени линкове от последния час"
→ Shows congestion anomalies in last hour

"Кои OLT имаха проблеми вчера?"
→ Lists OLTs with anomalies yesterday

"Покажи CPE с лош оптичен сигнал"
→ Finds CPE with power_warning anomalies

"Колко аномалии има по мрежата днес?"
→ Counts network anomalies today
```

### English 🇬🇧
```
"Show network anomalies near Burgas"
→ Spatial query for network issues

"Which nodes had high latency yesterday?"
→ Latency anomalies by node

"List all OLT capacity utilization"
→ Traffic metrics for OLT nodes

"Find switches with packet loss"
→ Packet loss anomalies on switches
```

---

## Key Metrics

| Metric | Description | Source |
|--------|-------------|--------|
| `capacity_gbps` | Node bandwidth capacity | metadata |
| `active_ports` | Ports in use | metadata |
| `rx_power_dbm` | Optical receive power | metadata (CPE) |
| `tx_power_dbm` | Optical transmit power | metadata (CPE) |
| `bandwidth_mbps` | Customer bandwidth | metadata (CPE) |
| `throughput_gbps` | Traffic throughput | metadata (traffic) |
| `latency_ms` | Network latency | metadata (traffic) |
| `packet_loss_pct` | Packet loss rate | metadata (traffic) |

---

## Anomaly Types

| Type | Severity | Description |
|------|----------|-------------|
| `high_latency` | 2-3 | Latency above threshold |
| `packet_loss` | 3-4 | Packet loss detected |
| `link_down` | 5 | Link failure |
| `congestion` | 3 | Bandwidth saturation |
| `power_warning` | 2 | Optical power degradation |

---

## Full Platform: Network Guardian

The complete Atlas4D platform includes **Network Guardian** module with:

### LSTM Predictions
- 6-hour traffic forecasting
- Anomaly prediction before occurrence
- Per-node prediction models

### SNMP Integration
- Real-time device polling
- ZTE GPON support (C300, C320)
- Custom OID mappings

### Advanced Features
- Topology visualization
- Impact analysis (which customers affected)
- Automated alerting
- Historical trend analysis

---

## Architecture
```
┌─────────────────────────────────────────────┐
│              Telecom Module                  │
├─────────────────────────────────────────────┤
│  network-guardian-svc                       │
│  ├── SNMP Poller                            │
│  ├── LSTM Predictor                         │
│  └── Anomaly Detector                       │
├─────────────────────────────────────────────┤
│  Metrics: telecom_*                         │
│  ├── nodes_total                            │
│  ├── anomalies_total                        │
│  └── prediction_latency                     │
├─────────────────────────────────────────────┤
│  Atlas4D Core                               │
│  observations_core + anomalies              │
└─────────────────────────────────────────────┘
```

---

## Try It

### 1. Start Base Stack
```bash
cd atlas4d-base
docker compose up -d
```

### 2. Load Telecom Demo
```bash
docker compose exec postgres psql -U atlas4d_app -d atlas4d \
  -f /docker-entrypoint-initdb.d/seed/demo_telecom.sql
```

### 3. Open Map
Visit http://localhost:8091 and select "📡 Telecom" scenario.

### 4. Query via API
```bash
# Get all OLT nodes
curl "http://localhost:8090/api/observations?source_type=olt" | jq

# Get network anomalies
curl "http://localhost:8090/api/anomalies" | jq
```

---

## Interested in Full Network Guardian?

Contact us at **office@atlas4d.tech** for:
- Full SNMP integration
- LSTM prediction models
- Custom dashboards
- Enterprise support

---

*This is a reference vertical demonstrating Atlas4D's multi-domain capabilities.*
