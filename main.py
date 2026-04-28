import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox

# Asegurar que el directorio raíz esté en el path antes de los imports del proyecto
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from model.graph  import FlightGraph
from utils.loader import load_flights
from view.splash  import SplashScreen
from view.app     import FlightApp


def _load_and_launch(csv_path: str, splash: SplashScreen) -> None:
    # Corre en hilo secundario: carga el CSV y construye el grafo
    try:
        # El progreso del loader se mapea al rango [0.05, 0.55]
        def loader_cb(msg: str, pct: float):
            splash.post_progress(msg, 0.05 + pct * 0.50)

        airports, routes = load_flights(csv_path, progress_cb=loader_cb)

        # La construcción del grafo ocupa la franja [0.55, 0.85]
        def graph_cb(msg: str, pct: float):
            splash.post_progress(msg, 0.55 + pct * 0.30)

        graph = FlightGraph.build_from_records(
            airports, routes, progress_cb=graph_cb
        )

        # Pre-calentar el caché de componentes para que la UI no tarde al abrirse
        splash.post_progress('Calculando componentes conexas…', 0.87)
        _ = graph.connected_components()

        splash.post_progress('Listo. Abriendo aplicación…', 1.0)

        # after() es thread-safe; es la única forma correcta de tocar tk desde aquí
        splash.after(300, lambda: _open_app(splash, graph))

    except FileNotFoundError as exc:
        splash.after(0, lambda: _show_error(splash, str(exc)))
    except Exception as exc:
        import traceback
        splash.after(0, lambda: _show_error(
            splash, f"Error inesperado:\n{exc}\n\n{traceback.format_exc()}"
        ))


def _open_app(splash: SplashScreen, graph: FlightGraph) -> None:
    # Destruye el splash y arranca la ventana principal (siempre en hilo principal)
    splash.close()
    app = FlightApp(graph)
    app.mainloop()


def _show_error(splash: SplashScreen, msg: str) -> None:
    # Muestra el error al usuario antes de cerrar el splash
    messagebox.showerror('Error al cargar datos', msg)
    splash.close()


def main() -> None:
    # Si no se pasa argumento, busca el CSV en el mismo directorio del script
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    else:
        csv_path = os.path.join(ROOT, 'flights_final.csv')

    splash = SplashScreen()
    splash.post_progress('Iniciando…', 0.03)

    # El hilo se marca como daemon para que no bloquee el cierre de la app
    t = threading.Thread(
        target=_load_and_launch,
        args=(csv_path, splash),
        daemon=True,
    )
    t.start()

    splash.mainloop()


if __name__ == '__main__':
    main()

