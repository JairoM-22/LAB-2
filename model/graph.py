from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Tuple

from utils.geo import haversine




@dataclass
class Airport:
    # Nodo del grafo: cada aeropuerto se identifica por su código IATA
    code   : str
    name   : str
    city   : str
    country: str
    lat    : float
    lon    : float

    def __hash__(self):
        return hash(self.code)

    def __eq__(self, other):
        return isinstance(other, Airport) and self.code == other.code

    def __repr__(self):
        return f"Airport({self.code})"

    def info_dict(self) -> dict:
        # Útil para mostrar detalles en la UI sin exponer el objeto directamente
        return {
            'Código'  : self.code,
            'Nombre'  : self.name,
            'Ciudad'  : self.city,
            'País'    : self.country,
            'Latitud' : f"{self.lat:.6f}",
            'Longitud': f"{self.lon:.6f}",
        }


@dataclass
class Edge:
    # Arista no dirigida; el peso es la distancia Haversine en km
    src    : str    # código aeropuerto origen
    dst    : str    # código aeropuerto destino
    weight : float  # distancia Haversine en km
    flights: int    # frecuencia de vuelos en el dataset

    def __repr__(self):
        return f"Edge({self.src}<->{self.dst}, {self.weight:.0f} km)"


# ── Union-Find (para Kruskal) ────────────────────────────────────────────

class UnionFind:
    # Compresión de camino + unión por rango: operaciones casi-O(1) amortizado

    def __init__(self, elements):
        self._parent = {e: e for e in elements}
        self._rank   = {e: 0  for e in elements}

    def find(self, x: str) -> str:
        # Aplana el árbol mientras sube; evita cadenas largas en llamadas futuras
        if self._parent[x] != x:
            self._parent[x] = self.find(self._parent[x])
        return self._parent[x]

    def union(self, x: str, y: str) -> bool:
        # Retorna False si ya estaban en el mismo conjunto (ciclo detectado)
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return False
        if self._rank[rx] < self._rank[ry]:
            rx, ry = ry, rx
        self._parent[ry] = rx
        if self._rank[rx] == self._rank[ry]:
            self._rank[rx] += 1
        return True


# ── Min-Heap manual (para Dijkstra) ─────────────────────────────────────

class MinHeap:
    # Heap binario desde cero; almacena (prioridad, valor) con extracción O(log n)

    def __init__(self):
        self._data: List[tuple] = []

    def push(self, priority: float, value) -> None:
        # Inserta al final y burbujea hacia arriba
        self._data.append((priority, value))
        self._sift_up(len(self._data) - 1)

    def pop(self) -> tuple:
        # Intercambia raíz con el último, extrae, y reordena hacia abajo
        if not self._data:
            raise IndexError("pop en heap vacío")
        self._swap(0, len(self._data) - 1)
        item = self._data.pop()
        if self._data:
            self._sift_down(0)
        return item

    def __len__(self) -> int:
        return len(self._data)

    def _swap(self, i, j):
        self._data[i], self._data[j] = self._data[j], self._data[i]

    def _sift_up(self, i):
        while i > 0:
            p = (i - 1) // 2
            if self._data[i][0] < self._data[p][0]:
                self._swap(i, p); i = p
            else:
                break

    def _sift_down(self, i):
        n = len(self._data)
        while True:
            s = i
            l, r = 2*i+1, 2*i+2
            if l < n and self._data[l][0] < self._data[s][0]: s = l
            if r < n and self._data[r][0] < self._data[s][0]: s = r
            if s == i: break
            self._swap(i, s); i = s


# ── Grafo principal ──────────────────────────────────────────────────────

class FlightGraph:
    # Grafo no dirigido ponderado; lista de adyacencia como estructura base

    def __init__(self):
        self.airports  : Dict[str, Airport]                = {}
        self.adjacency : Dict[str, List[Tuple[str,float]]] = {}
        self._edges    : List[Edge]                        = []
        # _edge_set evita duplicados en O(1) sin recorrer la lista de adyacencia
        self._edge_set : Set[Tuple[str, str]]              = set()
        self._cache_components: Optional[List[Set[str]]]   = None
        self._cache_mst       : Optional[dict]             = None

    # ── Construcción ─────────────────────────────────────────────────────

    def add_airport(self, code, name, city, country, lat, lon) -> None:
        # Ignora silenciosamente si el código ya existe
        if code not in self.airports:
            self.airports[code]  = Airport(code, name, city, country, lat, lon)
            self.adjacency[code] = []

    def add_edge(self, src: str, dst: str, flights: int = 0) -> None:
        # Clave canónica ordenada para tratar (A,B) y (B,A) como la misma arista
        if src not in self.airports or dst not in self.airports:
            return
        key = (src, dst) if src < dst else (dst, src)
        if key in self._edge_set:
            return
        self._edge_set.add(key)
        a1, a2 = self.airports[src], self.airports[dst]
        weight  = haversine(a1.lat, a1.lon, a2.lat, a2.lon)
        self.adjacency[src].append((dst, weight))
        self.adjacency[dst].append((src, weight))
        self._edges.append(Edge(src, dst, weight, flights))
        # Invalida cachés porque el grafo cambió
        self._cache_components = None
        self._cache_mst        = None

    @classmethod
    def build_from_records(
        cls,
        airports_list,
        routes_list,
        progress_cb: Optional[Callable[[str, float], None]] = None,
    ) -> 'FlightGraph':
        # Factory: construye el grafo desde las listas del loader
        def _cb(msg, pct):
            if progress_cb:
                progress_cb(msg, pct)

        g = cls()

        _cb(f"Agregando {len(airports_list):,} aeropuertos…", 0.0)
        for ap in airports_list:
            g.add_airport(**ap)

        total = len(routes_list)
        _cb(f"Agregando {total:,} rutas…", 0.2)

        # Reportar progreso cada 5 000 aristas para no saturar la UI
        report_every = max(1, total // 20)
        for i, (src, dst, freq) in enumerate(routes_list):
            g.add_edge(src, dst, freq)
            if i % report_every == 0:
                pct = 0.2 + 0.7 * (i / total)
                _cb(f"Rutas: {i:,} / {total:,}", pct)

        _cb("Grafo construido.", 1.0)
        print(f"[Graph] Nodos: {g.node_count:,}  |  Aristas: {g.edge_count:,}")
        return g

    # ── Propiedades básicas ───────────────────────────────────────────────

    @property
    def edges(self) -> List[Edge]:
        return self._edges

    @property
    def node_count(self) -> int:
        return len(self.airports)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def degree(self, code: str) -> int:
        return len(self.adjacency.get(code, []))

    # ── 1. Conectividad y componentes conexas ─────────────────────────────

    def _bfs(self, start: str, visited: Set[str]) -> Set[str]:
        # BFS iterativo con lista como cola; visited compartido entre llamadas
        queue     = [start]
        component : Set[str] = set()
        head = 0
        while head < len(queue):
            node = queue[head]; head += 1
            if node in visited:
                continue
            visited.add(node)
            component.add(node)
            for nbr, _ in self.adjacency[node]:
                if nbr not in visited:
                    queue.append(nbr)
        return component

    def connected_components(self) -> List[Set[str]]:
        # Resultado cacheado; se invalida cada vez que se agrega una arista
        if self._cache_components is not None:
            return self._cache_components
        visited   : Set[str]       = set()
        components: List[Set[str]] = []
        for code in self.airports:
            if code not in visited:
                components.append(self._bfs(code, visited))
        components.sort(key=len, reverse=True)
        self._cache_components = components
        return components

    def is_connected(self) -> bool:
        return len(self.connected_components()) == 1

    # ── 2. Bipartición (2-coloración BFS) ────────────────────────────────

    def is_bipartite(self, component: Optional[Set[str]] = None
                     ) -> Tuple[bool, Optional[Dict[str, int]]]:
        # Si hay un ciclo impar, la coloración falla y retorna (False, None)
        nodes = component if component is not None else set(self.airports)
        color : Dict[str, int] = {}

        for start in nodes:
            if start in color:
                continue
            queue = [start]; color[start] = 0; head = 0
            while head < len(queue):
                node = queue[head]; head += 1
                for nbr, _ in self.adjacency[node]:
                    if nbr not in nodes:
                        continue
                    if nbr not in color:
                        color[nbr] = 1 - color[node]
                        queue.append(nbr)
                    elif color[nbr] == color[node]:
                        return False, None   # ciclo impar encontrado
        return True, color

    # ── 3. MST con Kruskal + Union-Find ──────────────────────────────────

    def minimum_spanning_tree(self, component: Optional[Set[str]] = None
                              ) -> Tuple[List[Edge], float]:
        # Kruskal: ordena por peso y agrega aristas que no formen ciclos
        nodes = component if component is not None else set(self.airports)
        relevant = sorted(
            [e for e in self._edges if e.src in nodes and e.dst in nodes],
            key=lambda e: e.weight
        )
        uf = UnionFind(nodes)
        mst: List[Edge] = []
        total = 0.0
        for edge in relevant:
            if uf.union(edge.src, edge.dst):
                mst.append(edge)
                total += edge.weight
                # Un árbol de N nodos tiene exactamente N-1 aristas
                if len(mst) == len(nodes) - 1:
                    break
        return mst, total

    def mst_all_components(self) -> Dict[int, Tuple[List[Edge], float]]:
        # Calcula el MST de cada componente y cachea el resultado
        if self._cache_mst is not None:
            return self._cache_mst
        result = {}
        for i, comp in enumerate(self.connected_components()):
            result[i] = ([], 0.0) if len(comp) < 2 else self.minimum_spanning_tree(comp)
        self._cache_mst = result
        return result

    # ── 4 & 5. Dijkstra + reconstrucción ─────────────────────────────────

    def dijkstra(self, source: str
                 ) -> Tuple[Dict[str, float], Dict[str, Optional[str]]]:
        # Entradas obsoletas del heap se descartan con el chequeo d_u > dist[u]
        INF  = math.inf
        dist = {c: INF for c in self.airports}
        prev : Dict[str, Optional[str]] = {c: None for c in self.airports}
        dist[source] = 0.0
        heap = MinHeap()
        heap.push(0.0, source)

        while len(heap):
            d_u, u = heap.pop()
            if d_u > dist[u]:
                continue           # entrada obsoleta, ignorar
            for v, w in self.adjacency[u]:
                alt = dist[u] + w
                if alt < dist[v]:
                    dist[v] = alt
                    prev[v] = u
                    heap.push(alt, v)
        return dist, prev

    def reconstruct_path(self, prev: Dict[str, Optional[str]],
                         target: str) -> List[str]:
        # Sigue los predecesores hacia atrás y revierte para obtener el orden correcto
        path = []
        node: Optional[str] = target
        while node is not None:
            path.append(node)
            node = prev.get(node)
        path.reverse()
        if not path or (len(path) == 1 and prev.get(path[0]) is not None):
            return []
        return path

    def top_longest_shortest_paths(self, source: str, k: int = 10
                                   ) -> List[Tuple[str, float, List[str]]]:
        # Corre Dijkstra una vez y selecciona los k destinos más lejanos alcanzables
        dist, prev = self.dijkstra(source)
        INF = math.inf
        reachable = [(c, d) for c, d in dist.items() if d < INF and c != source]
        reachable.sort(key=lambda x: x[1], reverse=True)
        result = []
        for code, d in reachable[:k]:
            result.append((code, d, self.reconstruct_path(prev, code)))
        return result

    def shortest_path_between(self, src: str, dst: str
                              ) -> Tuple[float, List[str]]:
        # Retorna (inf, []) si src y dst están en componentes distintas
        dist, prev = self.dijkstra(src)
        d = dist.get(dst, math.inf)
        if d == math.inf:
            return math.inf, []
        return d, self.reconstruct_path(prev, dst)

    # ── Búsqueda ──────────────────────────────────────────────────────────

    def search_airports(self, query: str, max_results: int = 10) -> List[Airport]:
        # Busca por código, nombre, ciudad o país; insensible a mayúsculas
        q = query.lower().strip()
        results = []
        for ap in self.airports.values():
            if (q in ap.code.lower() or q in ap.name.lower()
                    or q in ap.city.lower() or q in ap.country.lower()):
                results.append(ap)
                if len(results) >= max_results:
                    break
        return results

    def nearest_airport(self, lat: float, lon: float) -> Optional[str]:
        # Recorre todos los aeropuertos; útil para selección por clic en el mapa
        best_code, best_dist = None, math.inf
        for code, ap in self.airports.items():
            d = haversine(lat, lon, ap.lat, ap.lon)
            if d < best_dist:
                best_dist = d; best_code = code
        return best_code

    # ── Estadísticas para el panel de info ───────────────────────────────

    def summary(self) -> dict:
        # Agrega las métricas principales del grafo en un solo dict
        comps  = self.connected_components()
        bip, _ = self.is_bipartite(comps[0] if comps else None)
        mst_all = self.mst_all_components()
        degrees = [self.degree(c) for c in self.airports]
        return {
            'nodos'          : self.node_count,
            'aristas'        : self.edge_count,
            'conexo'         : self.is_connected(),
            'num_componentes': len(comps),
            'bipartito_mayor': bip,
            'mst_peso_total' : sum(w for _, w in mst_all.values()),
            'grado_promedio' : sum(degrees)/len(degrees) if degrees else 0,
            'grado_maximo'   : max(degrees) if degrees else 0,
        }
