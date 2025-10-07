
import math
import unittest
from iot_routing_dijkstra import (
        Node, euclid, build_graph, dijkstra, reroute_on_failure, has_reverse_path
    )
# python -m unittest -v test_iot_routing.TestIotRouting.test_T1_basic_both

def assert_close(testcase, a, b, tol=1e-9):
    testcase.assertTrue(math.isclose(a, b, rel_tol=tol, abs_tol=tol), f"Expected {b}, got {a}")

def assert_in(testcase, item, choices):
    testcase.assertIn(item, choices, f"Expected one of {choices}, got {item}")

class TestIotRouting(unittest.TestCase):

    def setUp(self):
        # Base layout như demo (đơn vị mét)
        self.base_nodes = {
            "A": Node("A", 0, 0, 3.5),
            "B": Node("B", 2, 0, 2.0),
            "C": Node("C", 4, 0, 2.5),
            "D": Node("D", 4, 2, 2.0),
            "E": Node("E", 2, 2, 2.0),
            "F": Node("F", 0, 2, 2.0),
        }
        # self.base_nodes = {
        #     "A": Node("A",  0.0,  0.0, 3.0),
        #     "B": Node("B", 3.0,  0.0, 3.0),
        #     "C": Node("C",-3.0,  0.0, 3.0),
        #     "D": Node("D", 0.0,  3.0, 3.0),
        #     "E": Node("E", 0.0, -3.0, 3.0),
        #     "F": Node("F", 2.0,  2.0, 3.0),
        # }
        # self.base_nodes = {
        #     "A": Node("A", 0.0,   0.0, 5.0),   # phủ xa
        #     "B": Node("B", 3.0,   0.0, 2.0),   # phủ vừa
        #     "C": Node("C", 4.8,   0.0, 1.0),   # phủ ngắn
        #     "D": Node("D", 6.0,   1.5, 1.2),   # thêm 1 nút xa
        # }
        # self.base_nodes = {
        #     "L1": Node("L1", 0.0, 0.0, 3.5),
        #     "L2": Node("L2", 0.0, 2.0, 3.5),
        #     "M":  Node("M",  3.0, 1.0, 3.5),   # bridge
        #     "R1": Node("R1", 6.0, 0.0, 3.5),
        #     "R2": Node("R2", 6.0, 2.0, 3.5),
        # }
#         self.base_nodes  = {
#         "H1": Node("H1", 0.0,   0.0,   2.1),
#         "H2": Node("H2", 2.0,   0.0,   2.1),
#         "H3": Node("H3", 3.0,   1.732, 2.1),
#         "H4": Node("H4", 2.0,   3.464, 2.1),
#         "H5": Node("H5", 0.0,   3.464, 2.1),
#         "H6": Node("H6",-1.0,   1.732, 2.1),
# }


# Đồ thị vô hướng, trọng số là khoảng cách Euclid.
    def test_T1_basic_both(self):
        adj_both = build_graph(self.base_nodes, mode="both")
        cost, path = dijkstra(adj_both, "A", "D")
        print("T1:", cost, path)
        assert_close(self, cost, 6.0)
        assert_in(self, path, [["A","B","C","D"], ["A","F","E","D"]])
# Loại node C khỏi mạng → không còn đi A-B-C-D.
    def test_T2_reroute_failed_C(self):
        cost2, path2 = reroute_on_failure(self.base_nodes, "A", "D", failed_id="C", mode="both")
        print("T2:", cost2, path2)
        assert_close(self, cost2, 6.0)
        assert_in(self, path2, [
            ["A","F","E","D"],
            ["A","B","E","D"],   # cũng hợp lệ khi C bị cấm
        ])
# Đồ thị có hướng: cạnh tồn tại theo phạm vi phát của nguồn.
    def test_T3_either_one_way(self):
        nodes_one_way = {
            "A": Node("A", 0, 0, 5.0),
            "B": Node("B", 3, 0, 2.0),
        }
        adj_either = build_graph(nodes_one_way, mode="either")
        cost3, path3 = dijkstra(adj_either, "A", "B")
        cost3b, path3b = dijkstra(adj_either, "B", "A")
        print("T3:", cost3, path3, "| back:", cost3b, path3b)
        assert_close(self, cost3, 3.0)
        self.assertEqual(path3, ["A","B"])
        self.assertTrue(math.isinf(cost3b) and path3b == [])
# Khoảng cách quá xa so với bán kính → đồ thị rời rạc.
    def test_T4_disconnected(self):
        nodes_disconnected = {
            "P": Node("P", 0, 0, 1.0),
            "Q": Node("Q", 100, 0, 1.0)
        }
        adj_disc = build_graph(nodes_disconnected, mode="both")
        cost4, path4 = dijkstra(adj_disc, "P", "Q")
        print("T4:", cost4, path4)
        self.assertTrue(math.isinf(cost4) and path4 == [])
# Khi mỗi cạnh = 1.0, mục tiêu trở thành “ít hop nhất”.
    def test_T5_hop_weight(self):
        adj_both = build_graph(self.base_nodes, mode="both")
        cost5, path5 = dijkstra(adj_both, "A", "D")
        adj_hop = build_graph(self.base_nodes, mode="both", weight_fn=lambda u, v: 1.0)
        cost5h, path5h = dijkstra(adj_hop, "A", "D")
        print("T5 (euclid vs hops):", (cost5, path5), " | ", (cost5h, path5h))
        assert_close(self, cost5h, 3.0)
        assert_in(self, path5h, [["A","B","C","D"], ["A","F","E","D"]])
# Kiểm tra chiều ngược trong đồ thị có hướng:
    def test_T6_has_reverse_path(self):
        tri = {
            "A": Node("A", 0, 0, 1.5),
            "B": Node("B", 1, 0, 2.0),
            "C": Node("C", 0, 1, 1.5),
        }
        adj_tri = build_graph(tri, mode="either")
        ok_back, cost_back, path_back = has_reverse_path(adj_tri, src="A", dst="B")
        print("T6:", ok_back, cost_back, path_back)
        self.assertTrue(ok_back)
        # chấp nhận mọi đường hợp lệ B→A
        assert_in(self, path_back, [
            ["B","A"],
            ["B","C","A"],
        ])


    def test_T7_tie_paths(self):
        adj_both = build_graph(self.base_nodes, mode="both")
        cost7, path7 = dijkstra(adj_both, "A", "D")
        print("T7:", cost7, path7)
        assert_close(self, cost7, 6.0)
        assert_in(self, path7, [["A","B","C","D"], ["A","F","E","D"]])
# Trường hợp xuất phát cũng là đích.
    def test_T8_start_equals_goal(self):
        adj_both = build_graph(self.base_nodes, mode="both")
        cost8, path8 = dijkstra(adj_both, "A", "A")
        print("T8:", cost8, path8)
        assert_close(self, cost8, 0.0)
        self.assertEqual(path8, ["A"])
# Nếu start bị cấm → không thể đi đâu cả.
    def test_T9_banned_is_start(self):
        adj_both = build_graph(self.base_nodes, mode="both")
        cost9, path9 = dijkstra(adj_both, "A", "D", banned={"A"})
        print("T9:", cost9, path9)
        self.assertTrue(math.isinf(cost9) and path9 == [])
# Khi cấm B và C, nhánh phải đi là A→F→E→D.
    def test_T10_ban_multiple_nodes(self):
        adj_both = build_graph(self.base_nodes, mode="both")
        # Cấm B và C -> chỉ còn đường A-F-E-D
        banned = {"B","C"}
        cost10, path10 = dijkstra(adj_both, "A", "D", banned=banned)
        print("T10:", cost10, path10)
        assert_close(self, cost10, 6.0)
        self.assertEqual(path10, ["A","F","E","D"])
# Mô phỏng cạnh hỏng thay vì node hỏng.
    def test_T11_broken_edges(self):
        adj_both = build_graph(self.base_nodes, mode="both")
        # Chặn (B,C) & (C,B) và (F,E) & (E,F) trên bản sao adj
        broken = {("B","C"), ("C","B"), ("F","E"), ("E","F")}
        pruned = {u: [(v, w) for (v, w) in nbrs if (u, v) not in broken]
                  for u, nbrs in adj_both.items()}
        cost11, path11 = dijkstra(pruned, "A", "D")
        print("T11:", cost11, path11)
        # Đảm bảo tránh cạnh hỏng
        edges = list(zip(path11, path11[1:]))
        self.assertNotIn(("B","C"), edges)
        self.assertNotIn(("C","B"), edges)
        self.assertNotIn(("F","E"), edges)
        self.assertNotIn(("E","F"), edges)
# Tất cả node có r = 0 → không thể kết nối.
    def test_T12_zero_radius(self):
        nodes_zero_r = {
            "X": Node("X", 0, 0, 0.0),
            "Y": Node("Y", 1, 1, 0.0),
            "Z": Node("Z", 2, 2, 0.0),
        }
        adj_zero = build_graph(nodes_zero_r, mode="both")
        cost12, path12 = dijkstra(adj_zero, "X", "Z")
        print("T12:", cost12, path12)
        self.assertTrue(math.isinf(cost12) and path12 == [])

if __name__ == "__main__":
    unittest.main(verbosity=2)
