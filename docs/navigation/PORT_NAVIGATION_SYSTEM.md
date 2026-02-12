# Port Internal Navigation System

## Overview

Graph-based routing system for navigation within the port.
The core concept is a **Graph Builder Engine** that converts port topology configuration (YAML) into a navigable graph for route calculation.

## Architecture

```
+-----------------------------------------------------------------------------+
|                           MAP/CONFIG SOURCES                                 |
+-------------------+-------------------+-------------------------------------+
| Manual YAML       | GIS Export        | Database                            |
| (port_test.yaml)  | (future)          | (future)                            |
+--------+----------+---------+---------+-------------------+-----------------+
         |                    |                             |
         v                    v                             v
+-----------------------------------------------------------------------------+
|                       GRAPH BUILDER ENGINE                                   |
|                       (graph_builder.py)                                     |
|  - Parses YAML configuration                                                 |
|  - Creates Node and Edge objects                                             |
|  - Validates graph connectivity                                              |
|  - Applies restrictions by cargo type                                        |
+-----------------------------------+-----------------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------------+
|                          PORT GRAPH                                          |
|                       (route_planner_v2.py)                                  |
|  +------------------+  +-------------------+  +---------------------------+  |
|  | Nodes            |  | Edges             |  | Routing Algorithm         |  |
|  | (GATE, DOCK,     |  | (weight,          |  | (Dijkstra with dynamic    |  |
|  | TERMINAL, etc.)  |  | restrictions)     |  | weights + cargo class)    |  |
|  +------------------+  +-------------------+  +---------------------------+  |
+-----------------------------------+-----------------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------------+
|                          INTEGRATION                                         |
|  - Decision Engine uses graph for route calculation                          |
|  - Returns optimal path considering cargo restrictions                       |
+-----------------------------------------------------------------------------+
```

## Core Components

### 1. Graph Builder Engine (`graph_builder.py`)

Converts configuration files into a PortGraph object.

```python
from graph_builder import GraphBuilderEngine

engine = GraphBuilderEngine()
graph = engine.from_yaml("config/port_test.yaml")

# Graph now ready for route calculations
cost, path, edges = graph.find_route("gate_main", "dock_1")
```

### 2. Port Graph (`route_planner_v2.py`)

Core classes:
- **Node**: Point in the port (gate, dock, intersection, terminal)
- **Edge**: Connection between nodes with weight and restrictions
- **PortGraph**: Graph structure with Dijkstra routing

```python
from route_planner_v2 import PortGraph, CargoClass

# Find route for general cargo
cost, nodes, edges = graph.find_route("gate_main", "dock_1", CargoClass.GENERAL)

# Find route for hazardous cargo (avoids restricted routes)
cost, nodes, edges = graph.find_route("gate_hazmat", "dock_hazmat", CargoClass.CLASS_3_FLAMMABLE)
```

## Configuration Format (YAML)

```yaml
port_id: "porto_test"
name: "Test Port"
scale_factor: 10.0  # meters per unit

nodes:
  - id: "gate_main"
    x: 0
    y: 10
    type: "GATE"
    name: "Main Gate"
    
  - id: "dock_1"
    x: 18
    y: 12
    type: "DOCK"
    name: "Dock 1"

edges:
  - from: "gate_main"
    to: "int_entry"
    bidirectional: true
    speed_limit: 20
    restrictions:
      - type: "CARGO_PROHIBITED"
        affected_cargo: ["CLASS_1_EXPLOSIVES"]
```

### Node Types

| Type | Description |
|------|-------------|
| GATE | Port entrance/exit |
| DOCK | Loading/unloading berth |
| TERMINAL | Storage area |
| INTERSECTION | Road junction |
| INSPECTION_ZONE | Customs/inspection |
| HAZMAT_STORAGE | Hazardous materials zone |
| WEIGH_STATION | Weighbridge |

### Cargo Classes (IMO)

| Class | Description |
|-------|-------------|
| GENERAL | General cargo |
| CLASS_1_EXPLOSIVES | Explosives |
| CLASS_3_FLAMMABLE | Flammable liquids |
| CLASS_7_RADIOACTIVE | Radioactive materials |
| REFRIGERATED | Temperature controlled |
| OVERSIZED | Oversized cargo |

### Zone Statuses

| Status | Weight Multiplier | Effect |
|--------|-------------------|--------|
| NORMAL | 1.0x | Standard routing |
| CONGESTED | 2.5x | Prefers alternatives |
| UNDER_CONSTRUCTION | 3.0x | Avoids if possible |
| CLOSED | Infinity | Blocked |

## Usage Example

```python
from graph_builder import GraphBuilderEngine
from route_planner_v2 import CargoClass, ZoneStatus

# 1. Load port graph
engine = GraphBuilderEngine()
graph = engine.from_yaml("config/port_test.yaml")

# 2. Calculate route
cost, nodes, edges = graph.find_route(
    start="gate_main",
    end="dock_1",
    cargo=CargoClass.GENERAL
)

print(f"Route: {' -> '.join(n.name for n in nodes)}")
print(f"Distance: {cost:.0f}m")
print(f"Time: {graph.estimate_travel_time(edges)}")

# 3. Simulate congestion
graph.update_zone_status(
    affected_edges=["int_central->int_north"],
    status=ZoneStatus.CONGESTED,
    reason="Accident"
)

# 4. Recalculate (will find alternative if available)
cost, nodes, edges = graph.find_route("gate_main", "dock_1")
```

## Files

| File | Description |
|------|-------------|
| [graph_builder.py](../../src/V_APP/decision_engine/src/graph_builder.py) | Graph building engine |
| [route_planner_v2.py](../../src/V_APP/decision_engine/src/route_planner_v2.py) | Graph classes and routing |
| [port_test.yaml](../../src/V_APP/decision_engine/config/port_test.yaml) | Test port configuration |

## New Port Setup Workflow

```
1. CREATE CONFIG
   - Define nodes (gates, docks, intersections)
   - Define edges (roads with restrictions)
   - Set scale factor (meters per unit)

2. VALIDATE
   $ python graph_builder.py config/port_test.yaml

3. INTEGRATE
   - Load graph in decision_engine
   - Use find_route() for path calculation
```

## Future Considerations

- **GIS Integration**: Import from GeoJSON/QGIS for real port data
- **Real-time Updates**: IoT sensors for dynamic zone conditions
- **API Layer**: REST endpoints when frontend integration needed
