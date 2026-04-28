# Interfaz gráfica principal: sidebar tkinter + mapa Folium en el browser

import math
import os
import tempfile
import threading
import tkinter as tk
import webbrowser
import http.server
import socketserver
import socket
from tkinter import font as tkfont
from typing import Dict, List, Optional, Set, Tuple

from model.graph import Airport, Edge, FlightGraph
from view.map_builder import build_map, TOP_ROUTE_COLORS


# Paleta de colores compartida en toda la UI

C = {
    'bg'          : '#F5F5F7',
    'sidebar'     : '#FFFFFF',
    'card'        : '#F2F2F7',
    'text_primary': '#1D1D1F',
    'text_sec'    : '#6E6E73',
    'text_hint'   : '#AEAEB2',
    'accent'      : '#007AFF',
    'accent_light': '#E3F0FF',
    'green'       : '#34C759',
    'red'         : '#FF3B30',
    'orange'      : '#FF9500',
    'separator'   : '#E5E5EA',
}

SIDEBAR_W = 340


# Helper de botón con hover effect incorporado

def _make_button(parent, text, command, accent=False, small=False, **kw):
    bg     = C['accent'] if accent else C['card']
    fg     = '#FFFFFF'   if accent else C['text_primary']
    active = '#005EC4'   if accent else C['separator']
    size   = 11 if small else 13
    btn = tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, activebackground=active, activeforeground=fg,
        font=('SF Pro Display', size),
        relief='flat', bd=0, padx=14, pady=7, cursor='hand2', **kw
    )
    btn.bind('<Enter>', lambda e: btn.config(
        bg='#005EC4' if accent else C['accent_light']))
    btn.bind('<Leave>', lambda e: btn.config(bg=bg))
    return btn


# Servidor HTTP local: sirve el HTML de Folium para que el browser pueda recargarlo

class MapServer:
    _port = None

    @classmethod
    def start(cls) -> int:
        if cls._port is not None:
            return cls._port

        map_dir = os.path.join(tempfile.gettempdir(), 'flight_graph_app_maps')
        os.makedirs(map_dir, exist_ok=True)

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=map_dir, **kwargs)
            def log_message(self, format, *args):
                pass # Silenciar logs del servidor

        # Buscar puerto disponible
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', 0))
        cls._port = s.getsockname()[1]
        s.close()

        httpd = socketserver.TCPServer(("127.0.0.1", cls._port), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return cls._port


# Ventana principal de la aplicación

class FlightApp(tk.Tk):

    def __init__(self, graph: FlightGraph):
        super().__init__()
        self.graph = graph

        self.selected_src  : Optional[str]  = None
        self.selected_dst  : Optional[str]  = None
        self._current_path : List[str]      = []
        self._mst_edges    : List[Edge]     = []
        self._show_mst     : bool           = False
        self._top_paths    : List           = []   # lista de (code, dist, path) para top 10
        self._map_path     : Optional[str]  = None
        self._viewing_component_idx: Optional[int] = None
        self._components_cache: Optional[List[Set[str]]] = None
        self.server_port   : int            = MapServer.start()

        self.title('Flight Graph Analyzer')
        self.configure(bg=C['bg'])
        self.geometry('420x900')
        self.resizable(False, True)

        self._build_ui()
        self.after(300, self._show_welcome)

    # ─────────────────────────────────────────
    #  Construcción de UI
    # ─────────────────────────────────────────

    def _build_ui(self):
        self._frame_root = tk.Frame(self, bg=C['bg'])
        self._frame_root.pack(fill='both', expand=True)

        # Sidebar ocupa toda la ventana (el mapa está en el browser)
        self._sidebar = tk.Frame(self._frame_root, bg=C['sidebar'],
                                width=SIDEBAR_W)
        self._sidebar.pack(fill='both', expand=True)

        # Barra de estado
        tk.Frame(self, bg=C['separator'], height=1).pack(fill='x', side='bottom')
        self._status_frame = tk.Frame(self, bg=C['sidebar'])
        self._status_frame.pack(fill='x', side='bottom')
        self._status_var = tk.StringVar(value='Cargando…')
        tk.Label(self._status_frame, textvariable=self._status_var,
                font=('SF Pro Display', 10), fg=C['text_sec'],
                bg=C['sidebar'], anchor='w', padx=16, pady=5,
                wraplength=380).pack(fill='x')

        self._build_sidebar()

    def _build_sidebar(self):
        sb = self._sidebar

        # Header
        header = tk.Frame(sb, bg=C['sidebar'], pady=16)
        header.pack(fill='x', padx=20)
        tk.Label(header, text='✈', font=('SF Pro Display', 26),
                fg=C['accent'], bg=C['sidebar']).pack(anchor='w')
        tk.Label(header, text='Flight Graph',
                font=('SF Pro Display', 18, 'bold'),
                fg=C['text_primary'], bg=C['sidebar']).pack(anchor='w')
        tk.Label(header, text='Análisis de rutas aéreas',
                font=('SF Pro Display', 11), fg=C['text_sec'],
                bg=C['sidebar']).pack(anchor='w')
        tk.Label(header, text='Autores: Jonathan Calles, Jairo Molina, Santiago Florez',
                font=('SF Pro Display', 9), fg=C['text_hint'],
                bg=C['sidebar'], wraplength=SIDEBAR_W - 40, justify='left').pack(anchor='w', pady=(4, 0))

        tk.Frame(sb, bg=C['separator'], height=1).pack(fill='x')

        # Panel scrollable
        scroll_outer = tk.Frame(sb, bg=C['sidebar'])
        scroll_outer.pack(fill='both', expand=True)
        vscroll = tk.Scrollbar(scroll_outer, orient='vertical',
                                troughcolor=C['card'])
        self._sb_canvas = tk.Canvas(scroll_outer, bg=C['sidebar'],
                                    yscrollcommand=vscroll.set,
                                    highlightthickness=0)
        vscroll.config(command=self._sb_canvas.yview)
        vscroll.pack(side='right', fill='y')
        self._sb_canvas.pack(side='left', fill='both', expand=True)
        self._inner = tk.Frame(self._sb_canvas, bg=C['sidebar'])
        self._sb_canvas.create_window((0, 0), window=self._inner, anchor='nw')
        self._inner.bind('<Configure>', lambda e: self._sb_canvas.configure(
            scrollregion=self._sb_canvas.bbox('all')))

        def _scroll(e):
            self._sb_canvas.yview_scroll(
                int(-1*(e.delta/120) or (-1 if e.num==4 else 1)), 'units')
        self._sb_canvas.bind('<MouseWheel>', _scroll)
        self._sb_canvas.bind('<Button-4>',   _scroll)
        self._sb_canvas.bind('<Button-5>',   _scroll)

        inner = self._inner

        # ── Estadísticas ───────────────────────────────────────────────
        self._build_section(inner, 'RESUMEN DEL GRAFO')
        sf = tk.Frame(inner, bg=C['card'],
                    highlightbackground=C['separator'], highlightthickness=1)
        sf.pack(fill='x', padx=16, pady=(0, 10))
        self._stats_labels: Dict[str, tk.Label] = {}
        for key, lbl_text in [
            ('nodos',           'Aeropuertos'),
            ('aristas',         'Rutas'),
            ('conexo',          'Conectado'),
            ('num_componentes', 'Componentes'),
            ('bipartito_mayor', 'Bipartito (comp. mayor)'),
            ('grado_promedio',  'Grado promedio'),
        ]:
            row = tk.Frame(sf, bg=C['card'])
            row.pack(fill='x', padx=12, pady=2)
            tk.Label(row, text=lbl_text, font=('SF Pro Display', 11),
                    fg=C['text_sec'], bg=C['card'], anchor='w').pack(side='left')
            lbl = tk.Label(row, text='—', font=('SF Pro Display', 11, 'bold'),
                        fg=C['text_primary'], bg=C['card'], anchor='e')
            lbl.pack(side='right')
            self._stats_labels[key] = lbl

        # ── Buscar aeropuerto ──────────────────────────────────────────
        self._build_section(inner, 'BUSCAR AEROPUERTO')
        sf2 = tk.Frame(inner, bg=C['sidebar'])
        sf2.pack(fill='x', padx=16, pady=(0, 4))
        wrap = tk.Frame(sf2, bg=C['card'],
                        highlightbackground=C['separator'], highlightthickness=1)
        wrap.pack(fill='x', pady=(0, 6))
        self._search_var = tk.StringVar()
        self._search_entry = tk.Entry(
            wrap, textvariable=self._search_var,
            font=('SF Pro Display', 12), bg=C['card'],
            fg=C['text_primary'], insertbackground=C['accent'],
            relief='flat', bd=8)
        self._search_entry.pack(fill='x')
        self._search_entry.bind('<Return>', lambda e: self._do_search())

        btn_row = tk.Frame(sf2, bg=C['sidebar'])
        btn_row.pack(fill='x')
        _make_button(btn_row, 'Buscar', self._do_search, accent=True)\
            .pack(side='left', fill='x', expand=True, padx=(0, 3))
        _make_button(btn_row, 'Como origen', lambda: self._set_from_search('src'), small=True)\
            .pack(side='left', padx=3)
        _make_button(btn_row, 'Como destino', lambda: self._set_from_search('dst'), small=True)\
            .pack(side='left', padx=(3, 0))

        lb_wrap = tk.Frame(inner, bg=C['sidebar'])
        lb_wrap.pack(fill='x', padx=16, pady=(4, 10))
        self._search_lb = tk.Listbox(
            lb_wrap, height=5, font=('SF Pro Display', 11), bg=C['card'],
            fg=C['text_primary'], selectbackground=C['accent'],
            selectforeground='white', relief='flat', bd=0,
            activestyle='none', exportselection=False)
        self._search_lb.pack(fill='x')
        self._search_lb.bind('<Double-Button-1>', self._on_search_double)
        self._search_results: List[Airport] = []

        # ── Aeropuertos seleccionados ──────────────────────────────────
        self._build_section(inner, 'AEROPUERTO ORIGEN')
        self._src_card = self._build_airport_card(inner)
        self._build_section(inner, 'AEROPUERTO DESTINO')
        self._dst_card = self._build_airport_card(inner)

        # ── Acciones ───────────────────────────────────────────────────
        self._build_section(inner, 'ACCIONES')
        af = tk.Frame(inner, bg=C['sidebar'])
        af.pack(fill='x', padx=16, pady=(0, 10))

        _make_button(af, '🗺  Abrir / Actualizar mapa',
                    self._open_map, accent=True).pack(fill='x', pady=2)
        _make_button(af, '📍  Camino mínimo (Origen → Destino)',
                    self._do_shortest_path).pack(fill='x', pady=2)
        _make_button(af, '📊  Top 10 rutas más largas',
                    self._do_top_longest).pack(fill='x', pady=2)
        _make_button(af, '🌲  Ver MST en mapa',
                    self._do_show_mst).pack(fill='x', pady=2)
        _make_button(af, '📈  Analizar grafo completo',
                    self._do_full_analysis).pack(fill='x', pady=2)
        _make_button(af, '🧩  Ver componentes por separado',
                    self._do_view_components).pack(fill='x', pady=2)
        _make_button(af, '✕  Limpiar selección',
                    self._do_clear).pack(fill='x', pady=2)

        # ── Resultados ─────────────────────────────────────────────────
        self._build_section(inner, 'RESULTADOS')
        self._result_frame = tk.Frame(inner, bg=C['sidebar'])
        self._result_frame.pack(fill='x', padx=16, pady=(0, 24))

    def _build_section(self, parent, text: str):
        f = tk.Frame(parent, bg=C['sidebar'])
        f.pack(fill='x', padx=16, pady=(14, 5))
        tk.Label(f, text=text, font=('SF Pro Display', 9, 'bold'),
                fg=C['text_hint'], bg=C['sidebar']).pack(anchor='w')
        tk.Frame(parent, bg=C['separator'], height=1).pack(fill='x', padx=16)

    def _build_airport_card(self, parent) -> tk.Frame:
        card = tk.Frame(parent, bg=C['card'],
                        highlightbackground=C['separator'], highlightthickness=1)
        card.pack(fill='x', padx=16, pady=(4, 0))
        lbl = tk.Label(card, text='Ninguno seleccionado',
                        font=('SF Pro Display', 11), fg=C['text_hint'],
                        bg=C['card'], justify='left', anchor='w',
                        padx=10, pady=8, wraplength=290)
        lbl.pack(fill='x')
        card._label = lbl  # type: ignore
        return card

    # ─────────────────────────────────────────
    #  Selección
    # ─────────────────────────────────────────

    def _select_src(self, code: str):
        self.selected_src  = code
        self._current_path = []
        self._show_mst     = False
        self._update_card(self._src_card, code, 'ORIGEN')
        self._set_status(f'Origen: {code}. Selecciona destino o abre el mapa.')
        self._regen_map()

    def _select_dst(self, code: str):
        self.selected_dst  = code
        self._current_path = []
        self._update_card(self._dst_card, code, 'DESTINO')
        self._set_status(f'Destino: {code}. Pulsa "Camino mínimo" o abre el mapa.')
        self._regen_map()

    def _update_card(self, card: tk.Frame, code: str, role: str):
        ap  = self.graph.airports[code]
        txt = (f"{ap.code}  ·  {ap.name}\n"
            f"{ap.city}, {ap.country}\n"
            f"Lat {ap.lat:.4f}  |  Lon {ap.lon:.4f}")
        card._label.config(text=txt, fg=C['text_primary'])  # type: ignore

    # ─────────────────────────────────────────
    #  Búsqueda
    # ─────────────────────────────────────────

    def _do_search(self):
        q = self._search_var.get().strip()
        if not q:
            return
        self._search_results = self.graph.search_airports(q, max_results=20)
        self._search_lb.delete(0, 'end')
        if not self._search_results:
            self._search_lb.insert('end', 'Sin resultados')
            return
        for ap in self._search_results:
            self._search_lb.insert('end', f"{ap.code}  {ap.city}, {ap.country}")

    def _selected_search_code(self) -> Optional[str]:
        sel = self._search_lb.curselection()
        if not sel or sel[0] >= len(self._search_results):
            return None
        return self._search_results[sel[0]].code

    def _set_from_search(self, role: str):
        code = self._selected_search_code()
        if not code:
            self._set_status('Selecciona un aeropuerto de la lista primero.')
            return
        if role == 'src':
            self._select_src(code)
        else:
            self._select_dst(code)

    def _on_search_double(self, event):
        # Doble clic en la lista: asigna como origen si aún no hay, sino como destino
        code = self._selected_search_code()
        if not code:
            return
        if self.selected_src is None:
            self._select_src(code)
        else:
            self._select_dst(code)

    # ─────────────────────────────────────────
    #  Mapa Folium
    # ─────────────────────────────────────────

    def _regen_map(self, and_open: bool = False):
        # Lanza la generación del mapa en background para no congelar la UI

        single_comp_nodes = None
        single_comp_color = None
        if getattr(self, '_viewing_component_idx', None) is not None and self._components_cache:
            idx = self._viewing_component_idx
            single_comp_nodes = self._components_cache[idx]
            is_main = (idx == 0)
            single_comp_color = '#007AFF' if is_main else TOP_ROUTE_COLORS[idx % len(TOP_ROUTE_COLORS)]

        def _build():
            path = build_map(
                graph     = self.graph,
                src_code  = self.selected_src,
                dst_code  = self.selected_dst,
                path      = self._current_path if self._current_path else None,
                mst_edges = self._mst_edges if self._show_mst else None,
                show_mst  = self._show_mst,
                top_paths = self._top_paths if self._top_paths else None,
                single_comp_nodes = single_comp_nodes,
                single_comp_color = single_comp_color,
            )
            self.after(0, lambda: self._on_map_ready(path, and_open))

        threading.Thread(target=_build, daemon=True).start()

    def _on_map_ready(self, path: str, and_open: bool):
        self._map_path = path
        if and_open:
            filename = os.path.basename(path)
            url = f'http://127.0.0.1:{self.server_port}/{filename}'
            webbrowser.open(url)
        self._set_status_idle()

    def _open_map(self):
        # Genera y abre el mapa en el browser del sistema
        self._set_status('Generando mapa Folium…')
        self._regen_map(and_open=True)

    # ─────────────────────────────────────────
    #  Acciones de análisis
    # ─────────────────────────────────────────

    def _do_shortest_path(self):
        self._viewing_component_idx = None
        if not self.selected_src:
            self._set_status('⚠ Selecciona un aeropuerto origen primero.'); return
        if not self.selected_dst:
            self._set_status('⚠ Selecciona un aeropuerto destino primero.'); return
        self._set_status('Calculando camino mínimo (Dijkstra)…')

        def _run():
            dist, path = self.graph.shortest_path_between(
                self.selected_src, self.selected_dst)
            self.after(0, lambda: self._show_path(dist, path))

        threading.Thread(target=_run, daemon=True).start()

    def _show_path(self, dist: float, path: List[str]):
        self._clear_results()
        if not path or dist == math.inf:
            self._set_status('Sin ruta disponible entre esos aeropuertos.')
            self._add_result('No existe camino entre los aeropuertos.', C['red'])
            return
        self._current_path = path
        self._regen_map(and_open=True)

        self._add_result(f'Distancia total: {dist:,.0f} km',
                        C['accent'], size=14, weight='bold')
        self._add_result(f'Escalas: {max(0, len(path)-2)} aeropuerto(s) intermedios')
        for i, code in enumerate(path):
            ap = self.graph.airports[code]
            icon = '🛫' if i == 0 else ('🛬' if i == len(path)-1 else '↓')
            self._add_result(
                f"{icon}  {ap.code}  {ap.name}\n     {ap.city}, {ap.country}",
                size=11)
            # Distancia del segmento hacia el siguiente aeropuerto
            if i < len(path) - 1:
                w = self._edge_weight(code, path[i + 1])
                if w is not None:
                    self._add_result(f"        ↕  {w:,.0f} km", C['text_sec'], size=10)
        self._set_status(
            f'{self.selected_src} → {self.selected_dst}  |  '
            f'{dist:,.0f} km  |  {len(path)-1} tramo(s)')

    def _do_top_longest(self):
        self._viewing_component_idx = None
        if not self.selected_src:
            self._set_status('⚠ Selecciona un aeropuerto origen primero.'); return
        self._top_paths = []
        self._set_status('Calculando top 10 caminos más largos…')

        def _run():
            results = self.graph.top_longest_shortest_paths(self.selected_src, k=10)
            self.after(0, lambda: self._show_top(results))

        threading.Thread(target=_run, daemon=True).start()

    def _show_top(self, results):
        self._clear_results()
        src_ap = self.graph.airports[self.selected_src]
        self._add_result(f'Top 10 desde {src_ap.code}',
                        C['accent'], size=13, weight='bold')
        if not results:
            self._add_result('Sin resultados (aeropuerto aislado).', C['red']); return

        # Guardar para el mapa y regenerar
        self._top_paths = results
        self._regen_map(and_open=True)

        for rank, (code, dist, path) in enumerate(results, 1):
            ap = self.graph.airports[code]
            route_color = TOP_ROUTE_COLORS[(rank - 1) % len(TOP_ROUTE_COLORS)]

            # Fila de cabecera con pastilla de color
            header_row = tk.Frame(self._result_frame, bg=C['sidebar'])
            header_row.pack(fill='x', pady=(4, 1))
            swatch = tk.Frame(header_row, bg=route_color, width=14, height=14)
            swatch.pack(side='left', padx=(0, 6))
            swatch.pack_propagate(False)
            tk.Label(header_row,
                    text=f"#{rank}  {ap.code} — {ap.name}",
                    font=('SF Pro Display', 11, 'bold'),
                    fg=C['text_primary'], bg=C['sidebar'], anchor='w').pack(side='left')

            # Detalle
            self._add_result(
                f"     {ap.city}, {ap.country}\n"
                f"     {dist:,.0f} km  ·  {len(path)-1} tramo(s)",
                size=10)

            # Tramos con distancia de cada segmento
            if path and len(path) >= 2:
                segmentos = []
                for i in range(len(path) - 1):
                    w = self._edge_weight(path[i], path[i + 1])
                    seg = f'{path[i]} \u2192 {path[i+1]}'
                    if w is not None:
                        seg += f'  ({w:,.0f} km)'
                    segmentos.append(seg)
                self._add_result(
                    '     Tramos:\n     ' + '\n     '.join(segmentos),
                    C['text_sec'], size=10)

            tk.Frame(self._result_frame, bg=C['separator'], height=1)\
                .pack(fill='x', pady=3)

        self._set_status(f'Top 10 desde {self.selected_src} calculado. Visualizado en el mapa.')

    def _do_show_mst(self):
        self._viewing_component_idx = None
        self._set_status('Calculando MST (Kruskal)…')

        def _run():
            mst_data = self.graph.mst_all_components()
            self.after(0, lambda: self._show_mst_result(mst_data))

        threading.Thread(target=_run, daemon=True).start()

    def _show_mst_result(self, mst_data: dict):
        self._clear_results()
        self._show_mst  = True
        self._mst_edges = []
        total_w = 0.0
        for i, (edges, w) in mst_data.items():
            self._mst_edges.extend(edges)
            total_w += w
        self._regen_map(and_open=True)
        comps = self.graph.connected_components()
        self._add_result('Árbol de Expansión Mínima (MST)',
                        C['orange'], size=13, weight='bold')
        self._add_result(f'Peso total: {total_w:,.0f} km', size=12)
        for i, (comp_edges, comp_w) in mst_data.items():
            sz = len(comps[i]) if i < len(comps) else '?'
            self._add_result(
                f'Comp. {i+1}: {sz} aeropuertos  ·  {len(comp_edges)} aristas  ·  {comp_w:,.0f} km',
                size=11)
        self._set_status(f'MST visualizado en el mapa. Peso total: {total_w:,.0f} km')

    def _do_full_analysis(self):
        self._viewing_component_idx = None
        self._set_status('Analizando grafo completo…')

        def _run():
            summary      = self.graph.summary()
            comps        = self.graph.connected_components()
            # Bipartito del grafo completo (casi siempre False)
            bip_full, _  = self.graph.is_bipartite(None)
            # Bipartito de la componente mayor (índice 0)
            bip_major, _ = self.graph.is_bipartite(comps[0] if comps else None)
            # Si hay origen seleccionado, detectar su componente
            src_comp_idx = None
            bip_src_comp = None
            if self.selected_src:
                for idx, comp in enumerate(comps):
                    if self.selected_src in comp:
                        src_comp_idx = idx
                        if idx != 0:   # solo si NO es la componente mayor
                            bip_src_comp, _ = self.graph.is_bipartite(comp)
                        break
            self.after(0, lambda: self._show_analysis(
                summary, comps, bip_full, bip_major, src_comp_idx, bip_src_comp))

        threading.Thread(target=_run, daemon=True).start()

    def _show_analysis(self, summary: dict, comps,
                    bip_full: bool, bip_major: bool,
                    src_comp_idx: Optional[int],
                    bip_src_comp: Optional[bool]):
        self._clear_results()
        self._update_stats(summary)
        self._add_result('Análisis completo del grafo',
                        C['accent'], size=13, weight='bold')

        conn_c = C['green'] if summary['conexo'] else C['red']
        self._add_result(
            'El grafo ES conexo.' if summary['conexo']
            else f"El grafo NO es conexo.\n{summary['num_componentes']} componentes.", conn_c)

        if not summary['conexo']:
            for i, comp in enumerate(comps[:10]):
                self._add_result(f'  Comp. {i+1}: {len(comp)} aeropuertos', size=11)
            if len(comps) > 10:
                self._add_result(f'  … y {len(comps)-10} más.', size=11)

        tk.Frame(self._result_frame, bg=C['separator'], height=1).pack(fill='x', pady=5)

        # ── Sección bipartito ──────────────────────────────────────────
        # 1. Estado del grafo completo
        self._add_result(
            'El grafo completo ES bipartito.' if bip_full
            else 'El grafo completo NO es bipartito.',
            C['green'] if bip_full else C['red'], size=11)

        # 2. Si no es bipartito (el grafo completo), indicar que se analiza la comp. mayor
        if not bip_full:
            self._add_result(
                '→ Por tanto, se analiza la componente más grande:', C['text_sec'], size=11)
            major_size = len(comps[0]) if comps else 0
            bip_c = C['green'] if bip_major else C['orange']
            self._add_result(
                f'Componente mayor ({major_size} aeropuertos): '
                + ('BIPARTITA.' if bip_major else 'NO bipartita (tiene ciclo impar).'),
                bip_c, size=12, weight='bold')

        # 3. Si el origen está en otra componente distinta a la mayor
        if src_comp_idx is not None and src_comp_idx != 0 and bip_src_comp is not None:
            src_size = len(comps[src_comp_idx]) if src_comp_idx < len(comps) else '?'
            bip_sc = C['green'] if bip_src_comp else C['orange']
            self._add_result(
                f'\nAeropuerto origen está en la componente {src_comp_idx + 1} '
                f'({src_size} aeropuertos):', C['text_sec'], size=11)
            self._add_result(
                f'Componente {src_comp_idx + 1}: '
                + ('BIPARTITA.' if bip_src_comp else 'NO bipartita (tiene ciclo impar).'),
                bip_sc, size=11)

        tk.Frame(self._result_frame, bg=C['separator'], height=1).pack(fill='x', pady=5)

        self._add_result(f'Peso total MST: {summary["mst_peso_total"]:,.0f} km')
        self._add_result(
            f'Grado promedio: {summary["grado_promedio"]:.2f}\n'
            f'Grado máximo:   {summary["grado_maximo"]}', size=11)
        self._set_status('Análisis completo finalizado.')

    def _do_clear(self):
        self.selected_src  = None
        self.selected_dst  = None
        self._current_path = []
        self._show_mst     = False
        self._mst_edges    = []
        self._top_paths    = []
        self._viewing_component_idx = None
        self._src_card._label.config(  # type: ignore
            text='Ninguno seleccionado', fg=C['text_hint'])
        self._dst_card._label.config(  # type: ignore
            text='Ninguno seleccionado', fg=C['text_hint'])
        self._clear_results()
        self._regen_map(and_open=False)
        self._set_status('Selección limpiada.')

    # ─────────────────────────────────────────
    #  Ver Componentes
    # ─────────────────────────────────────────

    def _do_view_components(self):
        self._viewing_component_idx = None
        self._set_status('Calculando componentes conexas...')
        def _run():
            comps = self.graph.connected_components()
            self.after(0, lambda: self._show_component_ui(comps))
        threading.Thread(target=_run, daemon=True).start()

    def _show_component_ui(self, comps):
        self._components_cache = comps
        self._viewing_component_idx = 0
        self._render_component_results()

    def _render_component_results(self):
        self._clear_results()
        if not self._components_cache or getattr(self, '_viewing_component_idx', None) is None:
            return

        idx = self._viewing_component_idx
        comps = self._components_cache
        comp_nodes = comps[idx]

        # Navigation UI
        nav_frame = tk.Frame(self._result_frame, bg=C['sidebar'])
        nav_frame.pack(fill='x', pady=(0, 10))

        btn_prev = _make_button(nav_frame, '◀ Ant', lambda: self._change_comp(-1), small=True)
        btn_prev.pack(side='left')
        if idx == 0: btn_prev.config(state='disabled')

        btn_next = _make_button(nav_frame, 'Sig ▶', lambda: self._change_comp(1), small=True)
        btn_next.pack(side='right')
        if idx == len(comps) - 1: btn_next.config(state='disabled')

        tk.Label(nav_frame, text=f'Comp. {idx + 1} / {len(comps)}',
                font=('SF Pro Display', 11, 'bold'), fg=C['text_primary'], bg=C['sidebar']).pack(side='left', expand=True)

        is_main = (idx == 0)
        color = '#007AFF' if is_main else TOP_ROUTE_COLORS[idx % len(TOP_ROUTE_COLORS)]

        # Header with square
        header_row = tk.Frame(self._result_frame, bg=C['sidebar'])
        header_row.pack(fill='x', pady=(4, 6))
        swatch = tk.Frame(header_row, bg=color, width=16, height=16)
        swatch.pack(side='left', padx=(0, 8))
        swatch.pack_propagate(False)
        tk.Label(header_row,
                text="Componente Mayor" if is_main else f"Componente {idx + 1}",
                font=('SF Pro Display', 12, 'bold'),
                fg=C['text_primary'], bg=C['sidebar']).pack(side='left')

        self._add_result(f'Tamaño: {len(comp_nodes)} aeropuertos', size=11)

        # List regions or countries
        if is_main:
            regions = self._get_regions_for_nodes(comp_nodes)
            self._add_result('\nRegiones presentes:', C['text_sec'], size=11, weight='bold')
            for r in sorted(regions):
                self._add_result(f' • {r}', size=11)
        else:
            countries = self._get_countries_for_nodes(comp_nodes)
            self._add_result('\nPaíses presentes:', C['text_sec'], size=11, weight='bold')
            for c in sorted(countries)[:15]:
                self._add_result(f' • {c}', size=11)
            if len(countries) > 15:
                self._add_result(f'   ... y {len(countries) - 15} más.', size=11)

        # Regenera el mapa en background pero NO lo abre; el usuario decide cuándo
        self._regen_map(and_open=False)
        self._set_status(f'Componente {idx + 1} lista. Pulsa el botón para verla en el mapa.')

        # Botón explícito para abrir el mapa de esta componente
        tk.Frame(self._result_frame, bg=C['separator'], height=1).pack(fill='x', pady=(10, 4))
        _make_button(
            self._result_frame,
            '🗺  Ver esta componente en el mapa',
            self._open_map,
            accent=True,
        ).pack(fill='x', pady=(0, 8))

    def _change_comp(self, delta):
        if self._components_cache and getattr(self, '_viewing_component_idx', None) is not None:
            new_idx = self._viewing_component_idx + delta
            if 0 <= new_idx < len(self._components_cache):
                self._viewing_component_idx = new_idx
                self._render_component_results()

    def _get_countries_for_nodes(self, nodes: Set[str]) -> Set[str]:
        countries = set()
        for code in nodes:
            ap = self.graph.airports.get(code)
            if ap:
                countries.add(ap.country)
        return countries

    def _get_regions_for_nodes(self, nodes: Set[str]) -> Set[str]:
        countries = self._get_countries_for_nodes(nodes)
        regions = set()
        for c in countries:
            regions.add(self._country_to_region(c))
        return regions

    def _country_to_region(self, country: str) -> str:
        c_lower = country.lower()
        if c_lower in ['united states', 'canada', 'mexico']: return 'North America'
        if c_lower in ['brazil', 'argentina', 'colombia', 'chile', 'peru', 'ecuador', 'venezuela', 'bolivia', 'uruguay', 'paraguay']: return 'South America'
        if c_lower in ['united kingdom', 'germany', 'france', 'italy', 'spain', 'netherlands', 'switzerland', 'russia', 'sweden', 'norway', 'finland', 'poland', 'belgium', 'austria', 'greece', 'portugal', 'ireland', 'denmark']: return 'Europe'
        if c_lower in ['china', 'japan', 'india', 'south korea', 'indonesia', 'thailand', 'vietnam', 'malaysia', 'philippines', 'singapore', 'taiwan']: return 'Asia'
        if c_lower in ['australia', 'new zealand', 'fiji']: return 'Oceania'
        if c_lower in ['south africa', 'egypt', 'nigeria', 'kenya', 'morocco', 'ethiopia', 'algeria', 'tunisia', 'ghana', 'senegal']: return 'Africa'
        if c_lower in ['saudi arabia', 'united arab emirates', 'israel', 'turkey', 'qatar']: return 'Middle East'
        if c_lower in ['cuba', 'dominican republic', 'jamaica', 'puerto rico', 'bahamas', 'trinidad and tobago']: return 'Caribbean'
        if c_lower in ['guatemala', 'honduras', 'el salvador', 'nicaragua', 'costa rica', 'panama', 'belize']: return 'Central America'
        return 'Other Regions'

    # ─────────────────────────────────────────
    #  Helpers
    # ─────────────────────────────────────────

    def _edge_weight(self, src: str, dst: str) -> Optional[float]:
        # Busca en ambas direcciones porque el grafo es no dirigido
        for nbr, w in self.graph.adjacency.get(src, []):
            if nbr == dst:
                return w
        for nbr, w in self.graph.adjacency.get(dst, []):
            if nbr == src:
                return w
        return None

    def _clear_results(self):
        for w in self._result_frame.winfo_children():
            w.destroy()

    def _add_result(self, text: str, color=None, size=12, weight='normal'):
        tk.Label(
            self._result_frame, text=text,
            font=('SF Pro Display', size, weight),
            fg=color or C['text_primary'],
            bg=C['sidebar'], justify='left', anchor='w',
            wraplength=300, pady=2,
        ).pack(anchor='w', fill='x')

    def _update_stats(self, summary: dict):
        mapping = {
            'nodos'          : f"{summary['nodos']:,}",
            'aristas'        : f"{summary['aristas']:,}",
            'conexo'         : 'Sí' if summary['conexo'] else 'No',
            'num_componentes': str(summary['num_componentes']),
            'bipartito_mayor': 'Sí' if summary['bipartito_mayor'] else 'No',
            'grado_promedio' : f"{summary['grado_promedio']:.2f}",
        }
        for key, val in mapping.items():
            if key in self._stats_labels:
                self._stats_labels[key].config(text=val)

    def _set_status(self, msg: str):
        self._status_var.set(msg)

    def _set_status_idle(self):
        n = self.graph.node_count
        e = self.graph.edge_count
        self._status_var.set(
            f'{n:,} aeropuertos · {e:,} rutas cargadas.')

    # ─────────────────────────────────────────
    #  Bienvenida
    # ─────────────────────────────────────────

    def _show_welcome(self):
        self._set_status('Calculando estadísticas…')

        def _run():
            summary = self.graph.summary()
            self.after(0, lambda: self._on_welcome(summary))

        threading.Thread(target=_run, daemon=True).start()

    def _on_welcome(self, summary: dict):
        self._update_stats(summary)
        self._set_status_idle()
        # Generar mapa inicial (sin selección)
        self._regen_map(and_open=False)