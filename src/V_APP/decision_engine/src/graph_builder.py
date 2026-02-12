"""
Graph Builder Engine
====================
Engine to generate port navigation graphs from YAML configuration files.
"""

import yaml
from pathlib import Path
from typing import Optional, Union
from dataclasses import dataclass, field

from route_planner_v2 import (
    PortGraph, Node, Edge, NodeType, CargoClass, ZoneStatus,
    ZoneCondition, Restriction, RestrictionType, euclidean_distance
)


# =============================================================================
# Graph Builder Engine
# =============================================================================

class GraphBuilderEngine:
    """
    Engine for building navigation graphs from configuration files.
    
    Usage:
        engine = GraphBuilderEngine()
        graph = engine.from_yaml("config/port.yaml")
    """
    
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
    
    def from_yaml(self, filepath: Union[str, Path]) -> PortGraph:
        """Load graph from YAML file."""
        filepath = Path(filepath)
        
        if not filepath.exists():
            raise FileNotFoundError(f"Config file not found: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        return self._build_from_dict(data)
    
    def from_dict(self, data: dict) -> PortGraph:
        """Load graph from Python dictionary."""
        return self._build_from_dict(data)
    
    def _build_from_dict(self, data: dict) -> PortGraph:
        """Build graph from configuration dictionary."""
        self.errors = []
        self.warnings = []
        
        port_id = data.get('port_id', 'unknown_port')
        port_name = data.get('name', port_id)
        scale = data.get('scale_factor', 1.0)
        
        graph = PortGraph(port_id)
        node_map: dict[str, Node] = {}
        
        # Process nodes
        for node_data in data.get('nodes', []):
            node = self._parse_node(node_data, scale)
            if node:
                graph.add_node(node)
                node_map[node.id] = node
        
        # Process edges
        for edge_data in data.get('edges', []):
            self._parse_and_add_edges(graph, edge_data, node_map, scale)
        
        # Validation
        self._validate_graph(graph)
        
        if self.errors:
            print(f"[WARN] Graph built with {len(self.errors)} errors:")
            for err in self.errors[:5]:
                print(f"   - {err}")
        
        print(f"[OK] Graph '{port_name}' built: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
        
        return graph
    
    def _parse_node(self, data: dict, scale: float) -> Optional[Node]:
        """Parse node configuration."""
        try:
            node_id = data['id']
            x = data['x'] * scale
            y = data['y'] * scale
            type_str = data.get('type', 'INTERSECTION')
            name = data.get('name', node_id)
            
            try:
                node_type = NodeType[type_str.upper()]
            except KeyError:
                self.warnings.append(f"Unknown node type '{type_str}' for {node_id}")
                node_type = NodeType.INTERSECTION
            
            node = Node(x, y, node_type, node_id, name)
            node.metadata = data.get('metadata', {})
            
            return node
            
        except KeyError as e:
            self.errors.append(f"Missing required field in node: {e}")
            return None
    
    def _parse_and_add_edges(
        self, 
        graph: PortGraph, 
        data: dict, 
        node_map: dict[str, Node],
        scale: float
    ) -> None:
        """Parse and add edge(s) to graph."""
        try:
            from_id = data['from']
            to_id = data['to']
            
            from_node = node_map.get(from_id)
            to_node = node_map.get(to_id)
            
            if not from_node:
                self.errors.append(f"Unknown from_node: {from_id}")
                return
            if not to_node:
                self.errors.append(f"Unknown to_node: {to_id}")
                return
            
            weight = data.get('weight')
            if weight is not None:
                weight *= scale
            
            bidirectional = data.get('bidirectional', True)
            speed_limit = data.get('speed_limit', 30.0)
            lanes = data.get('lanes', 1)
            
            # Create edge
            edge1 = Edge(from_node, to_node, weight)
            edge1.speed_limit = speed_limit
            edge1.lanes = lanes
            
            # Apply initial condition
            initial_condition = data.get('initial_condition')
            if initial_condition:
                try:
                    status = ZoneStatus[initial_condition.upper()]
                    edge1.condition = ZoneCondition(status)
                except KeyError:
                    pass
            
            # Apply restrictions
            for restr_data in data.get('restrictions', []):
                self._apply_restriction(edge1, restr_data)
            
            graph.add_edge(edge1)
            
            if bidirectional:
                edge2 = Edge(to_node, from_node, weight)
                edge2.speed_limit = speed_limit
                edge2.lanes = lanes
                edge2.condition = edge1.condition
                edge2.restrictions = edge1.restrictions.copy()
                graph.add_edge(edge2)
                
        except KeyError as e:
            self.errors.append(f"Missing required field in edge: {e}")
    
    def _apply_restriction(self, edge: Edge, restr_data: dict) -> None:
        """Apply restriction to an edge."""
        try:
            restr_type = RestrictionType[restr_data['type'].upper()]
            affected_cargo = []
            
            for cargo_str in restr_data.get('affected_cargo', []):
                try:
                    affected_cargo.append(CargoClass[cargo_str.upper()])
                except KeyError:
                    pass
            
            restriction = Restriction(
                type=restr_type,
                value=restr_data.get('value'),
                affected_cargo=affected_cargo
            )
            
            edge.restrictions.append(restriction)
            
        except KeyError:
            pass
    
    def _validate_graph(self, graph: PortGraph) -> None:
        """Validate graph integrity."""
        gates = [n for n in graph.nodes.values() if n.type == NodeType.GATE]
        docks = [n for n in graph.nodes.values() if n.type == NodeType.DOCK]
        
        if not gates:
            self.warnings.append("No GATE nodes found")
        if not docks:
            self.warnings.append("No DOCK nodes found")
        
        # Check connectivity
        for gate in gates:
            reachable = self._bfs_reachable(graph, gate)
            unreachable_docks = [d for d in docks if d not in reachable]
            if unreachable_docks:
                self.warnings.append(
                    f"Docks unreachable from {gate.id}: {[d.id for d in unreachable_docks]}"
                )
    
    def _bfs_reachable(self, graph: PortGraph, start: Node) -> set[Node]:
        """BFS to find reachable nodes."""
        visited = set()
        queue = [start]
        
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            
            for edge in graph.adjacency_list.get(node, []):
                if edge.to_node not in visited:
                    queue.append(edge.to_node)
        
        return visited


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python graph_builder.py <config.yaml>")
        sys.exit(1)
    
    engine = GraphBuilderEngine()
    graph = engine.from_yaml(sys.argv[1])
    
    print(f"\nGraph loaded:")
    print(f"  Nodes: {len(graph.nodes)}")
    print(f"  Edges: {len(graph.edges)}")
