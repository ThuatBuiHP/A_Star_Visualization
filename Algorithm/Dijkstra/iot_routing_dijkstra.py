from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Set, Callable
import heapq
import math
# '''
# Khi nói “đối xứng” ở đây tức là kết nối chỉ tồn tại nếu cả hai node đều nằm trong vùng phủ sóng của nhau.

# Ví dụ:

# Node A có bán kính phủ sóng rA = 5.

# Node B có bán kính phủ sóng rB = 2.

# Khoảng cách giữa A và B là 3.

# → Nếu kiểm tra theo từng phía:

# A → B: 3 ≤ rA (5) → A có thể gửi tới B.

# B → A: 3 ≤ rB (2) → B không gửi ngược lại được.

# Như vậy:

# Nếu bạn chọn quy tắc đối xứng (both) → coi như KHÔNG có cạnh giữa A và B, vì đường truyền hai chiều không đảm bảo.

# Nếu chọn quy tắc không đối xứng (either) → vẫn tạo cạnh, có thể xem như liên kết một chiều hoặc “ít chặt chẽ hơn”.

# both (đối xứng):

# Ứng dụng yêu cầu trao đổi dữ liệu song công (ví dụ truyền thông trong mạng mesh, định tuyến, xác nhận gói tin ACK).

# Đảm bảo an toàn, tránh tình trạng một node “thấy” node kia nhưng ngược lại thì không.

# either (không đối xứng):

# Chấp nhận kết nối một chiều (ví dụ cảm biến gửi dữ liệu về server, không cần trả lời).

# Dùng khi bạn muốn mạng “dày” hơn, dễ có đường nối.
# '''
# iot_routing_dijkstra.py
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Set, Callable
import heapq
import math


# 1) MÔ HÌNH NODE & HÀM CƠ BẢN

@dataclass(frozen=True)
class Node:
    id: str
    x: float
    y: float
    r: float  # bán kính phủ sóng

def euclid(a: "Node", b: "Node") -> float:
    """Khoảng cách Euclid giữa hai node."""
    return math.hypot(a.x - b.x, a.y - b.y)
# kiểm tra vùng phủ : True nếu dst nằm trong phạm vi phủ sóng của src
def in_range(src: "Node", dst: "Node") -> bool:
    """dst nằm trong vùng phủ của src? (dùng cho chế độ có hướng)"""
    return euclid(src, dst) <= src.r

# 2) XÂY ĐỒ THỊ
def build_graph(
    nodes: Dict[str, Node], # tất cả node, lưu trong dict {"A": Node(...), ...}
    mode: str = "both",     # kiểu kết nối: đối xứng hay không đối xứng
    weight_fn: Callable[[Node, Node], float] = euclid # hàm tính trọng số (mặc định là khoảng cách Euclid)
) -> Dict[str, List[Tuple[str, float]]]:
    """
    Trả về adjacency list: {node_id: [(neighbor_id, weight), ...]}
    - mode='both'   : vô hướng (hai chiều) nếu dist <= min(r_u, r_v) :hai chiều, chỉ nối A-B nếu cả hai cùng phủ tới nhau
    - mode='either' : có hướng; u->v nếu dist <= r_u (v trong vùng phủ của u):một chiều, A→B nếu B nằm trong phạm vi của A.
    ví dụ: 
    {
    "A": [("B", 2.0), ("C", 3.5)],
    "B": [("A", 2.0)],
    "C": [("A", 3.5)]
    }

    """
    ids = list(nodes.keys())   # Bước 1: Lấy danh sách ID node
    adj: Dict[str, List[Tuple[str, float]]] = {i: [] for i in ids} # Bước 2: Tạo adjacency list rỗng
#  Bước 3: Xét từng cặp node
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            u, v = nodes[ids[i]], nodes[ids[j]]  #Duyệt tất cả cặp (u,v)
            d = euclid(u, v)

            if mode == "both":
                # Điều kiện: khoảng cách ≤ min(r_u, r_v) → cả hai cùng phủ tới nhau.
                # Thêm cạnh hai chiều A–B, B–A với trọng số w -> đồ thị lúc này sẽ vô hướng
                if d <= min(u.r, v.r):
                    # dùng trọng số đối xứng (trung bình 2 chiều nếu weight_fn không đối xứng)
                    w_uv = weight_fn(u, v)  #chi phí u → v
                    w_vu = weight_fn(v, u) # chi phí v → u  
                    w = 0.5 * (w_uv + w_vu) # lấy trung bình 2 chiều
                    """
Ở chế độ đối xứng (both), ta giả sử liên kết giữa hai node là vô hướng (không phân biệt chiều).
Nhưng hàm weight_fn(u,v) và weight_fn(v,u) có thể cho kết quả khác nhau (ví dụ nếu trọng số phụ thuộc vào công suất phát của từng node).
Để “công bằng”, ta lấy trung bình của hai hướng và dùng nó làm trọng số chung cho cạnh vô hướng A—B.
                    """
                    adj[u.id].append((v.id, w))
                    adj[v.id].append((u.id, w))

# Có thể xảy ra trường hợp chỉ có A→B, chứ không có B→A. (đồ thị lúc này có hướng)
            elif mode == "either":
                if in_range(u, v):
                    adj[u.id].append((v.id, weight_fn(u, v)))  # u -> v
                if in_range(v, u):
                    adj[v.id].append((u.id, weight_fn(v, u)))  # v -> u
            else:
                raise ValueError("mode must be 'both' or 'either'")

    return adj

# 3) DIJKSTRA (đường đi chi phí nhỏ nhất)
'''
Nhận vào một đồ thị dạng danh sách kề adj, điểm bắt đầu start, điểm đích goal.
Tính đường đi có tổng chi phí nhỏ nhất (shortest path) từ start → goal.
Có thể cấm một số nút (node) bằng tham số banned (mô phỏng node hỏng).
Trả về: (chi_phí_nhỏ_nhất, danh_sách_các_node_trên_đường_đi). Nếu không có đường: (math.inf, []).
    Ý tưởng:
    Gán khoảng cách ban đầu từ start đến mọi node là ∞, riêng start=0.
    Dùng hàng đợi ưu tiên (priority queue với heapq) để luôn lấy node gần nhất chưa xử lý.
    Lặp lại:
    Lấy node có khoảng cách nhỏ nhất.
    Cập nhật khoảng cách tới các node hàng xóm.
    Khi gặp goal → dừng.
'''
def dijkstra(
    adj: Dict[str, List[Tuple[str, float]]],
    start: str,
    goal: str,
    banned: Optional[Set[str]] = None,
    # tham số debug=True để in log sau mỗi lần pop và sau mỗi lần relax
    debug: bool = True 
) -> Tuple[float, List[str]]:
    '''
dist[u]: chi phí tốt nhất đã biết hiện tại để đi từ start tới u. Khởi tạo ∞, riêng start = 0.0.
prev[u]: nút trước đó trên đường đi tối ưu tới u (dùng để dựng lại đường).
pq: hàng đợi ưu tiên (min-heap) chứa các cặp (khoảng_cách_tốt_nhất_tới_u, u). Luôn rút ra node có khoảng_cách nhỏ nhất hiện tại.
    '''

    if banned is None:
        banned = set()
    if start in banned or goal in banned:  # Nếu start hoặc goal bị cấm → không thể đi, trả về inf
        # -------------------------------
        if debug:
            print(f"[INIT] start/goal bị cấm → không có đường")
        # -------------------------------    
        return math.inf, []
    if start not in adj or goal not in adj: # Nếu start hoặc goal không có trong đồ thị → cũng trả về inf
        # -------------------------------
        if debug:
            print(f"[INIT] start/goal không có trong đồ thị → không có đường")
        # -------------------------------    
        return math.inf, []

    dist = {u: math.inf for u in adj}
    prev: Dict[str, Optional[str]] = {u: None for u in adj}
    dist[start] = 0.0
    pq = [(0.0, start)]
    # -------------------------------
    if debug:
        print("===== Dijkstra Debug Start =====")
        print(f"[INIT] start={start}, goal={goal}, banned={banned}")
        print(f"[INIT] dist: {dist}")
        print(f"[INIT] prev: {prev}")
        print(f"[INIT] pq:   {pq}\n")
    # -------------------------------
    step = 0
    while pq:
        # Lấy ra node u có chi phí tạm nhỏ nhất d
        d, u = heapq.heappop(pq)
        # Nếu d KHÔNG trùng với dist[u] hiện tại ⇒ bản ghi cũ (trước đó ta có tìm được đường tốt hơn tới u và đã push cái mới vào heap)
        # Nếu u bị cấm ⇒ bỏ qua.
        # -------------------------------
        step += 1
        if debug:
            print(f"[POP  ] step={step} -> (d={d}, u={u})")
            print(f"       current dist[{u}]={dist[u]} | banned? {u in banned}")
        # -------------------------------
        # Bỏ bản ghi cũ hoặc node bị cấm
        if d != dist[u] or u in banned:
        # -------------------------------    
            if debug:
                reason = []
                if d != dist[u]:
                    reason.append("stale_entry(d != dist[u])")
                if u in banned:
                    reason.append("u_in_banned")
                print(f"       -> skip ({', '.join(reason)})\n")
        # -------------------------------        
            continue
        #Dijkstra, lần đầu bạn pop được goal ra khỏi heap, dist[goal] đã là ngắn nhất tuyệt đối .Không cần duyệt tiếp.
        if u == goal:
        # -------------------------------            
            if debug:
                print(f"       -> reached goal '{goal}', break.\n")
        # -------------------------------        
            break
        for v, w in adj[u]:
            if v in banned:
             # -------------------------------       
                if debug:
                    print(f"       relax {u}->{v} (w={w}): v in banned -> skip")
            # -------------------------------            
                continue
            nd = d + w           # chi phí đi qua u để tới v
            # -------------------------------  
            if debug:
                print(f"       relax {u}->{v} (w={w}): nd={nd} vs dist[{v}]={dist[v]}")
            # -------------------------------  
            if nd < dist[v]:    # nếu tốt hơn cái đang biết
                dist[v] = nd    # cập nhật chi phí tốt nhất tới v
                prev[v] = u     # ghi nhớ đường đi (v đến từ u)
                heapq.heappush(pq, (nd, v))  # đẩy ứng viên mới vào heap
                # -------------------------------  
                if debug:
                    print(f"         -> update: dist[{v}]={nd}, prev[{v}]={u}")
                    print(f"         -> push to pq: ({nd}, {v})")
        if debug:
            print(f"       dist: {dist}")
            print(f"       prev: {prev}")
            print(f"       pq:   {pq}\n")
                # -------------------------------  

    if dist[goal] == math.inf:
        # -------------------------------  
        if debug:
            print("[END  ] Không có đường tới goal.")
        # -------------------------------     
        return math.inf, []

    # reconstruct đường đi
    path = []
    cur: Optional[str] = goal
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()
    # -------------------------------  
    if debug:
        print(f"[END  ] cost={dist[goal]}, path={path}")
    # -------------------------------      
    return dist[goal], path


# 4)  REROUTE & KIỂM TRA NGƯỢC CHIỀU

def reroute_on_failure(
    nodes: Dict[str, Node],
    start: str,
    goal: str,
    failed_id: str,
    mode: str = "both",
    weight_fn: Callable[[Node, Node], float] = euclid
) -> Tuple[float, List[str]]:
    """
    Loại node lỗi khỏi mạng rồi tìm đường thay thế tối ưu (Dijkstra).
    """
    adj = build_graph(nodes, mode=mode, weight_fn=weight_fn)
    banned = {failed_id}
    return dijkstra(adj, start, goal, banned=banned)
# Chặn nhiều nút hỏng
def reroute_with_banned(
    nodes: Dict[str, Node],
    start: str,
    goal: str,
    banned_nodes: Set[str],
    mode: str = "both",
    weight_fn: Callable[[Node, Node], float] = euclid
) -> Tuple[float, List[str]]:
    adj = build_graph(nodes, mode=mode, weight_fn=weight_fn)
    return dijkstra(adj, start, goal, banned=banned_nodes)

def has_reverse_path(
    adj_directed: Dict[str, List[Tuple[str, float]]],
    src: str,
    dst: str
) -> Tuple[bool, float, List[str]]:
    """
    Khi dùng 'either' (đồ thị có hướng): đã có đường src->dst,
    vậy chiều ngược dst->src có tồn tại không?
    """
    cost_rev, path_rev = dijkstra(adj_directed, start=dst, goal=src)
    return (cost_rev < math.inf), cost_rev, path_rev

# 5) DEMO NHANH

if __name__ == "__main__":
    # Tập node demo (tọa độ mét, bán kính mét)
    nodes = {
        "A": Node("A", 0, 0, 3.5),
        "B": Node("B", 2, 0, 2.0),
        "C": Node("C", 4, 0, 2.5),
        "D": Node("D", 4, 2, 2.0),
        "E": Node("E", 2, 2, 2.0),
        "F": Node("F", 0, 2, 2.0),
    }

    print("=== BOTH (vô hướng, đối xứng) ===")
    adj_both = build_graph(nodes, mode="both")
    cost1, path1 = dijkstra(adj_both, start="A", goal="D")
    print("Dijkstra A→D:", path1, " | cost:", round(cost1, 3))

    # Node C bị lỗi → tìm tuyến thay thế
    cost2, path2 = reroute_on_failure(nodes, start="A", goal="D",
                                      failed_id="C", mode="both")
    print("Dijkstra A→D khi C lỗi:", path2, " | cost:", round(cost2, 3))

    print("\n=== EITHER (có hướng, một chiều) ===")
    nodes_one_way = {
        "A": Node("A", 0, 0, 5.0),  # phủ xa
        "B": Node("B", 3, 0, 2.0),  # phủ gần
    }
    adj_either = build_graph(nodes_one_way, mode="either")
    print("Adj (either):", adj_either)

    # Đường A -> B (kỳ vọng có)
    cost_f, path_f = dijkstra(adj_either, start="A", goal="B")
    print("Dijkstra A→B:", path_f, " | cost:", round(cost_f, 3))

    # Đường B -> A (kỳ vọng không có)
    cost_b, path_b = dijkstra(adj_either, start="B", goal="A")
    if cost_b == math.inf:
        print("Dijkstra B→A: không tồn tại đường (đúng kỳ vọng one-way)")
    else:
        print("Dijkstra B→A:", path_b, " | cost:", round(cost_b, 3))
