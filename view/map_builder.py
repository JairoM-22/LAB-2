import os
import re
import tempfile
from typing import List, Optional

import folium

from model.graph import Edge, FlightGraph


# Colores principales del mapa
COL_NODE       = '#007AFF'
COL_ORIGIN     = '#FF3B30'
COL_DEST       = '#FF9500'
COL_PATH       = '#007AFF'
COL_MST        = '#FF9500'
COL_EDGE_SRC   = '#FF3B30'
COL_EDGE_DST   = '#FF9500'
COL_NODE_PATH  = '#34C759'

# Paleta de 10 colores para las rutas del top 10; evitamos colores fosforescentes
TOP_ROUTE_COLORS = [
    '#2ECC71', '#E91E8C', '#00B4D8', '#F4A300', '#E05C00',
    '#C0392B', '#8E44AD', '#16A085', '#D4618A', '#2980B9',
]

TOP_ROUTE_NAMES = [
    'Verde esmeralda', 'Rosa frambuesa', 'Azul océano', 'Ámbar dorado',
    'Naranja quemado', 'Rojo rubí', 'Violeta uva', 'Verde azulado',
    'Rosa durazno', 'Azul zafiro',
]

# Archivo HTML fijo para que el browser pueda recargarlo sin cambiar de URL
_MAP_DIR  = os.path.join(tempfile.gettempdir(), 'flight_graph_app_maps')
os.makedirs(_MAP_DIR, exist_ok=True)
_MAP_FILE = os.path.join(_MAP_DIR, 'flight_graph_map.html')


def _fix_no_wrap(html: str) -> str:
    # Folium repite el mapa en X por defecto; aquí lo corregimos en post-proceso
    html = html.replace('"noWrap": false', '"noWrap": true')

    # Inyectar worldCopyJump: false en las opciones de L.map(...)
    html = re.sub(
        r'(var map_[a-f0-9]+ = L\.map\([^{]+\{)',
        r'\1\n                "worldCopyJump": false,',
        html,
    )

    # Script de auto-recarga: detecta cambios en Last-Modified cada 1.5 s
    auto_reload_script = """
<script>
    let _lastModified = null;
    setInterval(() => {
        fetch(location.href, { method: 'HEAD', cache: 'no-store' })
            .then(r => {
                const current = r.headers.get('Last-Modified');
                if (_lastModified && current !== _lastModified) {
                    location.reload();
                }
                _lastModified = current;
            })
            .catch(e => {});
    }, 1500);
</script>
"""
    html = html.replace('</body>', auto_reload_script + '\n</body>')
    return html


def _get_weight(graph: FlightGraph, src: str, dst: str) -> Optional[float]:
    # Busca el peso en ambas direcciones porque el grafo es no dirigido
    for nbr, w in graph.adjacency.get(src, []):
        if nbr == dst:
            return w
    for nbr, w in graph.adjacency.get(dst, []):
        if nbr == src:
            return w
    return None


def _dist_label(lat: float, lon: float, text: str, color: str = '#333') -> folium.Marker:
    # Etiqueta flotante en el punto medio de un segmento; pointer-events:none para no obstruir
    return folium.Marker(
        location=[lat, lon],
        icon=folium.DivIcon(
            html=(
                f'<div style="'
                f'font-size:9px;font-weight:bold;font-family:sans-serif;'
                f'background:{color};color:#fff;'
                f'padding:1px 5px;border-radius:4px;'
                f'white-space:nowrap;pointer-events:none;'
                f'box-shadow:0 1px 3px rgba(0,0,0,0.4);">'
                f'{text}</div>'
            ),
            icon_size=(80, 18),
            icon_anchor=(40, 9),
        ),
    )


def build_map(
    graph      : FlightGraph,
    src_code   : Optional[str]        = None,
    dst_code   : Optional[str]        = None,
    path       : Optional[List[str]]  = None,
    mst_edges  : Optional[List[Edge]] = None,
    show_mst   : bool                 = False,
    top_paths  : Optional[List[tuple]] = None,
    single_comp_nodes: Optional[set]  = None,
    single_comp_color: Optional[str]  = None,
) -> str:
    # Genera el HTML del mapa y retorna la ruta al archivo temporal

    # Centro del mapa: componente activa > origen > mundo
    if single_comp_nodes:
        lats, lons = [], []
        for code in list(single_comp_nodes)[:50]:
            ap = graph.airports.get(code)
            if ap:
                lats.append(ap.lat)
                lons.append(ap.lon)
        if lats:
            center = [sum(lats)/len(lats), sum(lons)/len(lons)]
            zoom = 4 if len(lats) < 10 else 3
        else:
            center = [20, 10]; zoom = 3
    elif src_code and src_code in graph.airports:
        ap     = graph.airports[src_code]
        center = [ap.lat, ap.lon]; zoom = 4
    else:
        center = [20, 10]; zoom = 3

    m = folium.Map(
        location  = center,
        zoom_start= zoom,
        prefer_canvas=True,
        max_bounds= True,
        min_zoom  = 2,
    )
    # maxBounds estrictos para bloquear el desplazamiento fuera del mundo
    m.options['maxBounds'] = [[-90, -180], [90, 180]]

    folium.TileLayer(
        tiles  = 'CartoDB positron',
        no_wrap= True,
        name   = 'Base',
        min_zoom=2,
    ).add_to(m)

    # Capa 1: todos los nodos como GeoJSON (más rápido que N marcadores individuales)
    features = []
    for code, ap in graph.airports.items():
        if single_comp_nodes is not None and code not in single_comp_nodes:
            continue
        if code in (src_code, dst_code):
            continue   # origen y destino tienen marcadores especiales
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [ap.lon, ap.lat]},
            "properties": {
                "code": code, "name": ap.name,
                "city": ap.city, "country": ap.country,
                "lat": f"{ap.lat:.4f}", "lon": f"{ap.lon:.4f}",
            },
        })

    node_color = single_comp_color if single_comp_color else COL_NODE
    folium.GeoJson(
        {"type": "FeatureCollection", "features": features},
        name  = 'Aeropuertos',
        marker= folium.CircleMarker(
            radius=4, color=node_color, fill=True,
            fill_color=node_color, fill_opacity=0.75, weight=1,
        ),
        tooltip= folium.GeoJsonTooltip(
            fields  = ['code', 'city', 'country'],
            aliases = ['✈ Código', 'Ciudad', 'País'],
            style   = 'font-family: sans-serif; font-size: 12px;',
        ),
        popup= folium.GeoJsonPopup(
            fields  = ['code', 'name', 'city', 'country', 'lat', 'lon'],
            aliases = ['Código', 'Nombre', 'Ciudad', 'País', 'Latitud', 'Longitud'],
        ),
    ).add_to(m)

    # Capa de aristas de la componente seleccionada (solo al explorar componentes)
    if single_comp_nodes is not None:
        fg_comp = folium.FeatureGroup(name='Aristas de la Componente', show=True)
        drawn = set()
        for code in single_comp_nodes:
            ap_src = graph.airports.get(code)
            if not ap_src: continue
            for nbr_code, weight in graph.adjacency.get(code, []):
                if nbr_code not in single_comp_nodes: continue
                edge_key = tuple(sorted([code, nbr_code]))
                if edge_key in drawn: continue
                drawn.add(edge_key)
                ap_dst = graph.airports.get(nbr_code)
                if not ap_dst: continue
                folium.PolyLine(
                    locations=[[ap_src.lat, ap_src.lon], [ap_dst.lat, ap_dst.lon]],
                    color=node_color, weight=1.0, opacity=0.4,
                ).add_to(fg_comp)
        fg_comp.add_to(m)

    # Capa 2: aristas que salen del origen
    if src_code and src_code in graph.airports:
        fg_src = folium.FeatureGroup(name='Rutas desde origen', show=True)
        ap_src = graph.airports[src_code]
        for nbr_code, weight in graph.adjacency.get(src_code, []):
            ap_nbr = graph.airports.get(nbr_code)
            if not ap_nbr: continue
            folium.PolyLine(
                locations=[[ap_src.lat, ap_src.lon], [ap_nbr.lat, ap_nbr.lon]],
                color=COL_EDGE_SRC, weight=1.2, opacity=0.5,
                tooltip=f"{src_code} → {nbr_code}  ({weight:,.0f} km)",
            ).add_to(fg_src)
        fg_src.add_to(m)

    # Capa 3: aristas que salen del destino
    if dst_code and dst_code in graph.airports:
        fg_dst = folium.FeatureGroup(name='Rutas desde destino', show=True)
        ap_dst = graph.airports[dst_code]
        for nbr_code, weight in graph.adjacency.get(dst_code, []):
            ap_nbr = graph.airports.get(nbr_code)
            if not ap_nbr: continue
            folium.PolyLine(
                locations=[[ap_dst.lat, ap_dst.lon], [ap_nbr.lat, ap_nbr.lon]],
                color=COL_EDGE_DST, weight=1.2, opacity=0.5,
                tooltip=f"{dst_code} → {nbr_code}  ({weight:,.0f} km)",
            ).add_to(fg_dst)
        fg_dst.add_to(m)

    # Capa 4: marcador rojo de origen con ícono de avión
    if src_code and src_code in graph.airports:
        ap = graph.airports[src_code]
        folium.Marker(
            location=[ap.lat, ap.lon],
            icon=folium.Icon(color='red', icon='plane', prefix='fa'),
            tooltip=f"✈ ORIGEN: {ap.code}",
            popup=folium.Popup(
                f"<b>ORIGEN</b><br><b>{ap.code}</b> — {ap.name}<br>"
                f"{ap.city}, {ap.country}<br>Lat {ap.lat:.4f} | Lon {ap.lon:.4f}",
                max_width=250,
            ),
        ).add_to(m)

    # Capa 5: marcador naranja de destino con ícono de bandera
    if dst_code and dst_code in graph.airports:
        ap = graph.airports[dst_code]
        folium.Marker(
            location=[ap.lat, ap.lon],
            icon=folium.Icon(color='orange', icon='flag', prefix='fa'),
            tooltip=f"🏁 DESTINO: {ap.code}",
            popup=folium.Popup(
                f"<b>DESTINO</b><br><b>{ap.code}</b> — {ap.name}<br>"
                f"{ap.city}, {ap.country}<br>Lat {ap.lat:.4f} | Lon {ap.lon:.4f}",
                max_width=250,
            ),
        ).add_to(m)

    # Capa 6: camino mínimo con etiquetas de distancia por segmento
    if path and len(path) > 1:
        fg_path = folium.FeatureGroup(name='Camino mínimo', show=True)
        coords = []
        for code in path:
            ap = graph.airports.get(code)
            if ap:
                coords.append([ap.lat, ap.lon])
        folium.PolyLine(
            locations=coords, color=COL_PATH, weight=3.5, opacity=0.9,
            tooltip='Camino mínimo',
        ).add_to(fg_path)

        for i, code in enumerate(path):
            if code in (src_code, dst_code): continue
            ap = graph.airports.get(code)
            if not ap: continue
            folium.CircleMarker(
                location=[ap.lat, ap.lon],
                radius=7, color='white', fill=True,
                fill_color=COL_NODE_PATH, fill_opacity=1.0, weight=2,
                tooltip=f"Escala {i}: {ap.code} — {ap.city}",
                popup=folium.Popup(
                    f"<b>Escala {i}</b><br><b>{ap.code}</b> — {ap.name}<br>"
                    f"{ap.city}, {ap.country}", max_width=220,
                ),
            ).add_to(fg_path)

        # Etiqueta de km en el punto medio de cada tramo
        for i in range(len(path) - 1):
            ap1 = graph.airports.get(path[i])
            ap2 = graph.airports.get(path[i + 1])
            if not ap1 or not ap2: continue
            w = _get_weight(graph, path[i], path[i + 1])
            if w is not None:
                mid_lat = (ap1.lat + ap2.lat) / 2
                mid_lon = (ap1.lon + ap2.lon) / 2
                _dist_label(mid_lat, mid_lon, f'{w:,.0f} km', '#005EC4').add_to(fg_path)
        fg_path.add_to(m)

    # Capa 7: árbol de expansión mínima
    if show_mst and mst_edges:
        fg_mst = folium.FeatureGroup(name='MST', show=True)
        for edge in mst_edges:
            ap1 = graph.airports.get(edge.src)
            ap2 = graph.airports.get(edge.dst)
            if not ap1 or not ap2: continue
            folium.PolyLine(
                locations=[[ap1.lat, ap1.lon], [ap2.lat, ap2.lon]],
                color=COL_MST, weight=1.5, opacity=0.7,
                tooltip=f"MST: {edge.src}↔{edge.dst}  {edge.weight:,.0f} km",
            ).add_to(fg_mst)
        fg_mst.add_to(m)

    # Capa 8: top 10 rutas más largas, cada una con color único de la paleta
    if top_paths:
        fg_top = folium.FeatureGroup(name='Top 10 rutas más largas', show=True)
        for rank, (dst_code_top, dist_top, path_top) in enumerate(top_paths, 1):
            if not path_top or len(path_top) < 2: continue
            route_color = TOP_ROUTE_COLORS[(rank - 1) % len(TOP_ROUTE_COLORS)]
            coords_top = []
            for code in path_top:
                ap = graph.airports.get(code)
                if ap:
                    coords_top.append([ap.lat, ap.lon])
            if len(coords_top) < 2: continue
            tramos = ' → '.join(path_top)
            folium.PolyLine(
                locations=coords_top,
                color=route_color, weight=2.5, opacity=0.85,
                tooltip=f"#{rank}  {path_top[0]} → {path_top[-1]}  ({dist_top:,.0f} km)<br>{tramos}",
            ).add_to(fg_top)

            # Marcador especial en el aeropuerto destino de cada ruta
            ap_dst_top = graph.airports.get(dst_code_top)
            if ap_dst_top:
                folium.CircleMarker(
                    location=[ap_dst_top.lat, ap_dst_top.lon],
                    radius=7, color='white', fill=True,
                    fill_color=route_color, fill_opacity=1.0, weight=2,
                    tooltip=f"#{rank}  {ap_dst_top.code} — {ap_dst_top.city}  ({dist_top:,.0f} km)",
                    popup=folium.Popup(
                        f"<b>#{rank} Ruta más larga</b><br>"
                        f"<b>{ap_dst_top.code}</b> — {ap_dst_top.name}<br>"
                        f"{ap_dst_top.city}, {ap_dst_top.country}<br>"
                        f"Distancia: {dist_top:,.0f} km<br>"
                        f"Tramos: {' → '.join(path_top)}",
                        max_width=300,
                    ),
                ).add_to(fg_top)

            # Nodos intermedios con el mismo color de la ruta
            for i, code in enumerate(path_top[1:-1], 1):
                if code == src_code: continue
                ap_int = graph.airports.get(code)
                if not ap_int: continue
                folium.CircleMarker(
                    location=[ap_int.lat, ap_int.lon],
                    radius=4, color='white', fill=True,
                    fill_color=route_color, fill_opacity=0.9, weight=1,
                    tooltip=f"Escala #{rank}: {ap_int.code} — {ap_int.city}",
                ).add_to(fg_top)

            # Etiquetas de km en cada segmento de esta ruta
            for i in range(len(path_top) - 1):
                ap1 = graph.airports.get(path_top[i])
                ap2 = graph.airports.get(path_top[i + 1])
                if not ap1 or not ap2: continue
                w = _get_weight(graph, path_top[i], path_top[i + 1])
                if w is not None:
                    mid_lat = (ap1.lat + ap2.lat) / 2
                    mid_lon = (ap1.lon + ap2.lon) / 2
                    _dist_label(mid_lat, mid_lon, f'{w:,.0f} km', route_color).add_to(fg_top)
        fg_top.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    # Guardar, aplicar fix anti-loop y sobreescribir
    m.save(_MAP_FILE)
    html = open(_MAP_FILE, encoding='utf-8').read()
    html = _fix_no_wrap(html)
    with open(_MAP_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    return _MAP_FILE

