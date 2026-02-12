"""
Route Planner V2 - Port Navigation Core
========================================
Core classes and routing algorithms for port internal navigation.

Features:
- Graph-based port topology (nodes, edges)
- Cargo type restrictions (IMO classes)
- Dynamic zone conditions (congestion, construction)
- Dijkstra routing with adaptive weights
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, Callable
import heapq
import itertools
from datetime import datetime, timedelta


def euclidean_distance(point1: tuple[float, float], point2: tuple[float, float]) -> float:
    """Calculate the Euclidean distance between two 2D points."""
    return ((point1[0] - point2[0]) ** 2 + (point1[1] - point2[1]) ** 2) ** 0.5


# =============================================================================
# ENUMS
# =============================================================================

class NodeType(Enum):
    """Types of nodes in the port graph."""
    INTERSECTION = auto()
    DOCK = auto()
    GATE = auto()
    TERMINAL = auto()
    BUILDING = auto()
    INSPECTION_ZONE = auto()
    HAZMAT_STORAGE = auto()
    PARKING_AREA = auto()
    WEIGH_STATION = auto()


class CargoClass(Enum):
    """IMO dangerous goods classes for route restrictions."""
    GENERAL = auto()
    CLASS_1_EXPLOSIVES = auto()
    CLASS_2_GASES = auto()
    CLASS_3_FLAMMABLE = auto()
    CLASS_4_SOLIDS = auto()
    CLASS_5_OXIDIZERS = auto()
    CLASS_6_TOXIC = auto()
    CLASS_7_RADIOACTIVE = auto()
    CLASS_8_CORROSIVE = auto()
    CLASS_9_MISC = auto()
    REFRIGERATED = auto()
    OVERSIZED = auto()


class ZoneStatus(Enum):
    """Dynamic status of a zone/edge."""
    NORMAL = auto()
    CONGESTED = auto()
    UNDER_CONSTRUCTION = auto()
    ENVIRONMENTAL_RISK = auto()
    EMERGENCY_ONLY = auto()
    CLOSED = auto()


class RestrictionType(Enum):
    """Types of restrictions that can be applied."""
    CARGO_PROHIBITED = auto()
    WEIGHT_LIMIT = auto()
    HEIGHT_LIMIT = auto()
    TIME_WINDOW = auto()
    SPEED_LIMIT = auto()


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Restriction:
    """Represents a restriction on an edge."""
    type: RestrictionType
    value: any = None
    affected_cargo: list[CargoClass] = field(default_factory=list)
    
    def applies_to_cargo(self, cargo: CargoClass) -> bool:
        """Check if the restriction applies to a cargo type."""
        if not self.affected_cargo:
            return True
        return cargo in self.affected_cargo


@dataclass
class ZoneCondition:
    """Dynamic condition of a zone (congestion, construction, etc.)."""
    status: ZoneStatus
    severity: float = 1.0
    reason: str = ""
    reported_at: datetime = field(default_factory=datetime.now)
    estimated_clear: Optional[datetime] = None
    
    def get_weight_multiplier(self) -> float:
        """Return the weight multiplier based on condition."""
        multipliers = {
            ZoneStatus.NORMAL: 1.0,
            ZoneStatus.CONGESTED: 2.5,
            ZoneStatus.UNDER_CONSTRUCTION: 3.0,
            ZoneStatus.ENVIRONMENTAL_RISK: 5.0,
            ZoneStatus.EMERGENCY_ONLY: 10.0,
            ZoneStatus.CLOSED: float('inf'),
        }
        return multipliers.get(self.status, 1.0) * self.severity


# =============================================================================
# CORE CLASSES
# =============================================================================

class Node:
    """Represents a point in the port graph."""
    
    def __init__(
        self, 
        x: float, 
        y: float, 
        node_type: NodeType,
        node_id: Optional[str] = None,
        name: Optional[str] = None
    ) -> None:
        self.x = x
        self.y = y
        self.type = node_type
        self.id = node_id or f"{node_type.name}_{x}_{y}"
        self.name = name or self.id
        self.metadata: dict = {}
    
    def __repr__(self) -> str:
        return f"Node({self.id}, type={self.type.name})"
    
    def __hash__(self) -> int:
        return hash(self.id)
    
    def __eq__(self, other) -> bool:
        if isinstance(other, Node):
            return self.id == other.id
        return False


class Edge:
    """Represents a connection between two nodes with restrictions support."""
    
    def __init__(
        self, 
        from_node: Node, 
        to_node: Node, 
        base_weight: Optional[float] = None,
        edge_id: Optional[str] = None
    ) -> None:
        self.from_node = from_node
        self.to_node = to_node
        self.id = edge_id or f"{from_node.id}->{to_node.id}"
        
        self._base_weight = base_weight if base_weight is not None else euclidean_distance(
            (from_node.x, from_node.y), (to_node.x, to_node.y)
        )
        
        self.restrictions: list[Restriction] = []
        self.condition: ZoneCondition = ZoneCondition(ZoneStatus.NORMAL)
        self.speed_limit: float = 30.0
        self.lanes: int = 1
    
    @property
    def base_weight(self) -> float:
        return self._base_weight
    
    @base_weight.setter
    def base_weight(self, value: float) -> None:
        if value < 0:
            raise ValueError("Edge weight cannot be negative!")
        self._base_weight = value
    
    def get_effective_weight(
        self, 
        cargo: CargoClass = CargoClass.GENERAL,
        at_time: Optional[datetime] = None
    ) -> float:
        """Calculate effective weight considering conditions and restrictions."""
        if self.condition.status == ZoneStatus.CLOSED:
            return float('inf')
        
        for restriction in self.restrictions:
            if restriction.type == RestrictionType.CARGO_PROHIBITED:
                if restriction.applies_to_cargo(cargo):
                    return float('inf')
        
        multiplier = self.condition.get_weight_multiplier()
        
        if cargo != CargoClass.GENERAL:
            if self.condition.status == ZoneStatus.ENVIRONMENTAL_RISK:
                multiplier *= 3.0
            elif self.condition.status == ZoneStatus.CONGESTED:
                multiplier *= 1.5
        
        return self._base_weight * multiplier
    
    def is_passable(self, cargo: CargoClass = CargoClass.GENERAL) -> bool:
        """Check if the edge is passable for a given cargo type."""
        return self.get_effective_weight(cargo) < float('inf')


# =============================================================================
# GRAPH
# =============================================================================

class PortGraph:
    """Port graph with routing support."""
    
    def __init__(self, port_id: str = "default_port") -> None:
        self.port_id = port_id
        self.nodes: dict[str, Node] = {}
        self.adjacency_list: dict[Node, list[Edge]] = {}
        self.edges: dict[str, Edge] = {}
        self._on_condition_change: list[Callable] = []
    
    def add_node(self, node: Node) -> None:
        """Add a node to the graph."""
        if node.id not in self.nodes:
            self.nodes[node.id] = node
            self.adjacency_list[node] = []
    
    def add_edge(self, edge: Edge) -> None:
        """Add a directed edge to the graph."""
        if edge.from_node.id not in self.nodes:
            self.add_node(edge.from_node)
        if edge.to_node.id not in self.nodes:
            self.add_node(edge.to_node)
        
        self.adjacency_list[edge.from_node].append(edge)
        self.edges[edge.id] = edge
    
    def add_bidirectional_edge(
        self, 
        node1: Node, 
        node2: Node, 
        weight: Optional[float] = None
    ) -> tuple[Edge, Edge]:
        """Add two edges (outbound and return) between two nodes."""
        edge1 = Edge(node1, node2, weight)
        edge2 = Edge(node2, node1, weight)
        self.add_edge(edge1)
        self.add_edge(edge2)
        return edge1, edge2
    
    def get_node(self, node_id: str) -> Optional[Node]:
        """Get a node by ID."""
        return self.nodes.get(node_id)
    
    def get_edge(self, edge_id: str) -> Optional[Edge]:
        """Get an edge by ID."""
        return self.edges.get(edge_id)
    
    def update_edge_condition(self, edge_id: str, condition: ZoneCondition) -> bool:
        """Update the condition of an edge."""
        edge = self.edges.get(edge_id)
        if not edge:
            return False
        edge.condition = condition
        return True
    
    def update_zone_status(
        self,
        affected_edges: list[str],
        status: ZoneStatus,
        reason: str = "",
        severity: float = 1.0
    ) -> int:
        """Update the status of multiple edges (a zone)."""
        condition = ZoneCondition(status=status, severity=severity, reason=reason)
        updated = 0
        for edge_id in affected_edges:
            if self.update_edge_condition(edge_id, condition):
                updated += 1
        return updated
    
    def find_route(
        self,
        start: Node | str,
        end: Node | str,
        cargo: CargoClass = CargoClass.GENERAL,
        avoid_edges: Optional[set[str]] = None
    ) -> tuple[float, list[Node], list[Edge]]:
        """
        Find the best route using Dijkstra with dynamic weights.
        Returns: (total_cost, node_list, edge_list)
        """
        if isinstance(start, str):
            start = self.nodes.get(start)
        if isinstance(end, str):
            end = self.nodes.get(end)
        
        if not start or not end:
            return float('inf'), [], []
        
        avoid_edges = avoid_edges or set()
        counter = itertools.count()
        queue = [(0, next(counter), start, [], [])]
        visited = set()
        
        while queue:
            cost, _, current, path_nodes, path_edges = heapq.heappop(queue)
            
            if current in visited:
                continue
            visited.add(current)
            path_nodes = path_nodes + [current]
            
            if current == end:
                return cost, path_nodes, path_edges
            
            for edge in self.adjacency_list.get(current, []):
                if edge.to_node in visited:
                    continue
                if edge.id in avoid_edges:
                    continue
                
                edge_cost = edge.get_effective_weight(cargo)
                
                if edge_cost < float('inf'):
                    heapq.heappush(queue, (
                        cost + edge_cost,
                        next(counter),
                        edge.to_node,
                        path_nodes,
                        path_edges + [edge]
                    ))
        
        return float('inf'), [], []
    
    def find_alternative_routes(
        self,
        start: Node | str,
        end: Node | str,
        cargo: CargoClass = CargoClass.GENERAL,
        num_alternatives: int = 3
    ) -> list[tuple[float, list[Node], list[Edge]]]:
        """Find multiple alternative routes."""
        routes = []
        avoid_edges: set[str] = set()
        
        for _ in range(num_alternatives):
            cost, nodes, edges = self.find_route(start, end, cargo, avoid_edges)
            
            if cost == float('inf'):
                break
            
            routes.append((cost, nodes, edges))
            
            if edges:
                mid_idx = len(edges) // 2
                avoid_edges.add(edges[mid_idx].id)
        
        return routes
    
    def estimate_travel_time(
        self,
        route_edges: list[Edge],
        cargo: CargoClass = CargoClass.GENERAL
    ) -> timedelta:
        """Estimate travel time for a route."""
        total_seconds = 0.0
        
        for edge in route_edges:
            distance_km = edge.base_weight / 1000
            effective_speed = edge.speed_limit
            
            if edge.condition.status == ZoneStatus.CONGESTED:
                effective_speed *= 0.4
            elif edge.condition.status == ZoneStatus.UNDER_CONSTRUCTION:
                effective_speed *= 0.3
            
            if cargo not in [CargoClass.GENERAL, CargoClass.REFRIGERATED]:
                effective_speed = min(effective_speed, 20.0)
            
            time_hours = distance_km / max(effective_speed, 5.0)
            total_seconds += time_hours * 3600
        
        return timedelta(seconds=total_seconds)
    
    def to_dict(self) -> dict:
        """Serialize the graph to dictionary."""
        return {
            "port_id": self.port_id,
            "nodes": [
                {
                    "id": n.id,
                    "name": n.name,
                    "type": n.type.name,
                    "x": n.x,
                    "y": n.y,
                    "metadata": n.metadata
                }
                for n in self.nodes.values()
            ],
            "edges": [
                {
                    "id": e.id,
                    "from": e.from_node.id,
                    "to": e.to_node.id,
                    "base_weight": e.base_weight,
                    "condition": e.condition.status.name,
                    "restrictions": [r.type.name for r in e.restrictions]
                }
                for e in self.edges.values()
            ]
        }


# =============================================================================
# DEMO PORT - For Tests
# =============================================================================

def create_demo_port() -> PortGraph:
    """Create a simple demo port for testing."""
    graph = PortGraph("demo_port")
    
    # Gates
    gate_main = Node(0, 10, NodeType.GATE, "gate_main", "Main Gate")
    gate_hazmat = Node(0, 2, NodeType.GATE, "gate_hazmat", "Hazmat Gate")
    
    # Intersections
    int_entry = Node(4, 6, NodeType.INTERSECTION, "int_entry", "Entry Junction")
    int_central = Node(8, 6, NodeType.INTERSECTION, "int_central", "Central Junction")
    
    # Terminals
    terminal_a = Node(12, 10, NodeType.TERMINAL, "terminal_a", "Terminal A")
    hazmat_zone = Node(12, 2, NodeType.HAZMAT_STORAGE, "hazmat_zone", "Hazmat Zone")
    
    # Docks
    dock_1 = Node(16, 10, NodeType.DOCK, "dock_1", "Dock 1")
    dock_2 = Node(16, 2, NodeType.DOCK, "dock_2", "Dock 2 (Hazmat)")
    
    # Add nodes
    for node in [gate_main, gate_hazmat, int_entry, int_central, 
                 terminal_a, hazmat_zone, dock_1, dock_2]:
        graph.add_node(node)
    
    # Add edges
    graph.add_bidirectional_edge(gate_main, int_entry)
    graph.add_bidirectional_edge(gate_hazmat, int_entry)
    graph.add_bidirectional_edge(int_entry, int_central)
    graph.add_bidirectional_edge(int_central, terminal_a)
    graph.add_bidirectional_edge(int_central, hazmat_zone)
    graph.add_bidirectional_edge(terminal_a, dock_1)
    graph.add_bidirectional_edge(hazmat_zone, dock_2)
    
    # Add HAZMAT restrictions on normal dock
    for edge_id in ["terminal_a->dock_1", "dock_1->terminal_a"]:
        edge = graph.get_edge(edge_id)
        if edge:
            edge.restrictions.append(Restriction(
                type=RestrictionType.CARGO_PROHIBITED,
                affected_cargo=[
                    CargoClass.CLASS_1_EXPLOSIVES,
                    CargoClass.CLASS_3_FLAMMABLE,
                    CargoClass.CLASS_7_RADIOACTIVE
                ]
            ))
    
    return graph


if __name__ == "__main__":
    # Simple test
    graph = create_demo_port()
    
    print("Demo Port Graph")
    print(f"Nodes: {len(graph.nodes)}")
    print(f"Edges: {len(graph.edges)}")
    
    # Test routing
    cost, path, edges = graph.find_route("gate_main", "dock_1", CargoClass.GENERAL)
    print(f"\nRoute (general cargo): {' -> '.join(n.name for n in path)}")
    print(f"Cost: {cost:.2f}m")
    
    cost, path, edges = graph.find_route("gate_hazmat", "dock_2", CargoClass.CLASS_3_FLAMMABLE)
    print(f"\nRoute (hazmat): {' -> '.join(n.name for n in path)}")
    print(f"Cost: {cost:.2f}m")
