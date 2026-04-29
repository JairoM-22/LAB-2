import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox

# Metemos el directorio raíz en sys.path para que los imports relativos funcionen
# sin importar desde dónde se ejecute el script
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from model.graph  import FlightGraph
from utils.loader import load_flights
from view.splash  import SplashScreen
from view.app     import FlightApp


def _load_and_launch(csv_path: str, splash: SplashScreen) -> None:
    # Todo el trabajo pesado (leer CSV, construir grafo) ocurre aquí,
    # en un hilo separado para que la splash screen no se congele
    try:
        # El loader reporta progreso entre 0 y 1; lo escalamos a [0.05, 0.55]
        # para que la barra avance de forma visual coherente con todo el proceso
        def loader_cb(msg: str, pct: float):
            splash.post_progress(msg, 0.05 + pct * 0.50)

        airports, routes = load_flights(csv_path, progress_cb=loader_cb)

        # La construcción del grafo ocupa la franja [0.55, 0.85]
        def graph_cb(msg: str, pct: float):
            splash.post_progress(msg, 0.55 + pct * 0.30)

        graph = FlightGraph.build_from_records(
            airports, routes, progress_cb=graph_cb
        )

        # Pre-calentamos las componentes conexas aquí mismo.
        # Si no lo hacemos, la primera vez que el usuario las pida
        # va a esperar varios segundos con la app ya abierta — mejor pagarlo ahora.
        splash.post_progress('Calculando componentes conexas…', 0.87)
        _ = graph.connected_components()

        splash.post_progress('Listo. Abriendo aplicación…', 1.0)

        # after() es la única forma thread-safe de pedirle algo al hilo de tkinter
        splash.after(300, lambda: _open_app(splash, graph))

    except FileNotFoundError as exc:
        splash.after(0, lambda: _show_error(splash, str(exc)))
    except Exception as exc:
        import traceback
        splash.after(0, lambda: _show_error(
            splash, f"Error inesperado:\n{exc}\n\n{traceback.format_exc()}"
        ))


def _open_app(splash: SplashScreen, graph: FlightGraph) -> None:
    # Cerramos el splash antes de abrir la app principal
    # para que no queden dos ventanas abiertas al mismo tiempo
    splash.close()
    app = FlightApp(graph)
    app.mainloop()


def _show_error(splash: SplashScreen, msg: str) -> None:
    messagebox.showerror('Error al cargar datos', msg)
    splash.close()


def main() -> None:
    # Si alguien pasa la ruta del CSV como argumento lo usamos;
    # si no, asumimos que está junto al script con el nombre por defecto
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    else:
        csv_path = os.path.join(ROOT, 'flights_final.csv')

    splash = SplashScreen()
    splash.post_progress('Iniciando…', 0.03)

    # El hilo daemon muere automáticamente cuando el usuario cierra la ventana,
    # así no dejamos procesos huérfanos corriendo en el fondo
    t = threading.Thread(
        target=_load_and_launch,
        args=(csv_path, splash),
        daemon=True,
    )
    t.start()

    splash.mainloop()


if __name__ == '__main__':
    main()
