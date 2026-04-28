import queue
import threading
import tkinter as tk

# Paleta de colores de la splash screen
C = {
    'bg'          : '#F5F5F7',
    'text_primary': '#1D1D1F',
    'text_sec'    : '#6E6E73',
    'accent'      : '#007AFF',
    'separator'   : '#E5E5EA',
}

SPINNER_CHARS = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']


class SplashScreen(tk.Tk):
    # Ventana de carga que se muestra mientras el grafo se construye en un hilo secundario

    def __init__(self):
        super().__init__()
        self.title('Flight Graph Analyzer')
        self.configure(bg=C['bg'])
        self.geometry('480x320')
        self.resizable(False, False)
        self.update_idletasks()
        # Centrar la ventana en la pantalla
        x = (self.winfo_screenwidth()  - 480) // 2
        y = (self.winfo_screenheight() - 320) // 2
        self.geometry(f'+{x}+{y}')

        # Cola thread-safe: el hilo secundario deposita aquí, el principal lee
        self._q: queue.Queue = queue.Queue()

        self._spinner_idx      = 0
        self._spinner_after_id = None
        self._poll_after_id    = None

        self._build_ui()
        self._animate_spinner()
        self._poll_queue()   # arrancar el ciclo de polling

    # ── Construcción de UI ────────────────────────────────────────────────

    def _build_ui(self):
        outer = tk.Frame(self, bg=C['bg'])
        outer.pack(expand=True, fill='both', padx=40, pady=40)

        tk.Label(outer, text='✈', font=('SF Pro Display', 52),
                 fg=C['accent'], bg=C['bg']).pack()

        tk.Label(outer, text='Flight Graph Analyzer',
                 font=('SF Pro Display', 20, 'bold'),
                 fg=C['text_primary'], bg=C['bg']).pack(pady=(8, 2))

        tk.Label(outer, text='Estructura de Datos II  ·  UniNorte',
                 font=('SF Pro Display', 11),
                 fg=C['text_sec'], bg=C['bg']).pack()
                 
        tk.Label(outer, text='Autores: Jonathan Calles, Jairo Molina, Santiago Florez',
                 font=('SF Pro Display', 9),
                 fg=C['text_sec'], bg=C['bg']).pack(pady=(4, 0))

        spinner_row = tk.Frame(outer, bg=C['bg'])
        spinner_row.pack(pady=(24, 4))

        self._spinner_lbl = tk.Label(
            spinner_row, text=SPINNER_CHARS[0],
            font=('SF Pro Display', 18),
            fg=C['accent'], bg=C['bg']
        )
        self._spinner_lbl.pack(side='left', padx=(0, 8))

        self._msg_var = tk.StringVar(value='Iniciando…')
        tk.Label(spinner_row, textvariable=self._msg_var,
                 font=('SF Pro Display', 12),
                 fg=C['text_sec'], bg=C['bg']).pack(side='left')

        prog_frame = tk.Frame(outer, bg=C['separator'],
                              height=4, highlightthickness=0)
        prog_frame.pack(fill='x', pady=(12, 0))
        self._prog_bar = tk.Frame(prog_frame, bg=C['accent'], height=4)
        self._prog_bar.place(x=0, y=0, relheight=1, relwidth=0)

    # ── Animación del spinner (hilo principal) ────────────────────────────

    def _animate_spinner(self):
        # Cicla los caracteres braille del spinner cada 80 ms
        self._spinner_idx = (self._spinner_idx + 1) % len(SPINNER_CHARS)
        self._spinner_lbl.config(text=SPINNER_CHARS[self._spinner_idx])
        self._spinner_after_id = self.after(80, self._animate_spinner)

    # ── Polling de la cola (hilo principal) ───────────────────────────────

    def _poll_queue(self):
        # Consume hasta 10 mensajes por ciclo para no bloquear el event loop
        try:
            for _ in range(10):
                msg, progress = self._q.get_nowait()
                self._msg_var.set(msg)
                if progress is not None:
                    self._prog_bar.place_configure(
                        relwidth=min(1.0, max(0.0, progress))
                    )
        except queue.Empty:
            pass
        self._poll_after_id = self.after(50, self._poll_queue)

    # ── API pública para el hilo secundario ──────────────────────────────

    def post_progress(self, msg: str, progress: float = None) -> None:
        # Thread-safe: solo encola el mensaje, nunca toca widgets directamente
        self._q.put((msg, progress))

    # ── Cierre ────────────────────────────────────────────────────────────

    def close(self):
        # Cancela los callbacks pendientes antes de destruir la ventana
        for after_id in (self._spinner_after_id, self._poll_after_id):
            if after_id is not None:
                self.after_cancel(after_id)
        self.destroy()
