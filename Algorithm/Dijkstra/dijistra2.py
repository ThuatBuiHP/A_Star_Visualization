from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Set, Callable, Any
import heapq
import math

# ======================
# 1) MÔ HÌNH DỮ LIỆU
# ======================

@dataclass(frozen=True)
class Node:
    id: str
    x: float
    y: float
    r: Optional[float] = None  # r có thể không dùng trong chế độ 'paths'

@dataclass(frozen=True)
class Path:
    id: str
    start_id: str
    end_id: str
    length: float

def euclid(a: "Node", b: "Node") -> float:
    return math.hypot(a.x - b.x, a.y - b.y)

def in_range(src: "Node", dst: "Node") -> bool:
    if src.r is None:
        return False
    return euclid(src, dst) <= src.r

# ======================
# 2) XÂY ĐỒ THỊ
# ======================

def build_graph(
    nodes: Dict[str, Node],
    mode: str = "range",  # 'range' (như cũ) hoặc 'paths' (theo JSON cạnh)
    paths: Optional[List[Path]] = None,
    undirected: bool = False,              # nếu True và mode='paths' -> thêm cạnh ngược
    weight_fn: Callable[[Node, Node], float] = euclid
) -> Dict[str, List[Tuple[str, float]]]:
    """
    Trả về adjacency list: {node_id: [(neighbor_id, weight), ...]}

    mode='range':
        - 'both' trước đây ~ vô hướng đối xứng; ở đây gộp lại bằng cách xét min(r_u, r_v).
        - 'either' trước đây ~ có hướng theo vùng phủ; ở đây ta quy về directed theo r của từng node.
        => Để đơn giản hoá, trong bản vá này 'range' tạo cả hai chiều
           chỉ khi u và v "nhìn thấy nhau" (đối xứng). Nếu bạn muốn 'either',
           có thể tách thêm tham số range_mode='both'/'either' tuỳ bạn.

    mode='paths':
        - Dùng danh sách paths (một chiều). Nếu undirected=True, tự thêm cạnh ngược.
        - Trọng số = Path.length (bắt buộc có).
    """
    ids = list(nodes.keys())
    adj: Dict[str, List[Tuple[str, float]]] = {i: [] for i in ids}

    if mode == "paths":
        if paths is None:
            raise ValueError("mode='paths' cần truyền danh sách paths")
        for p in paths:
            # đảm bảo node tồn tại
            if p.start_id not in nodes or p.end_id not in nodes:
                # có thể skip hoặc raise; ở đây raise để bắt lỗi dữ liệu
                raise KeyError(f"Path {p.id} tham chiếu node không tồn tại: {p.start_id} -> {p.end_id}")
            adj[p.start_id].append((p.end_id, float(p.length)))
            if undirected:
                adj[p.end_id].append((p.start_id, float(p.length)))
        return adj

    elif mode == "range":
        # giữ lại tinh thần 'both' cũ: chỉ nối vô hướng nếu hai bên phủ được nhau
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                u, v = nodes[ids[i]], nodes[ids[j]]
                d = euclid(u, v)
                ok_uv = (u.r is not None and d <= u.r)
                ok_vu = (v.r is not None and d <= v.r)
                if ok_uv and ok_vu:
                    # vô hướng với w là trung bình 2 chiều (nếu weight_fn bất đối xứng)
                    w_uv = weight_fn(u, v)
                    w_vu = weight_fn(v, u)
                    w = 0.5 * (w_uv + w_vu)
                    adj[u.id].append((v.id, w))
                    adj[v.id].append((u.id, w))
        return adj

    else:
        raise ValueError("mode phải là 'range' hoặc 'paths'")

# ======================
# 3) DIJKSTRA giữ nguyên
# ======================

def dijkstra(
    adj: Dict[str, List[Tuple[str, float]]],
    start: str,
    goal: str,
    banned: Optional[Set[str]] = None,
    debug: bool = False
) -> Tuple[float, List[str]]:
    if banned is None:
        banned = set()
    if start in banned or goal in banned:
        if debug: print(f"[INIT] start/goal bị cấm → không có đường")
        return math.inf, []
    if start not in adj or goal not in adj:
        if debug: print(f"[INIT] start/goal không có trong đồ thị → không có đường")
        return math.inf, []

    dist = {u: math.inf for u in adj}
    prev: Dict[str, Optional[str]] = {u: None for u in adj}
    dist[start] = 0.0
    pq = [(0.0, start)]
    step = 0

    if debug:
        print("===== Dijkstra Debug Start =====")
        print(f"[INIT] start={start}, goal={goal}, banned={banned}")

    while pq:
        d, u = heapq.heappop(pq)
        step += 1
        if d != dist[u] or u in banned:
            if debug: print(f"[POP ] stale/ban -> skip: (d={d}, u={u})")
            continue
        if u == goal:
            if debug: print(f"[GOAL] reached {goal}")
            break
        for v, w in adj[u]:
            if v in banned:
                if debug: print(f"  relax {u}->{v} skip (banned)")
                continue
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
                if debug: print(f"  update {u}->{v}: dist[{v}]={nd}")

    if dist[goal] == math.inf:
        if debug: print("[END] không có đường")
        return math.inf, []

    path = []
    cur: Optional[str] = goal
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    if debug: print(f"[END] cost={dist[goal]}, path={path}")
    return dist[goal], path

# ======================
# 4) HÀM TRỢ GIÚP: PARSE JSON & CHẠY
# ======================

def parse_json_to_graph(payload: Dict[str, Any], undirected: bool = False) -> Tuple[Dict[str, Node], Dict[str, List[Tuple[str, float]]]]:
    """
    Nhận dict JSON dạng:
    {
      "nodes": [{"node_id":1,"x":10,"y":20}, ...],
      "paths": [{"id":1,"start_id":1,"end_id":2,"length":5.0}, ...]
    }
    -> Trả về (nodes_dict, adj) theo chế độ 'paths'.
    """
    # 1) build nodes
    nodes_list = payload.get("nodes", [])
    nodes: Dict[str, Node] = {}
    for n in nodes_list:
        nid = str(n["node_id"])
        nodes[nid] = Node(id=nid, x=float(n["x"]), y=float(n["y"]), r=None)  # r không cần

    # 2) build paths
    paths_list = payload.get("paths", [])
    p_objs: List[Path] = []
    for p in paths_list:
        p_objs.append(
            Path(
                id=str(p.get("id", "")),
                start_id=str(p["start_id"]),
                end_id=str(p["end_id"]),
                length=float(p["length"])
            )
        )

    # 3) build adj theo 'paths'
    adj = build_graph(nodes, mode="paths", paths=p_objs, undirected=undirected)
    return nodes, adj


if __name__ == "__main__":
    sample = {
      "nodes": [
        {"node_id": 1, "x": 10, "y": 20},
        {"node_id": 2, "x": 15, "y": 25},
        {"node_id": 3, "x": 30, "y": 40}
      ],
      "paths": [
        {"id": 1, "start_id": 1, "end_id": 2, "length": 5.0},
        {"id": 2, "start_id": 2, "end_id": 3, "length": 7.5},
        {"id": 3, "start_id": 1, "end_id": 3, "length": 10.2}
      ]
    }

    # Đồ thị có hướng đúng theo JSON (one-way)
    nodes, adj = parse_json_to_graph(sample, undirected=False)
    print("Adj (directed):", adj)

    # Tìm đường 1 -> 3
    cost, path = dijkstra(adj, start="1", goal="3", debug=True)
    print("Dijkstra 1→3:", path, "| cost:", cost)

    # Nếu bạn muốn coi 'paths' là hai chiều (mỗi cạnh ngược có cùng length):
    nodes2, adj2 = parse_json_to_graph(sample, undirected=True)
    print("Adj (undirected by mirroring):", adj2)
