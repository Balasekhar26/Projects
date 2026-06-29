# K21-42: Spatial Reasoning Specification

This document defines the spatial coordinates system, distances calculation, containment rules, and navigation graphs in the Physical domain.

---

## 1. Coordinate Systems & Containment

The Physical domain represents coordinates in three formats:
1. **Geometric Coordinate (3D)**: $\langle x, y, z \rangle$ coordinates representing metric positions.
2. **Containment Tree (Topology)**: Hierarchical containment mappings:
   $$\text{Device} \subseteq \text{Room} \subseteq \text{Building} \subseteq \text{Region}$$
3. **Region Bounding Box**: Defining structural limits:
   $$\text{Box} = \langle \vec{x}_{min}, \vec{x}_{max} \rangle$$

---

## 2. Navigation Graphs & Distances

- **Navigation Graph**:
  - Vertices ($V$) represent waypoints or locations.
  - Edges ($E$) represent paths carrying a cost weight (Euclidean distance or routing delays).
- **Distance Calculation**:
  - Euclidean distance: $d = \|\vec{x}_1 - \vec{x}_2\|_2$
  - Containment distance: calculated as path distance in the topological tree.
- **Collision Checking**: The transition validator checks if two physical entities share the same region or overlapping bounding boxes, generating risk warnings if a collision is detected.
