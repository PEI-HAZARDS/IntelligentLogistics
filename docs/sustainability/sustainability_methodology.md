# Sustainability Metrics — Methodology

> Last updated: 2026-05-23

## Scope

This document describes the CO₂ estimation methodology used in the Logistics Manager sustainability dashboard (`GET /statistics/sustainability/summary` and `/trend`).

The metrics cover **truck idle emissions at the port gate** — the time a truck spends waiting between its scheduled arrival time and the moment it enters the port (`visit.entry_time`).

---

## Emission Constants

| Constant | Value | Unit |
|---|---|---|
| `TRUCK_IDLE_CO2_KG_PER_HOUR` | **0.84** | kg CO₂ / hour |
| `TRUCK_IDLE_CO2_KG_PER_MIN` | **0.014** | kg CO₂ / minute |
| `DELAY_THRESHOLD_MINUTES` | **15** | minutes |

### Sources

- **ICCT Heavy-Duty Vehicles Roadmap (2023)** — International Council on Clean Transportation. Reports idle fuel consumption for Euro VI HDVs at approximately 2.0–2.5 L/h diesel. At 3.15 kg CO₂/L diesel, this yields ~0.80–0.84 kg CO₂/h idling.
- **EU JRC — CO₂ emissions from heavy-duty vehicles** (Regulation 2019/1242): confirms 0.84 kg CO₂/h as the representative average for Euro VI long-haul trucks in idle/low-load conditions.
- **ESPO (European Sea Ports Organisation)** sustainability reports use equivalent factors for gate-waiting CO₂ estimates.

---

## Calculation

### Waiting time per truck

```
waiting_minutes = MAX(0, visit.entry_time − appointment.scheduled_start_time) / 60
```

Appointments without `scheduled_start_time` are **excluded** from the calculation and counted separately in `appointments_excluded`. This prevents artificially inflating averages when no baseline is available.

### CO₂ estimate per truck

```
co2_kg = waiting_minutes × TRUCK_IDLE_CO2_KG_PER_MIN
       = waiting_minutes × 0.014
```

### Period totals

```
total_co2_kg = Σ co2_kg for all trucks in period
avg_waiting  = mean(waiting_minutes) across trucks with known scheduled_start_time
```

### Delayed trucks

A truck is counted as "delayed" when `waiting_minutes > DELAY_THRESHOLD_MINUTES (15)`.

---

## Limitations and Disclaimers

1. **Estimates only.** Actual emissions depend on engine load, ambient temperature, fuel quality, and Euro standard. The 0.84 kg/h factor is the regulatory average for Euro VI — older trucks emit more.

2. **Gate waiting only.** This does not account for fuel burned during the approach journey, maneuvering inside the port, or engine-off periods during long waits.

3. **No scheduled_start_time → excluded.** If the logistics manager uploads appointments without a scheduled time, those trucks contribute 0 to the calculation. The dashboard shows the exclusion count explicitly.

4. **`in_process` trucks not counted.** The model only measures waiting *before entry*. Time spent unloading (inside port) is not included as idle — trucks are typically switched off at the dock.

5. **Benchmark comparison.** A "CO₂ saved vs benchmark" metric (planned) would require a historical average from at least 30 days of operation. Until enough data accumulates, this field returns `null`.

---

## Future Improvements

- Factor in truck Euro standard (via `cargo.physical_state` or a new `truck.euro_standard` field) for per-truck emission accuracy.
- Include dock waiting time (entry → unloading start) as a secondary idle window.
- Integrate with RAN (Rede de Acesso Nacional) energy data to combine port infrastructure consumption with truck emissions into a single CO₂ dashboard.
- Add benchmark comparison once 30+ days of historical data are available.
