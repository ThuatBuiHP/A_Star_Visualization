from collections import defaultdict, deque
from typing import Dict, List, Tuple, Set

# ---- Kiểu dữ liệu ----
# Đồ thị có hướng, trọng số không âm
# edges[u] = list[(v, w_uv)]
Graph = Dict[int, List[Tuple[int, float]]]

def find_pivots(
    edges: Graph,
    d_hat: Dict[int, float],   # ước lượng hiện tại \hat d[v]
    S: Set[int],               # tập S (các "complete" vertices hiện tại)
    k: int,                    # số bước relax
    B: float                   # bound B
) -> Tuple[Set[int], Set[int]]:
    """
    Trả về (P, W) theo Algorithm 1 (Finding Pivots).

    Giả định: Mọi đỉnh chưa hoàn tất v với d(v) < B đều có đường đi ngắn nhất đi qua
    một đỉnh đã hoàn tất trong S (giả định/điều kiện của thuật toán gốc).
    """
    # --- Dòng 1-11: Relax k bước (không đổi \hat d), xây W ---
    W = set(S)
    Wi_1 = set(S)

    for _ in range(1, k + 1):  # i = 1..k
        Wi = set()
        for u in Wi_1:
            for v, w_uv in edges.get(u, []):
                # Chỉ xét các cung "không làm xấu đi" ước lượng hiện tại
                if d_hat[u] + w_uv <= d_hat[v]:
                    # Chỉ quan tâm các đỉnh chưa vượt bound
                    if d_hat[u] + w_uv < B:
                        Wi.add(v)
        W |= Wi
        Wi_1 = Wi
        if not Wi_1:
            break  # không lan thêm được nữa

    # Nhánh nhanh: nếu |W| > k|S|, chọn luôn tất cả S làm pivots (dòng 12-13)
    if len(W) > k * max(1, len(S)):  # tránh chia 0
        return set(S), W

    # --- Dòng 15-16: Lập rừng có hướng F trên W bởi các cung "chặt" ---
    # F = {(u,v) in E : u,v in W and \hat d[v] = \hat d[u] + w_uv}
    children = defaultdict(list)  # cây có hướng từ u -> v
    indeg = defaultdict(int)

    for u in W:
        for v, w_uv in edges.get(u, []):
            if v in W and abs(d_hat[u] + w_uv - d_hat[v]) < 1e-12:  # so sánh số thực
                children[u].append(v)
                indeg[v] += 1

    # Các "gốc" trong rừng là đỉnh có indeg == 0
    roots = {u for u in W if indeg[u] == 0}

    # Với mỗi root trong S, tính kích thước cây con; chọn các root có >= k đỉnh
    def subtree_size(root: int) -> int:
        # duyệt DAG/rừng: không có chu trình theo giả định (Assumption 2.1)
        count = 0
        stack = [root]
        visited = set()
        while stack:
            x = stack.pop()
            if x in visited:
                continue
            visited.add(x)
            count += 1
            stack.extend(children.get(x, []))
        return count

    P = set()
    for u in S:
        if u in roots:
            if subtree_size(u) >= k:
                P.add(u)

    return P, W


# ---------------------- TESTCASE TỐI THIỂU ----------------------

def demo():
    # Đồ thị ví dụ:
    # 0 ->1(1), 0->2(2)
    # 1 ->3(1), 2->3(1), 1->4(3), 2->4(2)
    # 3 ->5(1), 4->5(1)
    edges: Graph = {
        0: [(1, 1), (2, 2)],
        1: [(3, 1), (4, 3)],
        2: [(3, 1), (4, 2)],
        3: [(5, 1)],
        4: [(5, 1)],
        5: []
    }

    # Một bộ \hat d "hợp lý" (ví dụ xuất phát từ s=0)
    d_hat = {
        0: 0,
        1: 1,
        2: 2,
        3: 2,   # min(1->3, 2->3) = 2
        4: 4,   # min(1->4, 2->4) = 4
        5: 3    # qua 3: 0->1->3->5 = 3 (cung "chặt"), qua 4 là 5 (không chặt)
    }

    # Tập S: giả sử các đỉnh có d(u) < b đã "complete". Lấy ví dụ S={0,1,2}
    S = {0, 1, 2}
    k = 2
    B = 10.0

    P, W = find_pivots(edges, d_hat, S, k, B)

    print("W (các đỉnh thu được sau k bước relax, có \u005Chat d < B):", sorted(W))
    print("P (các pivot được chọn):", sorted(P))

if __name__ == "__main__":
    demo()
