# src/controller/routing.py
# Paper-faithful DFS-based routing (Section IV-B)

class RoutingEngine:
    def __init__(self):
        # Adjacency list: { node : [(neighbor, weight), ...] }
        self.graph = {}

    # ------------------------------------------------------------------
    # Topology update (called by controller)
    # ------------------------------------------------------------------
    def update_topology(self, links):
        """
        links: list of (src_dpid, dst_dpid, weight)
        """
        self.graph.clear()
        for link in links:
             # link is expected to be (src_dpid, dst_dpid, weight, port_no)
             src, dst, weight, port_no = link
             if src not in self.graph:
                 self.graph[src] = []
             self.graph[src].append((dst, weight, port_no))

    # ------------------------------------------------------------------
    # Eq. (1): Path weight pw(L) = sum of link weights
    # ------------------------------------------------------------------
    def path_weight(self, path):
        cost = 0
        for i in range(len(path) - 1):
            u = path[i]
            v = path[i + 1]
            for neigh, w, _ in self.graph.get(u, []):
                if neigh == v:
                    cost += w
                    break
        return cost

    # ------------------------------------------------------------------
    # DFS path enumeration (paper-required)
    # ------------------------------------------------------------------
    def _dfs(self, current, destination, visited, stack, all_paths):
        visited.add(current)
        stack.append(current)

        if current == destination:
            all_paths.append(list(stack))
        else:
            for neighbor, _, _ in self.graph.get(current, []):
                if neighbor not in visited:
                    self._dfs(neighbor, destination, visited, stack, all_paths)

        stack.pop()
        visited.remove(current)

    # ------------------------------------------------------------------
    # Main path selection function (paper-faithful)
    # ------------------------------------------------------------------
    def find_shortest_path(self, src, dst, bandwidth_requirements=0):
        """
        Implements paper DFS + Eq.(1)
        Returns the path with minimum pw(L)
        """
        if src not in self.graph or dst not in self.graph:
            return None

        all_paths = []
        self._dfs(src, dst, set(), [], all_paths)

        if not all_paths:
            return None

        # Sort paths by Eq.(1)
        all_paths.sort(key=self.path_weight)

        # Paper: shortest path is selected
        return all_paths[0]

    # ------------------------------------------------------------------
    # Eq. (1) – Bucket weight (used for MRT extension)
    # ------------------------------------------------------------------
    def calculate_bucket_weight(self, paths):
        """
        bw(L) = (1 - pw(L) / sum(pw(i))) * 10
        """
        weights = [self.path_weight(p) for p in paths]
        total = sum(weights)

        bucket_weights = {}
        for p, w in zip(paths, weights):
            if total == 0:
                bucket_weights[tuple(p)] = 0
            else:
                bucket_weights[tuple(p)] = (1 - (w / total)) * 10

        return bucket_weights
    
    def get_port(self, src, dst):
        if src in self.graph:
            for neighbor, _, port in self.graph[src]:
                if neighbor == dst:
                    return port
        return None

    # ------------------------------------------------------------------
    # Multicast Routing Tree (Items 8, 9)
    # ------------------------------------------------------------------
    def find_multicast_tree(self, src, destinations):
        """
        Constructs a multicast tree (Union of Shortest Paths for simplicity, 
        or Steiner Tree approximation).
        Returns: { dpid: [next_hop_dpid_1, next_hop_dpid_2, ...] }
        """
        tree = {}
        for dst in destinations:
            path = self.find_shortest_path(src, dst)
            if not path: continue
            
            for i in range(len(path) - 1):
                u = path[i]
                v = path[i+1]
                if u not in tree:
                    tree[u] = []
                if v not in tree[u]:
                    tree[u].append(v)
        return tree
