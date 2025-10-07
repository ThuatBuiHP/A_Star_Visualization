# Copilot Instructions for This Codebase

## Project Overview
This repository contains Python implementations of graph algorithms, with a focus on Dijkstra's algorithm and graph construction for IoT or wireless network scenarios. The code is designed for experimentation with different cost functions and graph connectivity models.

## Key Files
- `iot_dijkstra.py`: Main file. Contains:
  - Cost functions: `cost_distance`, `cost_hop`, `cost_energy`
  - Graph builders: `build_graph_uniform_R`, `build_graph_per_node_R`
  - Dijkstra's algorithm: `dijkstra`
  - Example usage in `__main__`
- No external dependencies beyond Python standard library (`math`, `heapq`).

## Patterns & Conventions
- Node coordinates are stored as `Dict[int, Tuple[float, float]]`.
- Graphs are represented as adjacency lists: `Dict[int, List[Tuple[int, float]]]`.
- Cost functions are passed as arguments to graph builders for flexibility.
- Two graph construction modes:
  - Uniform radius (undirected)
  - Per-node radius (directed or undirected)
- Dijkstra's returns both path and cost. If unreachable, returns `(None, inf)`.
- Example usage is provided at the bottom of `iot_dijkstra.py` for quick testing.

## Developer Workflows
- Run the main example: `python iot_dijkstra.py`
- No build step required.
- No test suite is present; validate changes by running the script and checking output.
- To add new cost functions or graph types, follow the pattern in `iot_dijkstra.py`.

## Project-Specific Advice for AI Agents
- When adding new algorithms, keep them modular and follow the function signature style in `iot_dijkstra.py`.
- Document new cost functions and graph construction methods with docstrings.
- If adding tests, place them in a new file (e.g., `test_iot_dijkstra.py`) and use assert-based checks.
- Avoid introducing external dependencies unless necessary for new features.

## Example: Adding a New Cost Function
```python
# Example: Manhattan distance cost
 def cost_manhattan(a: Coord, b: Coord) -> float:
     return abs(a[0] - b[0]) + abs(a[1] - b[1])
```

---
For questions or unclear conventions, review `iot_dijkstra.py` for examples or ask for clarification.