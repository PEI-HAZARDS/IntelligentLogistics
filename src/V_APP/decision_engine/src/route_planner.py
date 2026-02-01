from enum import Enum
from matplotlib.patheffects import AbstractPathEffect, SimplePatchShadow
import networkx as nx
import matplotlib.pyplot as plt
import heapq
import itertools
import matplotlib.patches as mpatches
import numpy as np

def euclidean_distance(point1: tuple[float, float], point2: tuple[float, float]) -> float:
    """Calculate the Euclidean distance between two 2D points."""
    return ((point1[0] - point2[0]) ** 2 + (point1[1] - point2[1]) ** 2) ** 0.5

class NodeType(Enum):
    INTERSECTION = 1
    DOCK = 2
    GATE = 3
    TERMINAL = 4
    BUILDING = 5

class Node:
    def __init__(self, x: int, y: int, type: NodeType) -> None:
        self.x = x
        self.y = y
        self.type = type
    

class Edge:
    def __init__(self, from_node: Node, to_node: Node, weight: float | None) -> None:
        self.from_node = from_node
        self.to_node = to_node
        self.weight = weight if weight is not None else euclidean_distance(
            (from_node.x, from_node.y), (to_node.x, to_node.y)
        )
        self.rules = []  # Placeholder for future traffic rules
    
    @property
    def weight(self):
        """Returns the weight of the edge."""
        return self._weight

    @weight.setter
    def weight(self, value):
        """Sets the weight, but blocks negative numbers."""
        if value < 0:
            raise ValueError("Edge weight cannot be negative!")
        self._weight = value

class Graph:
    def __init__(self) -> None:
        self.nodes: list[Node] = []
        self.adjacency_list: dict[Node, list[Edge]] = {}

    def add_node(self, node: Node) -> None:
        if node not in self.adjacency_list:
            self.nodes.append(node)
            self.adjacency_list[node] = []

    def add_edge(self, edge: Edge) -> None:
        """Adds a directed edge. For bi-directional, add two separate edges."""
        if edge.from_node not in self.adjacency_list:
            self.add_node(edge.from_node)
        if edge.to_node not in self.adjacency_list:
            self.add_node(edge.to_node)
            
        self.adjacency_list[edge.from_node].append(edge)

    def get_neighbors(self, node: Node) -> list[Node]:
        """O(out-degree) complexity: only checks edges originating from this node."""
        return [edge.to_node for edge in self.adjacency_list.get(node, [])]
    
    def djikstra(self, start: Node, end: Node) -> tuple[float, list[Node]]:
        # Unique counter to break ties in the priority queue
        counter = itertools.count()
        
        # (cost, count, current_node, path)
        queue = [(0, next(counter), start, [])]  
        visited = set()

        while queue:
            # Now heapq compares cost, then count (which is always unique)
            cost, _, current_node, path = heapq.heappop(queue)

            if current_node in visited:
                continue
            visited.add(current_node)

            path = path + [current_node]

            if current_node == end:
                return cost, path

            for edge in self.adjacency_list.get(current_node, []):
                if edge.to_node not in visited:
                    # Add the next counter value here
                    heapq.heappush(queue, (cost + edge.weight, next(counter), edge.to_node, path))

        return float('inf'), []

    def visualize(self, path: list[Node] | None = None) -> None:
        # 1. Logic Graph to NX Graph
        display_g = nx.DiGraph()
        pos = {}
        for node in self.nodes:
            display_g.add_node(node)
            pos[node] = (node.x, node.y)
        
        for node, edges in self.adjacency_list.items():
            for edge in edges:
                display_g.add_edge(edge.from_node, edge.to_node)

        # 2. Setup Plot
        _, ax = plt.subplots(figsize=(10, 10))
        ax.set_facecolor('#fdfdfd')
        ax.grid(True, which='both', color='#e0e0e0', linestyle='-', linewidth=0.5, zorder=0)

        # 3. DRAW EDGES (Standard Roads)
        nx.draw_networkx_edges(
            display_g, 
            pos, 
            ax=ax,
            edge_color='#3498db',
            width=1.2,
            arrowsize=12,
            arrowstyle='-|>',
            alpha=0.3,     # Lower alpha so highlighted route pops
            node_size=200
        )

        # 4. HIGHLIGHT THE ROUTE
        if path and len(path) > 1:
            # Convert node list [A, B, C] into edge list [(A, B), (B, C)]
            path_edges = list(zip(path, path[1:]))
            nx.draw_networkx_edges(
                display_g,
                pos,
                ax=ax,
                edgelist=path_edges,
                edge_color='#f39c12', # Vibrant Orange
                width=3.0,            # Thicker line
                arrowsize=18,
                arrowstyle='-|>',
                node_size=200,
                alpha=1.0,
            )

        # 5. DRAW EDGE WEIGHT LABELS
        # --- Collect all edges and detect bidirectional pairs ---
        # Key: frozenset({A, B}) -> list of Edge objects between A and B
        edge_pairs: dict[frozenset, list[Edge]] = {}
        for node, edges in self.adjacency_list.items():
            for edge in edges:
                key = frozenset({edge.from_node, edge.to_node})
                edge_pairs.setdefault(key, []).append(edge)

        for key, edges in edge_pairs.items():
            is_bidirectional = len(edges) == 2

            # Canonical direction: always computed from the "lesser" node to the "greater"
            # so that perp is the SAME for both edges in a bidirectional pair.
            nodes_in_pair = sorted(key, key=lambda n: (n.x, n.y, id(n)))
            canon_p1 = np.array([nodes_in_pair[0].x, nodes_in_pair[0].y], dtype=float)
            canon_p2 = np.array([nodes_in_pair[1].x, nodes_in_pair[1].y], dtype=float)
            canon_dir = canon_p2 - canon_p1
            canon_len = np.linalg.norm(canon_dir)
            if canon_len == 0:
                continue
            canon_unit = canon_dir / canon_len
            # Perpendicular (left-normal of canonical direction) — shared by both edges
            perp = np.array([-canon_unit[1], canon_unit[0]])

            for edge in edges:
                p1 = np.array([edge.from_node.x, edge.from_node.y], dtype=float)
                p2 = np.array([edge.to_node.x, edge.to_node.y], dtype=float)

                # Midpoint of the edge
                mid = (p1 + p2) / 2.0

                # Per-edge direction (for the small arrow indicator)
                direction = p2 - p1
                length = np.linalg.norm(direction)
                if length == 0:
                    continue
                unit_dir = direction / length

                # --- Determine offset ---
                # For bidirectional pairs: one label goes above the edge (+perp), one below (-perp).
                # A consistent sort picks which edge is which so labels don't swap on re-render.
                if is_bidirectional:
                    sorted_edges = sorted(edges, key=lambda e: (e.from_node.x, e.from_node.y, e.to_node.x, e.to_node.y))
                    sign = 1.0 if edge is sorted_edges[0] else -1.0
                    offset_dist = 0.45   # How far the arrow+label band sits from the edge line
                else:
                    sign = 1.0           # Single edges: place above
                    offset_dist = 0.30

                # Base position for the arrow (sits at this offset from edge midpoint)
                arrow_center = mid + perp * (sign * offset_dist)

                # --- Small directional arrow indicator ---
                arrow_len = 0.30
                arrow_start = arrow_center - unit_dir * (arrow_len / 2)
                arrow_end   = arrow_center + unit_dir * (arrow_len / 2)

                # Color: orange if this edge is part of the highlighted path, else muted blue
                is_path_edge = (
                    path and len(path) > 1 and
                    any(path[i] == edge.from_node and path[i+1] == edge.to_node for i in range(len(path)-1))
                )
                arrow_color = '#f39c12' if is_path_edge else '#5d6d7e'
                text_color  = '#f39c12' if is_path_edge else '#2c3e50'
                bbox_color  = '#fff8e1' if is_path_edge else '#eef2f7'

                # Draw the small direction arrow
                ax.annotate(
                    '',
                    xy=arrow_end,
                    xytext=arrow_start,
                    arrowprops=dict(
                        arrowstyle='-|>',
                        color=arrow_color,
                        lw=1.4,
                    ),
                    zorder=7
                )

                # Weight label: pushed one more step outward (same perp direction) so it
                # doesn't collide with the arrow shaft.
                label_pos = arrow_center + perp * (sign * 0.22)

                ax.text(
                    label_pos[0], label_pos[1],
                    f"{edge.weight:.2f}",
                    fontsize=6.5,
                    ha='center', va='center',
                    family='monospace',
                    fontweight='bold',
                    color=text_color,
                    bbox=dict(boxstyle='round,pad=0.15', facecolor=bbox_color, edgecolor=arrow_color, linewidth=0.7, alpha=0.9),
                    zorder=8
                )

        # 6. DRAW NODES (With Shadow Logic)
        shadow: list[AbstractPathEffect] = [
            SimplePatchShadow(offset=(1, -1), shadow_rgbFace='black', alpha=0.15)
        ]
        
        color_map = {
            NodeType.INTERSECTION: '#f1c40f',
            NodeType.BUILDING: '#9b59b6',
            NodeType.TERMINAL: '#34495e',
            NodeType.GATE: '#2ecc71',
            NodeType.DOCK: '#e74c3c'
        }

        for node in self.nodes:
            color = color_map.get(node.type, '#7f8c8d')
            
            # Highlight start/end nodes of the path if they exist
            is_endpoint = path and (node == path[0] or node == path[-1])
            node_size = 120 if is_endpoint else 80
            edge_w = 2.0 if is_endpoint else 0.8
            edge_c = 'black' if is_endpoint else 'white'

            scatter = ax.scatter(node.x, node.y, c=color, s=node_size, 
                                 edgecolors=edge_c, linewidth=edge_w, zorder=3)
            scatter.set_path_effects(shadow)

            ax.text(node.x, node.y - 0.45, f"{node.type.name}\n({node.x}, {node.y})",
                    fontsize=7, ha='center', va='top', family='monospace', 
                    fontweight='bold', alpha=0.7, zorder=4)

        # 7. Cleanup
        ax.set_aspect('equal')
        ax.set_xticks(range(int(min(n.x for n in self.nodes))-1, int(max(n.x for n in self.nodes))+2))
        ax.set_yticks(range(int(min(n.y for n in self.nodes))-1, int(max(n.y for n in self.nodes))+2))
        ax.set_xticklabels([])
        ax.set_yticklabels([])
        
        for spine in ax.spines.values():
            spine.set_visible(False)
            
        plt.tight_layout()
        plt.show()
        
def main():
    graph = Graph()

    # 1. GATES (Entry/Exit Points)
    gate_north = Node(0, 10, NodeType.GATE)
    gate_south = Node(0, 2, NodeType.GATE)

    # 2. BUILDINGS (Admin & Customs)
    admin_office = Node(2, 6, NodeType.BUILDING)
    customs_hq = Node(4, 10, NodeType.BUILDING)

    # 3. INTERSECTIONS (The Road Network)
    int_entry = Node(4, 6, NodeType.INTERSECTION)
    int_central = Node(8, 6, NodeType.INTERSECTION)
    int_north_term = Node(8, 10, NodeType.INTERSECTION)
    int_south_term = Node(8, 2, NodeType.INTERSECTION)

    # 4. TERMINALS (Storage areas)
    term_a = Node(12, 10, NodeType.TERMINAL)
    term_b = Node(12, 2, NodeType.TERMINAL)

    # 5. DOCKS (Where ships arrive)
    dock_1 = Node(16, 12, NodeType.DOCK)
    dock_2 = Node(16, 8, NodeType.DOCK)
    dock_3 = Node(16, 4, NodeType.DOCK)
    dock_4 = Node(16, 0, NodeType.DOCK)

    # Register all nodes
    nodes = [gate_north, gate_south, admin_office, customs_hq, int_entry, 
             int_central, int_north_term, int_south_term, term_a, term_b, 
             dock_1, dock_2, dock_3, dock_4]
    for n in nodes:
        graph.add_node(n)

    # HELPER: Quick bi-directional road
    def add_road(n1, n2):
        graph.add_edge(Edge(n1, n2, None))
        graph.add_edge(Edge(n2, n1, None))

    # --- DEFINE THE FLOW ---

    # Entry Roads (Bi-directional)
    add_road(gate_north, admin_office)
    add_road(gate_south, admin_office)
    add_road(admin_office, int_entry)

    # One-Way Security/Customs Check
    graph.add_edge(Edge(int_entry, customs_hq, None))
    graph.add_edge(Edge(customs_hq, int_north_term, None))

    # Central Spines
    edge_1 = Edge(int_entry, int_central, None)
    edge_2 = Edge(int_central, int_entry, None)
    
    graph.add_edge(edge_1)
    graph.add_edge(edge_2)
    
    add_road(int_central, int_north_term)
    add_road(int_central, int_south_term)

    # Terminal Access
    add_road(int_north_term, term_a)
    add_road(int_south_term, term_b)

    # Dock Connections (The final destination)
    add_road(term_a, dock_1)
    add_road(term_a, dock_2)
    add_road(term_b, dock_3)
    add_road(term_b, dock_4)
    
    star_node = gate_north
    end_node = dock_3
    cost, path = graph.djikstra(star_node, end_node)
    print(f"Cost from {star_node.type.name} to {end_node.type.name}: {cost:.2f}")
    print("Path:")
    for p in path:
        print(f" - {p.type.name} at ({p.x}, {p.y})")

    graph.visualize(path=path)

if __name__ == "__main__":
    main()