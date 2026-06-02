#   ******************************************************************************
#   * @file           : app.py
#   * @brief          : ANALISIS DE SEDIMETOS URINARIOS USANDO VISION POR COMPUTADORA
#   * 
#   * @author			: Angel Juarez Monroy & Hadali Miliani Montero Aguilar
#   * @date			: apr 16, 2026
#   ******************************************************************************



import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import shutil
import subprocess
import sys
import io
import threading
import traceback
from datetime import datetime
from pathlib import Path
from PIL import Image as PILImage, ImageTk
from reportlab.lib.pagesizes import letter

torch = None
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, BaseDocTemplate, PageTemplate, Frame
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader

# Intentar importar PyMuPDF para la previsualización
try:
    import fitz
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# RUTA DEL ESCRITORIO PARA ARCHIVOS GENERADOS
# Soporta usuarios en inglés y español.
def get_desktop_path():
    home = Path.home()
    candidates = ["Desktop", "Escritorio"]
    for name in candidates:
        desktop_candidate = home / name
        if desktop_candidate.exists() and desktop_candidate.is_dir():
            return str(desktop_candidate)
    return str(home)

desktop_path = get_desktop_path()

def desktop_file(filename):
    return os.path.join(desktop_path, filename)

def log_error(exc):
    try:
        with open(desktop_file("error_log.txt"), "a", encoding="utf-8") as f:
            f.write(str(exc))
            f.write("\n")
            f.write(traceback.format_exc())
            f.write("\n\n")
    except Exception:
        pass

# -----------------------------
# CONFIGURACIÓN YOLO
# -----------------------------
class_names = ["cast","cryst", "epith", "epithn", "eryth","leuko", "mycete"]
DISPLAY_NAMES = {
    "cast": "Cilindros",
    "cryst": "Oxalato de Calcio",
    "epith": "Células uretrales superficiales",
    "epithn": "Células uretrales intermedias",
    "eryth": "Eritrocitos",
    "leuko": "Leucocitos",
    "mycete": "Levaduras"
}
COLOR_MAP = {
"cast":   "#ff7f00",   # naranja intenso
"cryst":  "#ffd60a",   # amarillo brillante
"epith":  "#00d4ff",   # cian eléctrico
"epithn": "#ff00aa",   # magenta fuerte
"eryth":  "#ff0000",   # rojo (SIN CAMBIO)
"leuko":  "#0066ff",   # azul brillante (SIN CAMBIO)
"mycete": "#00ff66"    # verde neón   
}


def load_yolo_names(weights_path=None):
    """Carga el orden de clases real desde el archivo de pesos YOLO."""
    if torch is None:
        return class_names

    if weights_path is None:
        weights_path = resource_path("weights/best.pt")

    try:
        model_data = torch.load(weights_path, map_location="cpu")
        model = model_data.get("model") if isinstance(model_data, dict) else model_data
        names = getattr(model, "names", None)
        if isinstance(names, (list, tuple)):
            return list(names)
        if isinstance(names, dict):
            return [names[i] for i in sorted(names)]
    except Exception:
        pass

    return class_names

MODEL_CLASS_NAMES = load_yolo_names()

styles = getSampleStyleSheet()
cell_style = styles["Normal"]
cell_right_bold_style = ParagraphStyle(
    'CellRightBold',
    parent=styles['Normal'],
    fontName='Helvetica-Bold',
    alignment=TA_RIGHT,
    leading=14,
)

def format_param_pdf(text):
    multiline_targets = {
        "CÉLULAS TUBULARES RENALES": "CÉLULAS TUBULARES<br/>RENALES",
        "CÉLULAS UROTELIALES SUPERFICIALES": "CÉLULAS UROTELIALES<br/>SUPERFICIALES",
        "CÉLULAS UROTELIALES INTERMEDIAS": "CÉLULAS UROTELIALES<br/>INTERMEDIAS",
        "CÉLULAS UROTELIALES BASALES": "CÉLULAS UROTELIALES<br/>BASALES",
        "CÉLULAS URETRALES SUPERFICIALES": "CÉLULAS URETRALES<br/>SUPERFICIALES",
        "CÉLULAS URETRALES INTERMEDIAS": "CÉLULAS URETRALES<br/>INTERMEDIAS",
        "CÉLULAS URETRALES BASALES": "CÉLULAS URETRALES<br/>BASALES",
    }

    if text == "FOSFATO AMÓNICO MAGNÉSICO":
        return format_fosfato_amonico_magnesico()

    if text in multiline_targets:
        return Paragraph(multiline_targets[text], cell_right_bold_style)

    return text

fosfato_style = ParagraphStyle(
    "fosfato_style",
    fontName="Helvetica-Bold",
    fontSize=10,
    alignment=TA_RIGHT,
    leading=12
)

def format_fosfato_amonico_magnesico():
    return Paragraph(
        "<para alignment='right'><b>"
        "FOSFATO AMÓNICO MAGNÉSICO<br/>"
        "(FOSFATO TRIPLE)"
        "</b></para>",
        fosfato_style
    )

# -----------------------------
# PARÁMETROS DE LAS TABLAS MANUALES
# -----------------------------
# Examen Físico
FISICO_PARAMS = [
    {"param": "ASPECTO", "options": ["TRANSPARENTE", "LIGERAMENTE TURBIA", "TURBIA"], "ref": "TRANSPARENTE"},
    {"param": "COLOR", "options": ["INCOLORO", "AMA-PALIDO", "AMARILLO", "AMA-OSCURO", "AMBAR", "ANARANJADO", "AZUL-VERDE", "ROJIZA", "NEGRO", "OTRO"], "ref": "AMARILLO"},
    {"param": "OLOR", "options": ["SUI-GENERIS", "FRUTAL", "MEDICAMENTO", "FETIDO", "OTRO"], "ref": "SUI-GÉNERIS"},
    {"param": "ESPUMA", "options": ["AUSENTE", "ESCASA (+)", "MODERADA (++)", "ABUNDANTE (+++)"], "ref": "AUSENTE"},
    {"param": "SEDIMENTO", "options": ["AUSENTE", "ESCASO (+)", "MODERADO (++)", "ABUNDANTE (+++)"], "ref": "AUSENTE"},
    {"param": "DENSIDAD", "options": None, "ref": "1.018 - 1.025"}
]

# Examen Químico
QUIMICO_PARAMS = [
    {"param": "PH", "options": ["1.0", "2.0", "3.0", "4.0", "5.0", "6.0", "7.0", "8.0", "9.0", "10.0", "11.0", "12.0", "13.0", "14.0"], "ref": "5.0 - 7.0"},
    {"param": "LEUCOCITOS (TIRA)", "options": ["NEGATIVO", "10-25(+)", "~75(++)", "~500(+++)"], "ref": "NEGATIVO (MENOR A 10 Leu/µL)"},
    {"param": "NITRITOS", "options": ["NEGATIVO", "POSITIVO"], "ref": "NEGATIVO"},
    {"param": "PROTEÍNAS", "options": ["NEGATIVO", "30(+)" , "100(++)", "500(+++)"], "ref": "NEGATIVO (MENOR A 10 mg/dL)"},
    {"param": "GLUCOSA", "options": ["NEGATIVO", "NORMAL", "50(+)", "100(++)", "300(+++)", "1000(++++)"], "ref": "NORMAL (MENOR A 30 mg/dL)"},
    {"param": "CETONAS", "options": ["NEGATIVO", "POSITIVO"], "ref": "NEGATIVO (MENOR A 5 mg/dL)"},
    {"param": "UROBILINÓGENO", "options": ["NORMAL", "1(+)", "4(++)", "8(+++)"], "ref": "NORMAL (MENOR A 1 mg/dL)"},
    {"param": "BILIRRUBINA", "options": ["NEGATIVO", "1(+)" , "3(++)", "6(+++)"], "ref": "NEGATIVO (MENOR A 0.2 mg/dL)"},
    {"param": "ERITROCITOS", "options": ["NEGATIVO", "10(+)", "~25(++)", "~50(+++)", "~250(++++)"], "ref": "NEGATIVO (MENOR A 0-5 Ery/µL)"},
    {"param": "HEMOGLOBINA", "options": ["NEGATIVO", "10(+)", "~25(++)", "~50(+++)", "~250(++++)"], "ref": "NEGATIVO (MENOR A 0-5 Ery/µL)"}
]

# Celularidad
CELULARIDAD_PARAMS = [
    {"param": "LEUCOCITOS", "auto": True, "ref": "0-5 x C"},
    {"param": "ERITROCITOS", "auto": True, "ref": "0-5 x C"},
    {"param": "LEVADURAS", "auto": True, "ref": "AUSENTES"},
    {"param": "CILINDROS", "auto": True, "ref": "AUSENTES"},
    {"param": "BACTERIAS", "options": ["AUSENTES", "ESCASAS (+)", "MODERADAS (++)", "ABUNDANTES (+++)"], "ref": "AUSENTES"},
    {"param": "CÉLULAS TUBULARES RENALES", "options": ["AUSENTES", "ESCASAS (+)", "MODERADAS (++)", "ABUNDANTES (+++)"], "ref": "PATOLÓGICA"},
    {"param": "CÉLULAS UROTELIALES SUPERFICIALES", "options": ["AUSENTES", "ESCASAS (+)", "MODERADAS (++)", "ABUNDANTES (+++)"], "ref": "PATOLÓGICA"},
    {"param": "CÉLULAS UROTELIALES INTERMEDIAS", "options": ["AUSENTES", "ESCASAS (+)", "MODERADAS (++)", "ABUNDANTES (+++)"], "ref": "PATOLÓGICA"},
    {"param": "CÉLULAS UROTELIALES BASALES", "options": ["AUSENTES", "ESCASAS (+)", "MODERADAS (++)", "ABUNDANTES (+++)"], "ref": "PATOLÓGICA"},
    {"param": "CÉLULAS URETRALES SUPERFICIALES", "auto": True, "ref": "NORMAL"},
    {"param": "CÉLULAS URETRALES INTERMEDIAS", "auto": True, "ref": "NORMAL"},
    {"param": "CÉLULAS URETRALES BASALES", "options": ["AUSENTES", "ESCASAS (+)", "MODERADAS (++)", "ABUNDANTES (+++)"], "ref": "NORMAL"}
]

# Cristaluria
CRISTALURIA_PARAMS = [
    {"param": "URATO AMORFO", "options": ["AUSENTES", "ESCASOS (+)", "MODERADOS (++)", "ABUNDANTES (+++)"], "ref": "NORMAL EN ORINA ÁCIDA"},
    {"param": "ÁCIDO ÚRICO", "options": ["AUSENTES", "ESCASOS (+)", "MODERADOS (++)", "ABUNDANTES (+++)"], "ref": "NORMAL EN ORINA ÁCIDA"},
    {"param": "OXALATO DE CALCIO", "auto": True, "ref": "NORMAL EN ORINA ÁCIDA / NEUTRA"},
    {"param": "FOSFATO AMORFO", "options": ["AUSENTES", "ESCASOS (+)", "MODERADOS (++)", "ABUNDANTES (+++)"], "ref": "NORMAL EN ORINA ALCALINA / NEUTRA"},
    {"param": "FOSFATO DE CALCIO", "options": ["AUSENTES", "ESCASOS (+)", "MODERADOS (++)", "ABUNDANTES (+++)"], "ref": "NORMAL EN ORINA ALCALINA / NEUTRA"},
    {"param": "FOSFATO AMÓNICO MAGNÉSICO", "options": ["AUSENTES", "ESCASOS (+)", "MODERADOS (++)", "ABUNDANTES (+++)"], "ref": "NORMAL EN ORINA ALCALINA"},
    {"param": "BIURATO DE AMONIO", "options": ["AUSENTES", "ESCASOS (+)", "MODERADOS (++)", "ABUNDANTES (+++)"], "ref": "NORMAL EN ORINA ALCALINA"},
    {"param": "CARBONATO DE CALCIO", "options": ["AUSENTES", "ESCASOS (+)", "MODERADOS (++)", "ABUNDANTES (+++)"], "ref": "NORMAL EN ORINA ALCALINA"},
    {"param": "CISTINA", "options": ["AUSENTES", "ESCASAS (+)", "MODERADAS (++)", "ABUNDANTES (+++)"], "ref": "ANORMAL EN ORINA ÁCIDA"},
    {"param": "COLESTEROL", "options": ["AUSENTES", "ESCASOS (+)", "MODERADOS (++)", "ABUNDANTES (+++)"], "ref": "ANORMAL EN ORINA ÁCIDA"},
    {"param": "BILIRRUBINA", "options": ["AUSENTES", "ESCASAS (+)", "MODERADAS (++)", "ABUNDANTES (+++)"], "ref": "ANORMAL EN ORINA ÁCIDA"},
    {"param": "LEUCINA", "options": ["AUSENTES", "ESCASAS (+)", "MODERADAS (++)", "ABUNDANTES (+++)"], "ref": "ANORMAL EN ORINA ÁCIDA / NEUTRA"},
    {"param": "TIROSINA", "options": ["AUSENTES", "ESCASAS (+)", "MODERADAS (++)", "ABUNDANTES (+++)"], "ref": "ANORMAL EN ORINA ÁCIDA / NEUTRA"},
    {"param": "SULFONAMIDA", "options": ["AUSENTES", "ESCASAS (+)", "MODERADAS (++)", "ABUNDANTES (+++)"], "ref": "ANORMAL EN ORINA ÁCIDA / NEUTRA"},
    {"param": "AMPICILINA", "options": ["AUSENTES", "ESCASAS (+)", "MODERADAS (++)", "ABUNDANTES (+++)"], "ref": "ANORMAL EN ORINA ÁCIDA / NEUTRA"}
]

def levadura_qualitative(count):
    """Clasifica las levaduras según cantidad detectada.
    Ausentes: 0 | Escasas (+): 1-5 | Moderadas (++): 6-10 | Abundantes (+++): >10
    """
    if count == 0:
        return "AUSENTES"
    elif 1 <= count <= 5:
        return f"ESCASAS (+)"
    elif 6 <= count <= 10:
        return f"MODERADAS (++)"
    else:
        return f"ABUNDANTES (+++)"

def celula_qualitative(count):
    """Clasifica las células epith y epithn según cantidad detectada.
    Ausentes = 0 células	
    Escasas (+) = 1 – 5 células 
    Moderadas (++) = 6 – 10 células 
    Abundantes (+++) = 11 – 20 Y MAS células 
    """
    if count == 0:
        return "AUSENTES"
    elif 1 <= count <= 5:
        return "ESCASAS (+)"
    elif 6 <= count <= 10:
        return "MODERADAS (++)"
    else:
        return "ABUNDANTES (+++)"


def cristal_qualitative(count):
    """Clasifica los cristales (cryst) según cantidad detectada.
    Ausentes: 0 cristales
    Escasos (+): 1 – 5 cristales
    Moderados (++): 6 – 10 cristales
    Abundantes (+++): 11 – 20 cristales EN ADELANTE
    """
    if count == 0:
        return "AUSENTES"
    elif 1 <= count <= 5:
        return "ESCASOS (+)"
    elif 6 <= count <= 10:
        return "MODERADOS (++)"
    else:
        return "ABUNDANTES (+++)"


def cilindro_qualitative(count):
    """Clasifica los cilindros (cast) según cantidad detectada.
    Ausentes: 0 cilindros
    Escasos (+): 1 – 2 cilindros
    Moderados (++): 3 – 5 cilindros
    Abundantes (+++): 6 – 10 cilindros EN ADELANTE
    """
    if count == 0:
        return "AUSENTES"
    elif 1 <= count <= 2:
        return "ESCASOS (+)"
    elif 3 <= count <= 5:
        return "MODERADOS (++)"
    else:
        return "ABUNDANTES (+++)"

#SISTEMA DE CARGA (SPLASH SCREEN)
# 1. VENTANA DE CARGA
def mostrar_carga(root):
    """Crea y muestra la ventana splash de carga."""
    splash = tk.Toplevel(root)
    splash.overrideredirect(True)  # sin bordes
    splash.attributes('-topmost', True)  # siempre arriba

    width = 300
    height = 120

    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)

    splash.geometry(f"{width}x{height}+{x}+{y}")
    splash.configure(bg="#2563eb")

    label = tk.Label(splash, text="Cargando...", fg="white", bg="#2563eb", font=("Arial", 12, "bold"))
    label.pack(pady=15)

    progress = ttk.Progressbar(splash, mode="indeterminate", length=250)
    progress.pack(pady=10, padx=20, fill="x")

    progress.start(10)
    return splash

#CARGAR MODELO EN SEGUNDO PLANO (SIN CONGELAR)
def cargar_sistema(app, splash):
    try:
        # 1. Cargar modelo (pesado)
        app.load_model()
    except Exception as e:
        # print(f"Error cargando modelo: {e}")  #ELIMINADO: Silenciar consola
        pass  #Silenciar errores de carga también

    #2. Finalizar carga en el hilo principal cuando la UI esté idle
    app.root.after_idle(lambda: finalizar_carga(app, splash))

# 3. INICIAR EN SEGUNDO PLANO
def iniciar_carga_asincronico(app, splash):
    """Inicia la carga en un hilo daemon para no bloquear la UI."""
    hilo = threading.Thread(target=cargar_sistema, args=(app, splash), daemon=True)
    hilo.start()

#FINALIZAR CARGA
def finalizar_carga(app, splash):
    #Construir TODA la UI antes de mostrarla
    if not app.analysis_frame:
        app.build_analysis_ui()

    #Forzar render completo antes de exponer la ventana
    app.root.update_idletasks()

    #Crear pantalla de inicio y mostrar la app ya lista
    app.create_start_screen()
    splash.destroy()
    app.mostrar_interfaz()

# -----------------------------
# FUNCIONES AUXILIARES
# -----------------------------
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_image_tk(path, width=1024, height=768):
    """Optimizado: INTER_AREA para mejor rendimiento y calidad."""
    import cv2
    img = cv2.imread(path)
    if img is None:
        return None
    #INTER_AREA: 50% más rápido que default + mejor calidad en downsampling
    img = cv2.resize(img, (width, height), interpolation=cv2.INTER_AREA)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = PILImage.fromarray(img)
    return ImageTk.PhotoImage(img)

def save_patient_data(data):
    with open(os.path.join(desktop_path, "paciente.json"), "w") as f:
        json.dump(data, f)

def load_patient_data():
    paciente_path = os.path.join(desktop_path, "paciente.json")
    if os.path.exists(paciente_path):
        with open(paciente_path, "r") as f:
            return json.load(f)
    return {}

# -----------------------------
# CLASE PRINCIPAL
# -----------------------------
def scale_content(canvas, doc):
    canvas.saveState()

    scale = 0.8
    width, height = doc.pagesize


    y_move = 60   

    # Luego escala
    canvas.translate(0, -y_move)  # negativo = baja contenido
    canvas.scale(scale, scale)

    # Centrado después del scale
    x_offset = (width * (1 - scale)) / 2
    y_offset = (height * (1 - scale)) / 2

    canvas.translate(x_offset / scale, y_offset / scale)

def restore_canvas(canvas, doc):
    canvas.restoreState()

class BackgroundPageTemplate(PageTemplate):
    def __init__(self, id, frames, background_path):
        super().__init__(id=id, frames=frames)
        self.background_path = background_path
    def beforeDrawPage(self, canvas, doc):
        if os.path.exists(self.background_path):
            width, height = doc.pagesize
            canvas.drawImage(self.background_path, 0, 0, width=width, height=height)
            # print("FONDO OK")  

class AnalizadorSedimento:
    def __init__(self, root):
        self.root = root
        self.root.title("Sistema de Uruanálisis")

        self.root.withdraw()
        self.root.configure(bg="#f1f5f9")

        # Estado
        self.selected_image = None
        self.cap = None
        self.camera_running = False
        self.last_result_image = None
        self.last_counts = {}
        self.patient_data = load_patient_data()
        self.exp_counter = 0

        # Variables de entrada para pestaña datos
        self.nombre_var = tk.StringVar(value=self.patient_data.get("nombre", ""))
        self.apellidos_var = tk.StringVar(value=self.patient_data.get("apellidos", ""))
        self.edad_var = tk.StringVar(value=self.patient_data.get("edad", ""))
        self.sexo_var = tk.StringVar(value=self.patient_data.get("sexo", ""))
        self.folio_var = tk.StringVar(value=self.patient_data.get("folio", ""))
        self.fecha_var = tk.StringVar(value=self.patient_data.get("fecha", datetime.now().strftime("%d / %m / %Y")))
        self.elaboro_var = tk.StringVar(value=self.patient_data.get("elaboro", ""))

        # Diccionarios para almacenar las variables de los comboboxes
        self.fisico_vars = {}
        self.quimico_vars = {}
        self.celularidad_vars = {}
        self.cristaluria_vars = {}

        # Variables para valores automáticos (YOLO)
        self.leuko_var = tk.StringVar(value="")
        self.eryth_var = tk.StringVar(value="")
        self.levadura_var = tk.StringVar(value="AUSENTES")
        self.epith_var = tk.StringVar(value="AUSENTES")
        self.epithn_var = tk.StringVar(value="AUSENTES")
        self.cryst_var = tk.StringVar(value="AUSENTES")
        self.cast_var = tk.StringVar(value="AUSENTES")

        # Flag para controlar transiciones y evitar múltiples llamadas
        self.transitioning = False
        self.start_frame = None
        self.analysis_frame = None
        self.current_screen = "inicio"
        self.tabla_creada = False
        

        self.image_cache = {}
        

        self.bg_image = None
        self.bg_photo = None
        

        self.model = None
        self.device = None
        self.stride = None
        self.imgsz = None
        self.names = None
        self.colors = None

        self.setup_style()


        self.root.bind_all("<Escape>", self.handle_escape)
    
    #MOSTRAR INTERFAZ DESPUÉS DE CARGAR
    def mostrar_interfaz(self):
        """Muestra la ventana principal cuando el sistema está listo."""
        if not self.start_frame:
            self.create_start_screen()
        self.root.state('zoomed')  # Pantalla completa (maximizada)
        self.root.deiconify()  # Mostrar ventana

    #1. LOAD MODEL (PRO)
    def load_model(self):
        import sys
        import os
        import torch
        import warnings
        
        #Silenciar warnings de PyTorch/YOLO (solo ruido de consola)
        warnings.filterwarnings("ignore")

        #Asegurar que yolov7 sea importable tanto en desarrollo como dentro del EXE
        yolo_path = resource_path("yolov7")
        if not os.path.isdir(yolo_path):
            yolo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yolov7")
        if yolo_path not in sys.path:
            sys.path.insert(0, yolo_path)

        from models.experimental import attempt_load
        from utils.torch_utils import select_device
        from utils.general import check_img_size

        torch.set_grad_enabled(False)
        torch.set_num_threads(1)  #CPU optimizado para arranque más ligero
        torch.set_num_interop_threads(1)
        torch.backends.cudnn.benchmark = False

        self.device = select_device('cpu')

        #Silenciar stdout durante carga (elimina "Fusing layers..." y "RepConv.fuse_repvgg_block")
        from contextlib import redirect_stdout, redirect_stderr
        with redirect_stdout(open(os.devnull, 'w')), redirect_stderr(open(os.devnull, 'w')):
            self.model = attempt_load(resource_path("weights/best.pt"), map_location=self.device)
        self.model.eval()
        self.model.float()

        self.stride = int(self.model.stride.max())
        self.imgsz = check_img_size(1024, s=self.stride)  

        self.names = self.model.module.names if hasattr(self.model, "module") else self.model.names


        self.colors = {
            "cast":   (0, 127, 255),
            "cryst":  (10, 214, 255),
            "epith":  (255, 212, 0),
            "epithn": (170, 0, 255),
            "eryth":  (0, 0, 255),
            "leuko":  (255, 102, 0),
            "mycete": (102, 255, 0)
        }

    def setup_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background="#f1f5f9", borderwidth=0)
        style.configure("TNotebook.Tab", background="#e2e8f0", padding=[12, 6], font=('Segoe UI', 11))
        style.map("TNotebook.Tab", background=[("selected", "#ffffff")])
        style.configure("TFrame", background="#f1f5f9")
        style.configure("TLabelframe", background="#ffffff", relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background="#ffffff", font=('Segoe UI', 12, 'bold'))

    def load_background(self):
        """Carga la imagen de fondo general de forma perezosa."""
        if self.bg_photo is not None:
            return
        try:
            img = PILImage.open(resource_path("assets/BBACKGROUND.png"))
            img = img.resize((1600, 800), PILImage.BILINEAR)
            self.bg_photo = ImageTk.PhotoImage(img)
        except Exception as e:
            # print(f"Error cargando fondo general: {e}")  
            self.bg_photo = None

    def set_background(self, container, image_path):
        """Establece una imagen de fondo optimizada (redimensionado eficiente con caché)."""
        if not os.path.exists(image_path):
            # print(f"Advertencia: No se encontró la imagen {image_path}")  
            return

        # Cargar la imagen original una sola vez
        original_img = PILImage.open(image_path)
        
  
        resize_cache = {'last_size': None, 'last_photo': None, 'pending': None}

        def resize_background(event=None):
  
            if resize_cache['pending']:
                container.after_cancel(resize_cache['pending'])

            resize_cache['pending'] = container.after(100, lambda: _do_resize())

        def _do_resize():
            w = container.winfo_width()
            h = container.winfo_height()
            

            if (w, h) == resize_cache['last_size'] or w <= 1 or h <= 1:
                resize_cache['pending'] = None
                return
            
            resize_cache['last_size'] = (w, h)
            
            # Redimensionar usando BILINEAR (más rápido que LANCZOS)
            img_resized = original_img.resize((w, h), PILImage.Resampling.BILINEAR)
            bg_photo = ImageTk.PhotoImage(img_resized)
            

            self.bg_label.config(image=bg_photo)
            self.bg_label.image = bg_photo  # mantener referencia
            resize_cache['last_photo'] = bg_photo
            resize_cache['pending'] = None

        self.bg_label = tk.Label(container)
        self.bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        self.bg_label.lower()

        container.bind('<Configure>', resize_background)
        # Forzar primera redimensión
        container.update_idletasks()
        _do_resize()

    def create_start_screen(self):
        # Destruir frame anterior si existe
        if self.start_frame:
            self.start_frame.destroy()
        if self.analysis_frame:
            self.analysis_frame.place_forget()
            
        self.start_frame = tk.Frame(self.root)
        self.start_frame.place(relwidth=1, relheight=1)

        # Fondo (tu imagen)
        self.set_background(self.start_frame, resource_path("assets/INICIOLOBBY.png"))

        btn_frame = tk.Frame(self.start_frame, bg="#2563eb", bd=0, relief="flat")
        btn_frame.place(relx=0.5, rely=0.6, anchor="center")

        # Botón Iniciar análisis
        canvas_start = tk.Canvas(btn_frame, width=250, height=48, bg="#2563eb", bd=0,
                         highlightthickness=0, highlightbackground="#2563eb",
                         relief="flat", cursor="hand2", takefocus=False)
        canvas_start.create_text(125, 24, text="▶ Iniciar análisis", fill="white",
                         font=("Segoe UI", 16, "bold"), anchor="center")
        canvas_start.bind("<Button-1>", lambda e: self.start_analysis())
        canvas_start.pack(pady=8)
        
        self.start_frame.focus_set()

        self.current_screen = "inicio"





    def start_analysis(self):
        if self.transitioning or not self.analysis_frame:
            return
        self.transitioning = True
        self.root.after(1, self._start_analysis_real)

    def _start_analysis_real(self):
        self.start_frame.place_forget()
        self.analysis_frame.place(relwidth=1, relheight=1)
        self.current_screen = "analisis"
        self.transitioning = False

    def show_config(self):
        messagebox.showinfo("Configuración", "Umbral de confianza, selección de cámara, etc. (por implementar)")

    def show_help(self):
        messagebox.showinfo("Ayuda",
            "Ayuda:\n"
            "1. Complete datos del paciente.\n"
            "2. Cargue imagen desde cámara o galería.\n"
            "3. Presione Analizar.\n"
            "4. Revise detecciones y tabla.\n"
            "5. Genere PDF.")

    def build_analysis_ui(self):
        self.load_background()
        self.analysis_frame = tk.Frame(self.root, bg="#f1f5f9")
        self.notebook = ttk.Notebook(self.analysis_frame)
        self.notebook.enable_traversal()
        

        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)
        
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_datos = tk.Frame(self.notebook, bg="#ffffff")
        self.notebook.add(self.tab_datos, text="📋 Captura de datos")
        self.create_datos_tab()

        self.tab_muestra = tk.Frame(self.notebook, bg="#ffffff")
        self.notebook.add(self.tab_muestra, text="🖼 Carga de muestra")
        self.create_muestra_tab()
        self.notebook.tab(self.tab_muestra, state="disabled")

        self.tab_detecciones = tk.Frame(self.notebook, bg="#ffffff")
        self.notebook.add(self.tab_detecciones, text="🔍 Detecciones")
        self.create_detecciones_tab()
        self.notebook.tab(self.tab_detecciones, state="disabled")

        self.tab_tabla = tk.Frame(self.notebook, bg="#ffffff")
        self.notebook.add(self.tab_tabla, text="📊 Resultados")

        # self.create_tabla_tab()  # ← ELIMINADO: Causa doble render
        self.notebook.tab(self.tab_tabla, state="disabled")

        self.tab_imprimir = tk.Frame(self.notebook, bg="#ffffff")
        self.notebook.add(self.tab_imprimir, text="🖨 Imprimir")
        self.create_imprimir_tab()
        self.notebook.tab(self.tab_imprimir, state="disabled")

        bottom_frame = tk.Frame(self.analysis_frame, bg="#f1f5f9")
        bottom_frame.pack(side="bottom", fill="x", pady=10)

        # Bind Escape en el analysis_frame para asegurar que siempre funciona
        self.analysis_frame.bind("<Escape>", lambda e: self.salir())
        self.analysis_frame.focus_set()
        
        # Resetear flag de transición
        self.transitioning = False

        self.cargar_datos_paciente()
        self.verificar_bloqueos()

    def on_tab_change(self, event=None):

            current_tab = self.notebook.index(self.notebook.select())
            # Índice de tab_tabla (contando desde 0: datos=0, muestra=1, detecciones=2, tabla=3)
            if current_tab == 3 and not self.tabla_creada:
                self._build_tabla_tab_lazy()
        except:
            pass

    def create_analysis_ui(self):
        if self.analysis_frame:
            self.analysis_frame.pack(fill="both", expand=True, padx=10, pady=10)

    def cerrar_programa(self):
        if messagebox.askyesno("Salir", "¿Está seguro de que desea cerrar el programa?"):
            self._limpiar_archivos_temporales()
            self.root.quit()

    def _limpiar_archivos_temporales(self):
        """Limpia archivos temporales generados durante la ejecución."""
        import os
        archivos_a_limpiar = [
            os.path.join(desktop_path, "resultado.jpg"),
            os.path.join(desktop_path, "captura_microscopio.jpg"),
            os.path.join(desktop_path, "stats.json"),
            os.path.join(desktop_path, "paciente.json")
        ]
        for archivo in archivos_a_limpiar:
            try:
                if os.path.exists(archivo):
                    os.remove(archivo)
            except Exception:
                pass  # Silenciar errores de limpieza

    def salir(self, *args):
        # Evitar múltiples llamadas rápidas durante la transición
        if self.transitioning:
            return
        
        self.transitioning = True
        
        if self.analysis_frame:
            self.analysis_frame.pack_forget()
            self.analysis_frame.unbind("<Escape>")
        if self.cap:
            self.cap.release()
        
        # Crear pantalla de inicio
        self.create_start_screen()
        
        self.current_screen = "inicio"
        
        # Resetear flag después de un pequeño delay
        self.root.after(100, lambda: setattr(self, 'transitioning', False))

    def handle_escape(self, event=None):
        if self.current_screen != "inicio":
            self.ir_a_inicio()
        else:
            self.confirmar_salida()

    def ir_a_inicio(self):
        self.salir()

    def confirmar_salida(self):
        respuesta = messagebox.askyesno(
            "Salir",
            "¿Deseas cerrar el programa?"
        )
        if respuesta:
            self._limpiar_archivos_temporales()
            self.root.destroy()

    def cargar_datos_paciente(self):
        self.nombre_var.set(self.patient_data.get("nombre", ""))
        self.apellidos_var.set(self.patient_data.get("apellidos", ""))
        self.edad_var.set(self.patient_data.get("edad", ""))
        self.sexo_var.set(self.patient_data.get("sexo", ""))
        self.folio_var.set(self.patient_data.get("folio", ""))
        self.fecha_var.set(self.patient_data.get("fecha", datetime.now().strftime("%d / %m / %Y")))
        self.elaboro_var.set(self.patient_data.get("elaboro", ""))

    def guardar_datos_paciente(self):
        data = {
            "nombre": self.nombre_var.get(),
            "apellidos": self.apellidos_var.get(),
            "edad": self.edad_var.get(),
            "sexo": self.sexo_var.get(),
            "folio": self.folio_var.get(),
            "fecha": self.fecha_var.get(),
            "elaboro": self.elaboro_var.get()
        }
        save_patient_data(data)
        self.patient_data = data
        messagebox.showinfo("Guardado", "Datos del paciente guardados.")
        self.verificar_bloqueos()
        if self.notebook.tab(self.tab_muestra, "state") == "normal":
            self.notebook.select(self.tab_muestra)

    def limpiar_datos(self):
        self.nombre_var.set("")
        self.apellidos_var.set("")
        self.edad_var.set("")
        self.sexo_var.set("")
        self.folio_var.set("")
        self.fecha_var.set(datetime.now().strftime("%d / %m / %Y"))
        self.elaboro_var.set("")
        save_patient_data({})
        self.patient_data = {}
        messagebox.showinfo("Limpieza", "Datos del paciente borrados.")
        self.verificar_bloqueos()

    def verificar_bloqueos(self):
        nombre_ok = bool(self.nombre_var.get().strip())
        folio_ok = bool(self.folio_var.get().strip())
        if nombre_ok and folio_ok:
            self.notebook.tab(self.tab_muestra, state="normal")
        else:
            self.notebook.tab(self.tab_muestra, state="disabled")
            self.notebook.tab(self.tab_detecciones, state="disabled")
            self.notebook.tab(self.tab_tabla, state="disabled")
            self.notebook.tab(self.tab_imprimir, state="disabled")
            return

        if self.last_result_image and self.last_counts:
            self.notebook.tab(self.tab_detecciones, state="normal")
            self.notebook.tab(self.tab_tabla, state="normal")
            # Imprimir solo se habilita cuando se guarden los resultados
            self.notebook.tab(self.tab_imprimir, state="disabled")
        else:
            self.notebook.tab(self.tab_detecciones, state="disabled")
            self.notebook.tab(self.tab_tabla, state="disabled")
            self.notebook.tab(self.tab_imprimir, state="disabled")

    # -----------------------------
    # PESTAÑA DATOS
    # -----------------------------
    def create_datos_tab(self):
        frame = self.tab_datos
        frame.configure(bg="#ffffff")

        # Configurar columnas para que se expandan al ancho completo
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)
        frame.columnconfigure(3, weight=1)
        frame.columnconfigure(4, weight=1)

        # Imagen de fondo que abarca toda la pestaña (optimizada)
        bg_label = tk.Label(frame, image=self.bg_photo)
        bg_label.place(x=0, y=0, relwidth=1, relheight=1)

        tk.Label(frame, text="Datos del paciente", font=("Segoe UI", 16, "bold"),
                 bg="#ffffff", fg="#0f172a").grid(row=0, column=0, columnspan=2, pady=20)

        fields = [
            ("Nombre:", self.nombre_var, 1, 0),
            ("Apellidos:", self.apellidos_var, 2, 0),
            ("Edad:", self.edad_var, 3, 0),
            ("Género:", self.sexo_var, 4, 0),
            ("Folio laboratorio:", self.folio_var, 5, 0),
            ("Fecha:", self.fecha_var, 6, 0),
            ("Realizó:", self.elaboro_var, 7, 0)
        ]

        for label, var, row, col in fields:
            tk.Label(frame, text=label, font=("Segoe UI", 12), bg="#ffffff",
                     anchor="e", width=18).grid(row=row, column=col, sticky="e", padx=10, pady=8)
            if label == "Género:":
                combo = ttk.Combobox(frame, textvariable=var, values=["FEMENINO", "MASCULINO", "OTRO"],
                                     font=("Segoe UI", 12), width=25)
                combo.grid(row=row, column=col+1, padx=10, pady=8)
            else:
                entry = tk.Entry(frame, textvariable=var, font=("Segoe UI", 12), width=28, relief="solid", bd=1)
                entry.grid(row=row, column=col+1, padx=10, pady=8)

        btn_frame = tk.Frame(frame, bg="#ffffff")
        btn_frame.grid(row=8, column=0, columnspan=2, pady=20)
        tk.Button(btn_frame, text="💾 Guardar ficha", command=self.guardar_datos_paciente,
                  bg="#2563eb", fg="white", font=("Segoe UI", 12, "bold"), padx=15, pady=5,
                  relief="flat", bd=0).pack(side="left", padx=10)
        tk.Button(btn_frame, text="🗑 Limpiar", command=self.limpiar_datos,
                  bg="#e2e8f0", fg="#1e293b", font=("Segoe UI", 12, "bold"), padx=15, pady=5,
                  relief="flat", bd=0).pack(side="left", padx=10)

        # Imagen al lado derecho
        try:
            img = PILImage.open(resource_path("assets/medical-report_18526776.png"))
            img = img.resize((300, 300), PILImage.LANCZOS)  # Ajustar tamaño si es necesario
            self.photo_datos = ImageTk.PhotoImage(img)
            img_label = tk.Label(frame, image=self.photo_datos, bg="#ffffff")
            img_label.grid(row=1, column=2, rowspan=7, padx=20, pady=10, sticky="n")
        except Exception as e:
            # print(f"Error cargando imagen: {e}")  # 🔥 ELIMINADO: Silenciar consola
            pass

    # -----------------------------
    # PESTAÑA MUESTRA
    # -----------------------------
    def create_muestra_tab(self):
        frame = self.tab_muestra
        frame.configure(bg="#ffffff")

        # Imagen de fondo (optimizada)
        bg_label = tk.Label(frame, image=self.bg_photo)
        bg_label.place(x=0, y=0, relwidth=1, relheight=1)

        btn_frame = tk.Frame(frame, bg="#ffffff")
        btn_frame.pack(pady=15)

        self.btn_subir = tk.Button(btn_frame, text="📁 Subir imagen", command=self.upload_image,
                  bg="#2563eb", fg="white", font=("Segoe UI", 12, "bold"), padx=15, pady=6,
                  relief="flat", bd=0, cursor="hand2")
        self.btn_subir.pack(side="left", padx=8)
        self.btn_camara = tk.Button(btn_frame, text="📷 Cámara", command=self.start_camera,
                  bg="#2563eb", fg="white", font=("Segoe UI", 12, "bold"), padx=15, pady=6,
                  relief="flat", bd=0, cursor="hand2")
        self.btn_camara.pack(side="left", padx=8)
        self.btn_capturar = tk.Button(btn_frame, text="📸 Capturar", command=self.capture_image,
                  bg="#2563eb", fg="white", font=("Segoe UI", 12, "bold"), padx=15, pady=6,
                  relief="flat", bd=0, cursor="hand2", state="disabled")
        self.btn_capturar.pack(side="left", padx=8)
        self.btn_analizar = tk.Button(btn_frame, text="🔬 Analizar", command=self.analyze_image,
                  bg="#059669", fg="white", font=("Segoe UI", 12, "bold"), padx=15, pady=6,
                  relief="flat", bd=0, cursor="hand2", state="disabled")
        self.btn_analizar.pack(side="left", padx=8)
        self.btn_borrar = tk.Button(btn_frame, text="🗑 Borrar", command=self.clear_image,
                  bg="#dc2626", fg="white", font=("Segoe UI", 12, "bold"), padx=15, pady=6,
                  relief="flat", bd=0, cursor="hand2", state="disabled")
        self.btn_borrar.pack(side="left", padx=8)

        self.preview_label = tk.Label(frame, text="Sin imagen", bg="#e2e8f0", font=("Segoe UI", 12, "bold"),
                                      width=900, height=600, relief="solid", bd=1)
        self.preview_label.pack(pady=15)


        # self.badge_estado = tk.Label(frame, text="Listo", fg="#059669", font=("Segoe UI", 11, "bold"),
        #                              bg="#ffffff")
        # self.badge_estado.pack(pady=5)

        self.spinner_overlay = tk.Label(frame, text="", bg="#10b981", fg="white",
                                        font=("Segoe UI", 16, "bold"), padx=25, pady=15,
                                        bd=0, relief="raised")
        self.spinner_overlay.place(relx=0.5, rely=0.5, anchor="center")
        self.spinner_overlay.place_forget()

        self.spinner_chars = ["⠋", "⠙", "⠚", "⠒", "⠂","⠂", "⠒", "⠚", "⠙", "⠋","⠏", "⠟", "⠿", "⠷", "⠯","⠟", "⠏"]
        self.spinner_index = 0
        self.spinner_job = None
        self.spinner_running = False

    def upload_image(self):
        path = filedialog.askopenfilename()
        if path:
            self.stop_camera()
            self.selected_image = path
            self.show_preview(path)
            # self.badge_estado.config(text="Imagen cargada", fg="#2563eb")
            self.btn_analizar.config(state="normal")
            self.btn_borrar.config(state="normal")
            self.btn_subir.config(state="disabled")
            self.btn_camara.config(state="disabled")

    def start_camera(self):
        import cv2
        if self.cap is not None:
            self.stop_camera()
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            messagebox.showerror("Error", "No se pudo abrir la cámara.")
            return
        self.camera_running = True
        self.btn_capturar.config(state="normal")
        self.show_camera_preview()

    def stop_camera(self):
        if self.cap:
            self.camera_running = False
            self.cap.release()
            self.cap = None
        self.btn_capturar.config(state="disabled")

    def show_camera_preview(self):
        import cv2
        if self.cap and self.camera_running:
            ret, frame = self.cap.read()
            if ret:
                frame = cv2.resize(frame, (900, 600))
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = PILImage.fromarray(frame)
                imgtk = ImageTk.PhotoImage(img)

                if hasattr(self.preview_label, 'imgtk'):
                    del self.preview_label.imgtk
                self.preview_label.imgtk = imgtk
                self.preview_label.config(image=imgtk)
            self.root.after(30, self.show_camera_preview)  

    def capture_image(self):
        import cv2
        if self.cap is None:
            messagebox.showwarning("Sin cámara", "Primero active la cámara con el botón 'Cámara'.")
            return

        ret, frame = self.cap.read()
        if ret:
            path = os.path.join(desktop_path, "captura_microscopio.jpg")
            cv2.imwrite(path, frame)
            self.selected_image = path
            self.show_preview(path)
            if hasattr(self, 'badge_estado'):
                self.badge_estado.config(text="Imagen capturada", fg="#2563eb")
            self.btn_analizar.config(state="normal")
            self.btn_borrar.config(state="normal")
            self.btn_subir.config(state="disabled")
            self.btn_camara.config(state="disabled")
        else:
            messagebox.showerror("Error", "No se pudo capturar la imagen.")

        self.stop_camera()
        self.btn_capturar.config(state="disabled")

    def clear_image(self):
        self.selected_image = None
        self.preview_label.config(image="", text="Sin imagen")
        # self.badge_estado.config(text="Listo", fg="#059669")
        self.last_result_image = None
        self.last_counts = {}

        self.image_cache.clear()
        self.verificar_bloqueos()
        # Stop camera if running
        self.stop_camera()
        # Re-enable input buttons
        self.btn_subir.config(state="normal")
        self.btn_camara.config(state="normal")
        self.btn_analizar.config(state="disabled")
        self.btn_borrar.config(state="disabled")
        # Clear results in other tabs
        self.update_detecciones_tab()
        # Reset table values to first option (not empty)
        for param in FISICO_PARAMS:
            if param["param"] in self.fisico_vars:
                if param.get("options"):
                    self.fisico_vars[param["param"]].set(param["options"][0])
                else:
                    self.fisico_vars[param["param"]].set("")
        for param in QUIMICO_PARAMS:
            if param["param"] in self.quimico_vars:
                if param.get("options"):
                    self.quimico_vars[param["param"]].set(param["options"][0])
                else:
                    self.quimico_vars[param["param"]].set("")
        for param in CRISTALURIA_PARAMS:
            if param["param"] in self.cristaluria_vars:
                if param.get("options"):
                    self.cristaluria_vars[param["param"]].set(param["options"][0])
                else:
                    self.cristaluria_vars[param["param"]].set("")
        for param in CELULARIDAD_PARAMS:
            if param["param"] in self.celularidad_vars:
                if param.get("options"):
                    self.celularidad_vars[param["param"]].set(param["options"][0])
                else:
                    self.celularidad_vars[param["param"]].set("")
        # Reset auto values
        self.leuko_var.set("")
        self.eryth_var.set("")
        self.levadura_var.set("AUSENTES")
        # Clear PDF preview
        for widget in self.preview_scrollable.winfo_children():
            widget.destroy()
        self.preview_images = []

    def show_preview(self, path):

        cache_key = f"{path}_900_600"
        if cache_key not in self.image_cache:
            imgtk = get_image_tk(path, width=900, height=600)
            if imgtk:
                self.image_cache[cache_key] = imgtk
        else:
            imgtk = self.image_cache[cache_key]
        
        if imgtk:

            if hasattr(self.preview_label, 'imgtk'):
                del self.preview_label.imgtk
            self.preview_label.imgtk = imgtk  # Mantener referencia
            self.preview_label.config(image=imgtk, text="")

    def analyze_image(self):
        if not self.selected_image:
            messagebox.showwarning("Sin imagen", "No hay imagen cargada o capturada.")
            return

        # Deshabilitar botones durante análisis
        self.btn_analizar.config(state="disabled", text="🔄 Analizando...")
        self.btn_subir.config(state="disabled")
        self.btn_camara.config(state="disabled")
        self.btn_capturar.config(state="disabled")
        self.btn_borrar.config(state="disabled")


        self.show_spinner_overlay()

        thread = threading.Thread(target=self._run_analysis)
        thread.daemon = True
        thread.start()

    def show_spinner_overlay(self):
        self.spinner_running = True
        self.spinner_index = 0
        self.spinner_overlay.place(relx=0.5, rely=0.5, anchor="center")
        self.spinner_overlay.lift()
        self._animate_spinner()

    def _animate_spinner(self):
        if not self.spinner_running:
            return
        spinner_char = self.spinner_chars[self.spinner_index]
        self.spinner_overlay.config(text=f"{spinner_char} ANALIZANDO {spinner_char}")
        self.spinner_index = (self.spinner_index + 1) % len(self.spinner_chars)
        self.spinner_job = self.root.after(120, self._animate_spinner)

    def hide_spinner_overlay(self):
        self.spinner_running = False
        if self.spinner_job:
            self.root.after_cancel(self.spinner_job)
            self.spinner_job = None
        self.spinner_overlay.place_forget()

    def _run_analysis(self):
        try:
            import torch
            import cv2
            import numpy as np
            import time

            from utils.general import non_max_suppression, scale_coords
            from utils.plots import plot_one_box
            from utils.datasets import letterbox

            t0 = time.time()

            img0 = cv2.imread(self.selected_image)

            if img0 is None:
                raise RuntimeError("No se pudo leer la imagen")

            #PREPROCESAMIENTO CORRECTO (YOLO STYLE)
            img = letterbox(img0, self.imgsz, stride=self.stride)[0]
            img = img[:, :, ::-1].transpose(2, 0, 1)
            img = np.ascontiguousarray(img)

            img = torch.from_numpy(img).to(self.device).float() / 255.0
            img = img.unsqueeze(0)

            #INFERENCIA
            with torch.no_grad():
                pred = self.model(img)[0]

            pred = non_max_suppression(pred, 0.85, 0.80)

            im0 = img0.copy()
            counts = {}

            #POSTPROCESAMIENTO
            for det in pred:
                if len(det):
                    det[:, :4] = scale_coords(img.shape[2:], det[:, :4], im0.shape).round()

                    for *xyxy, conf, cls in det:
                        cls = int(cls)
                        name = self.names[cls]

                        counts[name] = counts.get(name, 0) + 1

                        color = self.colors.get(name, (255, 255, 255))

                        plot_one_box(
                            xyxy,
                            im0,
                            label=f"{name}",
                            color=color,
                            line_thickness=2
                        )

            #GUARDAR RESULTADO
            result_path = os.path.join(desktop_path, "resultado.jpg")
            cv2.imwrite(result_path, im0)

            total_time = time.time() - t0

            self.root.after(0, lambda: self._on_analysis_done(counts, result_path))
        except Exception as e:
            log_error(e)
            self.root.after(0, lambda: self._on_analysis_error(str(e)))

    def _on_analysis_done(self, counts, result_image):
        self.last_counts = counts
        self.last_result_image = result_image

        self.update_auto_values()
        self.update_detecciones_tab()
        self.verificar_bloqueos()
        self.hide_spinner_overlay()
        # self.badge_estado.config(text="ANÁLISIS COMPLETADO", fg="#059669")
        self.notebook.select(self.tab_detecciones)

        # Re-habilitar botones
        self.btn_analizar.config(state="disabled", text="🔬 Analizar")  # Mantener deshabilitado después de análisis
        self.btn_subir.config(state="disabled")
        self.btn_camara.config(state="disabled")
        self.btn_capturar.config(state="disabled")
        self.btn_borrar.config(state="normal")  # Habilitar Borrar para limpiar y cargar otra imagen

    def _on_analysis_error(self, error_msg):
        messagebox.showerror("Error", f"Error al ejecutar YOLOv7: {error_msg}")
        # self.badge_estado.config(text="Error", fg="#dc2626")
        # Re-habilitar botones
        self.btn_analizar.config(state="normal", text="🔬 Analizar")
        self.btn_subir.config(state="normal")
        self.btn_camara.config(state="normal")
        self.btn_capturar.config(state="disabled")
        self.btn_borrar.config(state="normal")
        self.hide_spinner_overlay()

    def update_auto_values(self):
        leuko = self.last_counts.get("leuko", 0)
        eryth = self.last_counts.get("eryth", 0)
        mycete = self.last_counts.get("mycete", 0)
        epith = self.last_counts.get("epith", 0)
        epithn = self.last_counts.get("epithn", 0)
        cryst = self.last_counts.get("cryst", 0)
        cast = self.last_counts.get("cast", 0)
        
        # Si el conteo es 0, mostrar AUSENTES
        leuko_result = "AUSENTES" if leuko == 0 else f"{leuko} X C"
        eryth_result = "AUSENTES" if eryth == 0 else f"{eryth} X C"
        
        self.leuko_var.set(leuko_result)
        self.eryth_var.set(eryth_result)
        self.levadura_var.set(levadura_qualitative(mycete))
        self.epith_var.set(celula_qualitative(epith))
        self.epithn_var.set(celula_qualitative(epithn))
        self.cryst_var.set(cristal_qualitative(cryst))
        self.cast_var.set(cilindro_qualitative(cast))

    # -----------------------------
    # PESTAÑA DETECCIONES
    # -----------------------------
    def create_detecciones_tab(self):
        frame = self.tab_detecciones
        frame.configure(bg="#ffffff")

        # Imagen de fondo (optimizada)
        bg_label = tk.Label(frame, image=self.bg_photo)
        bg_label.place(x=0, y=0, relwidth=1, relheight=1)

        self.detecciones_lista_frame = tk.Frame(frame, bg="#ffffff")
        self.detecciones_lista_frame.pack(pady=23.29)
        

        self.detecciones_widgets = {}
        for class_name in class_names:
            item_frame = tk.Frame(self.detecciones_lista_frame, bg="#ffffff")
            item_frame.pack(side="left", padx=10)
            item_frame.pack_forget()  # Ocultar inicialmente
            
            color = COLOR_MAP.get(class_name, "#000000")
            bullet = tk.Label(item_frame, text="■", fg=color, font=("Segoe UI", 14, "bold"),
                              bg="#ffffff")
            bullet.pack(side="left", padx=(0, 5))
            
            display = DISPLAY_NAMES.get(class_name, class_name).upper()
            name_label = tk.Label(item_frame, text=f"{display}:", fg="black",
                                  font=("Segoe UI", 12, "bold"), bg="#ffffff")
            name_label.pack(side="left")
            
            count_label = tk.Label(item_frame, text=" 0", fg="black",
                                   font=("Segoe UI", 12, "bold"), bg="#ffffff")
            count_label.pack(side="left")
            
            self.detecciones_widgets[class_name] = {
                'frame': item_frame,
                'count_label': count_label
            }

        self.detecciones_img_label = tk.Label(frame, bg="#e2e8f0", width=900, height=600, relief="solid", bd=1)
        self.detecciones_img_label.pack(pady=10)

    def update_detecciones_tab(self):

        shown = set()
        for k in class_names:
            v = self.last_counts.get(k, 0)
            if v > 0 and k in self.detecciones_widgets:
                # Actualizar count y mostrar
                self.detecciones_widgets[k]['count_label'].config(text=f" {v}")
                self.detecciones_widgets[k]['frame'].pack(side="left", padx=10)
                shown.add(k)
            elif k in self.detecciones_widgets:
                # Ocultar si no hay detecciones
                self.detecciones_widgets[k]['frame'].pack_forget()

        # Manejar nombres extra no estándar
        extra_names = [name for name in self.last_counts.keys() if name not in class_names and name not in shown]
        for name in extra_names:
            v = self.last_counts.get(name, 0)
            if v > 0:
                # Crear frame temporal para items no estándar
                if name not in self.detecciones_widgets:
                    item_frame = tk.Frame(self.detecciones_lista_frame, bg="#ffffff")
                    color = COLOR_MAP.get(name, "#000000")
                    bullet = tk.Label(item_frame, text="■", fg=color, font=("Segoe UI", 14, "bold"), bg="#ffffff")
                    bullet.pack(side="left", padx=(0, 5))
                    name_label = tk.Label(item_frame, text=f"{DISPLAY_NAMES.get(name, name).upper()}:", fg="black",
                                          font=("Segoe UI", 12, "bold"), bg="#ffffff")
                    name_label.pack(side="left")
                    count_label = tk.Label(item_frame, text=" 0", fg="black", font=("Segoe UI", 12, "bold"), bg="#ffffff")
                    count_label.pack(side="left")
                    self.detecciones_widgets[name] = {'frame': item_frame, 'count_label': count_label}
                
                self.detecciones_widgets[name]['count_label'].config(text=f" {v}")
                self.detecciones_widgets[name]['frame'].pack(side="left", padx=10)

        if self.last_result_image and os.path.exists(self.last_result_image):

            cache_key = f"{self.last_result_image}_900_600_detecciones"
            if cache_key not in self.image_cache:
                imgtk = get_image_tk(self.last_result_image, width=900, height=600)
                if imgtk:
                    self.image_cache[cache_key] = imgtk
            else:
                imgtk = self.image_cache[cache_key]
            
            if imgtk:

                if hasattr(self.detecciones_img_label, 'imgtk'):
                    del self.detecciones_img_label.imgtk
                self.detecciones_img_label.imgtk = imgtk
                self.detecciones_img_label.config(image=imgtk)
        else:
            self.detecciones_img_label.config(image="", text="No hay imagen de resultado")

    # -----------------------------
    # PESTAÑA TABLA DE RESULTADOS (organizada en 2 columnas)
    # LAZY RENDERING - Se crea solo cuando se abre la pestaña
    # -----------------------------
    def create_tabla_tab(self):
       
        pass
    
    def _build_tabla_tab_lazy(self):
        """🔥 LAZY RENDERING: Construye la tabla solo cuando se abre."""
        if self.tabla_creada:
            return
        
        self.tabla_creada = True
        
        frame = self.tab_tabla
        
        # Limpiar placeholder si existe
        for widget in frame.winfo_children():
            widget.destroy()
        
        frame.configure(bg="#ffffff")

        # Canvas con scroll vertical
        canvas = tk.Canvas(frame, bg="#ffffff", highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#ffffff")


        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Título general (centrado, ocupa ambas columnas)
        titulo = tk.Label(scrollable_frame, text="REPORTE DE ANÁLISIS - EXAMEN GENERAL DE ORINA",
                          font=("Segoe UI", 18, "bold"), bg="#ffffff", fg="#0f172a")
        titulo.pack(pady=20)

        # Frame contenedor de las dos columnas
        two_columns = tk.Frame(scrollable_frame, bg="#ffffff")
        two_columns.pack(fill="both", expand=True, padx=20, pady=10)

        # Columna izquierda
        col_left = tk.Frame(two_columns, bg="#ffffff")
        col_left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # Columna derecha
        col_right = tk.Frame(two_columns, bg="#ffffff")
        col_right.pack(side="right", fill="both", expand=True, padx=(10, 0))

        # ---- Tabla Examen Físico (izquierda, arriba) ----
        self._crear_tabla_con_combobox(col_left, "EXAMEN FÍSICO", FISICO_PARAMS, self.fisico_vars, pack_in_frame=False)

        # ---- Tabla Examen Químico (izquierda, abajo) ----
        self._crear_tabla_con_combobox(col_left, "EXAMEN QUÍMICO", QUIMICO_PARAMS, self.quimico_vars, pack_in_frame=False)

        # Botón Guardar Resultados debajo de Examen Químico
        btn_frame = tk.Frame(col_left, bg="#ffffff")
        btn_frame.pack(pady=5, fill="x")

        tk.Button(btn_frame, text="💾 Guardar Resultados", command=self.save_results,
                  bg="#10b981", fg="white", font=("Segoe UI", 12, "bold"),
                  padx=15, pady=0.01, relief="flat", bd=0, cursor="hand2").pack(side="left", padx=10)

        # ---- Tabla Celularidad (derecha, arriba) ----
        self._crear_tabla_celularidad(col_right, pack_in_frame=False)

        # ---- Tabla Cristaluria (derecha, abajo) ----
        self._crear_tabla_con_combobox(col_right, "EXAMEN MICROSCÓPICO - CRISTALURIA", CRISTALURIA_PARAMS, self.cristaluria_vars, pack_in_frame=False)


        canvas.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))
        

        self.tabla_tab_canvas = canvas
        self.tabla_tab_scrollable = scrollable_frame

    def save_results(self):
        """Guarda los resultados de las tablas en el archivo JSON de resultados."""
        results = {
            "paciente": {
                "nombre": self.nombre_var.get(),
                "apellidos": self.apellidos_var.get(),
                "edad": self.edad_var.get(),
                "sexo": self.sexo_var.get(),
                "folio": self.folio_var.get(),
                "fecha": self.fecha_var.get(),
                "elaboro": self.elaboro_var.get()
            },
            "examen_fisico": {k: v.get() for k, v in self.fisico_vars.items()},
            "examen_quimico": {k: v.get() for k, v in self.quimico_vars.items()},
            "celularidad": dict({k: v.get() for k, v in self.celularidad_vars.items()}, **{
                "LEUCOCITOS": self.leuko_var.get(),
                "ERITROCITOS": self.eryth_var.get(),
                "LEVADURAS": self.levadura_var.get(),
                "CÉLULAS URETRALES SUPERFICIALES": self.epith_var.get(),
                "CÉLULAS URETRALES INTERMEDIAS": self.epithn_var.get(),
                "CILINDROS": self.cast_var.get()
            }),
            "cristaluria": dict({k: v.get() for k, v in self.cristaluria_vars.items()}, **{"OXALATO DE CALCIO": self.cryst_var.get()}),
            "timestamp": datetime.now().isoformat()
        }
        try:
            with open(os.path.join(desktop_path, "stats.json"), "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=4)
            messagebox.showinfo("Guardado", "Resultados guardados exitosamente.")

            # Limpiar la vista de impresión para que se regenere si se vuelve a guardar
            if hasattr(self, 'preview_scrollable'):
                for widget in self.preview_scrollable.winfo_children():
                    widget.destroy()
            if hasattr(self, 'preview_images'):
                self.preview_images.clear()

            # Habilitar la pestaña de Imprimir y navegar a ella
            self.notebook.tab(self.tab_imprimir, state="normal")
            self.notebook.select(self.tab_imprimir)


            if FITZ_AVAILABLE:
                self.preview_pdf()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudieron guardar los resultados:\n{e}")

    def _crear_tabla_con_combobox(self, parent, titulo, params, vars_dict, pack_in_frame=True):
        """Crea una tabla con encabezados y la coloca en parent."""
        frame_tabla = tk.LabelFrame(parent, text=titulo, font=("Segoe UI", 12, "bold"),
                                    bg="#ffffff", fg="#0f172a", padx=10, pady=10)
        if pack_in_frame:
            frame_tabla.pack(pady=15, fill="x", padx=20)
        else:
            frame_tabla.pack(fill="x", pady=(0, 20))

        headers = ["Parámetro", "Resultado", "Valores de Referencia"]
        for i, header in enumerate(headers):
            tk.Label(frame_tabla, text=header, font=("Segoe UI", 11, "bold"),
                     bg="#f1f5f9", relief="solid", bd=1, anchor="center").grid(row=0, column=i, sticky="nsew", padx=1, pady=1)

        for row, param_info in enumerate(params, start=1):
            param = param_info["param"]
            ref = param_info["ref"]
            if param == "FOSFATO AMÓNICO MAGNÉSICO":
                param_text = "FOSFATO AMÓNICO MAGNÉSICO\n(FOSFATO TRIPLE)"
            else:
                param_text = param
            tk.Label(frame_tabla, text=param_text, font=("Segoe UI", 10),
                     bg="#ffffff", relief="solid", bd=1, anchor="w", padx=5).grid(row=row, column=0, sticky="nsew", padx=1, pady=1)

            if param_info.get("auto", False):
                if param == "OXALATO DE CALCIO":
                    var = self.cryst_var
                    cristal_options = ["AUSENTES", "ESCASOS (+)", "MODERADOS (++)", "ABUNDANTES (+++)"]
                    combo = ttk.Combobox(frame_tabla, textvariable=var, values=cristal_options,
                                         font=("Segoe UI", 10), state="readonly", width=20, justify="center")
                    combo.grid(row=row, column=1, sticky="nsew", padx=1, pady=1)
                else:
                    var = tk.StringVar(value="")
                    entry = tk.Entry(frame_tabla, textvariable=var, font=("Segoe UI", 10), width=15, justify="center")
                    entry.grid(row=row, column=1, sticky="nsew", padx=1, pady=1)
            elif param_info.get("options") is None:
                var = tk.StringVar(value="")
                entry = tk.Entry(frame_tabla, textvariable=var, font=("Segoe UI", 10), width=15, justify="center")
                entry.grid(row=row, column=1, sticky="nsew", padx=1, pady=1)
                vars_dict[param] = var
            else:
                var = tk.StringVar(value=param_info["options"][0] if param_info["options"] else "")
                combo = ttk.Combobox(frame_tabla, textvariable=var, values=param_info["options"],
                                     font=("Segoe UI", 10), state="readonly", width=20, justify="center")
                combo.grid(row=row, column=1, sticky="nsew", padx=1, pady=1)
                vars_dict[param] = var

            tk.Label(frame_tabla, text=ref, font=("Segoe UI", 10),
                     bg="#ffffff", relief="solid", bd=1, anchor="w", padx=5).grid(row=row, column=2, sticky="nsew", padx=1, pady=1)

        frame_tabla.columnconfigure(0, weight=2)
        frame_tabla.columnconfigure(1, weight=1)
        frame_tabla.columnconfigure(2, weight=3)
        return frame_tabla

    def _crear_tabla_celularidad(self, parent, pack_in_frame=True):
        """Crea la tabla de celularidad con los primeros valores editables y LEVADURAS con combobox."""
        frame_tabla = tk.LabelFrame(parent, text="EXAMEN MICROSCÓPICO - CELULARIDAD",
                                    font=("Segoe UI", 12, "bold"), bg="#ffffff", fg="#0f172a", padx=10, pady=10)
        if pack_in_frame:
            frame_tabla.pack(pady=15, fill="x", padx=20)
        else:
            frame_tabla.pack(fill="x", pady=(0, 20))

        headers = ["Parámetro", "Resultado", "Valores de Referencia"]
        for i, header in enumerate(headers):
            tk.Label(frame_tabla, text=header, font=("Segoe UI", 11, "bold"),
                     bg="#f1f5f9", relief="solid", bd=1, anchor="center").grid(row=0, column=i, sticky="nsew", padx=1, pady=1)

        for row, param_info in enumerate(CELULARIDAD_PARAMS, start=1):
            param = param_info["param"]
            ref = param_info["ref"]
            tk.Label(frame_tabla, text=param, font=("Segoe UI", 10),
                     bg="#ffffff", relief="solid", bd=1, anchor="w", padx=5).grid(row=row, column=0, sticky="nsew", padx=1, pady=1)

            if param_info.get("auto", False):
                if param == "LEUCOCITOS":
                    var = self.leuko_var
                    entry = tk.Entry(frame_tabla, textvariable=var, font=("Segoe UI", 10), width=15, justify="center")
                    entry.grid(row=row, column=1, sticky="nsew", padx=1, pady=1)
                elif param == "ERITROCITOS":
                    var = self.eryth_var
                    entry = tk.Entry(frame_tabla, textvariable=var, font=("Segoe UI", 10), width=15, justify="center")
                    entry.grid(row=row, column=1, sticky="nsew", padx=1, pady=1)
                elif param == "LEVADURAS":
                    var = self.levadura_var
                    levadura_options = ["AUSENTES", "ESCASAS (+)", "MODERADAS (++)", "ABUNDANTES (+++)"]
                    combo = ttk.Combobox(frame_tabla, textvariable=var, values=levadura_options,
                                         font=("Segoe UI", 10), state="readonly", width=20, justify="center")
                    combo.grid(row=row, column=1, sticky="nsew", padx=1, pady=1)
                elif param == "CÉLULAS URETRALES SUPERFICIALES":
                    var = self.epith_var
                    celula_options = ["AUSENTES", "ESCASAS (+)", "MODERADAS (++)", "ABUNDANTES (+++)"]
                    combo = ttk.Combobox(frame_tabla, textvariable=var, values=celula_options,
                                         font=("Segoe UI", 10), state="readonly", width=20, justify="center")
                    combo.grid(row=row, column=1, sticky="nsew", padx=1, pady=1)
                elif param == "CÉLULAS URETRALES INTERMEDIAS":
                    var = self.epithn_var
                    celula_options = ["AUSENTES", "ESCASAS (+)", "MODERADAS (++)", "ABUNDANTES (+++)"]
                    combo = ttk.Combobox(frame_tabla, textvariable=var, values=celula_options,
                                         font=("Segoe UI", 10), state="readonly", width=20, justify="center")
                    combo.grid(row=row, column=1, sticky="nsew", padx=1, pady=1)
                elif param == "CILINDROS":
                    var = self.cast_var
                    cilindro_options = ["AUSENTES", "ESCASOS (+)", "MODERADOS (++)", "ABUNDANTES (+++)"]
                    combo = ttk.Combobox(frame_tabla, textvariable=var, values=cilindro_options,
                                         font=("Segoe UI", 10), state="readonly", width=20, justify="center")
                    combo.grid(row=row, column=1, sticky="nsew", padx=1, pady=1)
                else:
                    var = tk.StringVar(value="")
                    entry = tk.Entry(frame_tabla, textvariable=var, font=("Segoe UI", 10), width=15, justify="center")
                    entry.grid(row=row, column=1, sticky="nsew", padx=1, pady=1)
            else:
                var = tk.StringVar(value=param_info["options"][0] if param_info["options"] else "")
                combo = ttk.Combobox(frame_tabla, textvariable=var, values=param_info["options"],
                                     font=("Segoe UI", 10), state="readonly", width=20, justify="center")
                combo.grid(row=row, column=1, sticky="nsew", padx=1, pady=1)
                self.celularidad_vars[param] = var

            tk.Label(frame_tabla, text=ref, font=("Segoe UI", 10),
                     bg="#ffffff", relief="solid", bd=1, anchor="w", padx=5).grid(row=row, column=2, sticky="nsew", padx=1, pady=1)

        frame_tabla.columnconfigure(0, weight=2)
        frame_tabla.columnconfigure(1, weight=1)
        frame_tabla.columnconfigure(2, weight=3)
        return frame_tabla

    # -----------------------------
    # PESTAÑA IMPRIMIR (con previsualización)
    # -----------------------------
    def create_imprimir_tab(self):
        frame = self.tab_imprimir
        frame.configure(bg="#ffffff")

        # Imagen de fondo (optimizada)
        bg_label = tk.Label(frame, image=self.bg_photo)
        bg_label.place(x=0, y=0, relwidth=1, relheight=1)

        # Botones superiores
        btn_frame = tk.Frame(frame, bg="#ffffff")
        btn_frame.pack(pady=10)

          font=("Segoe UI", 10), fg="#dc2626", bg="#ffffff").pack(side="left", padx=10)

        tk.Button(btn_frame, text="💾 Guardar PDF", command=self.export_pdf,
                  bg="#f59e0b", fg="white", font=("Segoe UI", 12, "bold"),
                  padx=15, pady=8, relief="flat", bd=0, cursor="hand2").pack(side="left", padx=10)

        # Botón Imprimir
        tk.Button(btn_frame, text="🖨 Imprimir", command=self.print_pdf,
                  bg="#10b981", fg="white", font=("Segoe UI", 12, "bold"),
                  padx=15, pady=8, relief="flat", bd=0, cursor="hand2").pack(side="left", padx=10)

        # Botón Cerrar Programa
        tk.Button(btn_frame, text="✖ Cerrar Programa", command=self.cerrar_programa,
                  bg="#dc2626", fg="white", font=("Segoe UI", 12, "bold"),
                  padx=15, pady=8, relief="flat", bd=0, cursor="hand2").pack(side="left", padx=10)

        # Área de previsualización
        preview_container = tk.LabelFrame(frame, text="Previsualización del PDF",
                                          font=("Segoe UI", 11, "bold"), bg="#ffffff", fg="#0f172a")
        preview_container.pack(pady=15, fill="both", expand=True, padx=20)

        self.preview_canvas = tk.Canvas(preview_container, bg="#e2e8f0", highlightthickness=0)
        scrollbar = ttk.Scrollbar(preview_container, orient="vertical", command=self.preview_canvas.yview)
        self.preview_scrollable = tk.Frame(self.preview_canvas, bg="#e2e8f0")
        self.preview_scrollable.bind("<Configure>", lambda e: self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox("all")))
        self.preview_canvas.create_window(
            (self.preview_canvas.winfo_width() // 2, 0),
            window=self.preview_scrollable,
            anchor="n"
        )
        self.preview_canvas.configure(yscrollcommand=scrollbar.set)


        self.preview_canvas.bind_all(
            "<MouseWheel>",
            lambda e: self.preview_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        )

        def resize_preview(event):
            self.preview_canvas.coords("all", event.width // 2, 0)

        self.preview_canvas.bind("<Configure>", resize_preview)

        self.preview_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.preview_images = []  # mantener referencia a las imágenes

    def preview_pdf(self):
        """Genera el PDF temporalmente y muestra sus páginas en el área de previsualización."""
        if not self.last_result_image:
            messagebox.showwarning("Sin análisis", "No se ha realizado un análisis aún.")
            return

        if not FITZ_AVAILABLE:
            messagebox.showerror("Error", "PyMuPDF no está instalado. Ejecute: pip install PyMuPDF")
            return

        # Limpiar previsualización anterior
        for widget in self.preview_scrollable.winfo_children():
            widget.destroy()
        self.preview_images.clear()


        self.preview_canvas.yview_moveto(0)

        # Generar PDF temporal
        temp_pdf = desktop_file(f"temp_preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
        try:
            self._generate_pdf_to_file(temp_pdf)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo generar el PDF:\n{e}")
            return

        # Cargar el PDF con PyMuPDF
        try:
            doc = fitz.open(temp_pdf)
            max_width = self.preview_canvas.winfo_width() - 20
            if max_width < 100:
                max_width = 600

            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                zoom = 1.5
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img_data = pix.tobytes("png")
                pil_img = PILImage.open(io.BytesIO(img_data))
                photo = ImageTk.PhotoImage(pil_img)
                self.preview_images.append(photo)

                lbl_page = tk.Label(self.preview_scrollable, text=f"Página {page_num+1}", font=("Segoe UI", 10, "bold"),
                                    bg="#e2e8f0", fg="#0f172a")
                lbl_page.pack(pady=(10, 0))

                container = tk.Frame(self.preview_scrollable, bg="#e2e8f0")
                container.pack(fill="x", pady=10)

                lbl_img = tk.Label(container, image=photo, bg="#e2e8f0")
                lbl_img.image = photo  
                lbl_img.pack(anchor="center")


            self.preview_canvas.update_idletasks()
            self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox("all"))

            doc.close()

            self.root.update_idletasks()
            self.preview_canvas.yview_moveto(0)
            os.remove(temp_pdf)
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo previsualizar el PDF:\n{e}")
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

    def _generate_pdf_to_file(self, filename):
        """Genera el PDF con los datos guardados en stats.json y lo guarda en filename."""
        # Cargar datos desde stats.json
        saved_data = {}
        try:
            with open(os.path.join(desktop_path, "stats.json"), "r", encoding="utf-8") as f:
                saved_data = json.load(f)
        except Exception:
            pass
        
        doc = BaseDocTemplate(filename, pagesize=letter,
                                rightMargin=0, leftMargin=0,
                                topMargin=0, bottomMargin=0)
        story = []

        # Crear frame
        frame = Frame(
            0,
            0,
            doc.pagesize[0],
            doc.pagesize[1],
            leftPadding=0,
            bottomPadding=0,
            rightPadding=0,
            topPadding=0,
            id='normal'
        )

        background_path = resource_path("assets/PDF_FONDOPLANTILLA.jpg")
        template = BackgroundPageTemplate(
            id='template',
            frames=[frame],
            background_path=background_path
        )

        template.onPage = scale_content
        template.onPageEnd = restore_canvas

        doc.addPageTemplates([template])

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'],
                                     fontSize=16, alignment=TA_CENTER, spaceAfter=20)
        normal_style = styles['Normal']
        centered_bold_style = ParagraphStyle('CenteredBold', parent=styles['Normal'],
                                             fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=6)

        total_pages = 4
        
        # Usar datos guardados o variables de UI como fallback
        paciente_data = saved_data.get("paciente", self.patient_data)
        realizo = paciente_data.get('elaboro', '—')
        realizo_line = f"<b>REALIZÓ:</b> {realizo}"

        # PÁGINA 1
        story.append(Spacer(1, 0.2 * inch))
        story.append(self._create_patient_table(1, total_pages, paciente_data))
        story.append(Spacer(1, 0.2 * inch))

        fisico_data = [["PARÁMETRO", "RESULTADO", "VALORES DE REFERENCIA"]]
        examen_fisico = saved_data.get("examen_fisico", {})
        for param in FISICO_PARAMS:
            nombre = param["param"]
            ref = param["ref"]
            if nombre == "DENSIDAD":
                res = examen_fisico.get(nombre, "").strip() if examen_fisico else self.fisico_vars.get(nombre, tk.StringVar()).get().strip()
                if res == "":
                    res = "-"
            else:
                res = examen_fisico.get(nombre, "") if examen_fisico else self.fisico_vars.get(nombre, tk.StringVar()).get()
            fisico_data.append([format_param_pdf(nombre), res, ref])

        fisico_table = Table(fisico_data, colWidths=[180, 180, 180])
        fisico_table.setStyle(self._tabla_estilo_con_bold())
        story.append(Paragraph("EXAMEN FÍSICO", centered_bold_style))
        story.append(Spacer(1, 0.1 * inch))
        story.append(fisico_table)
        story.append(Spacer(1, 0.2 * inch))

        quimico_data = [["PARÁMETRO", "RESULTADO", "VALORES DE REFERENCIA"]]
        examen_quimico = saved_data.get("examen_quimico", {})
        for param in QUIMICO_PARAMS:
            nombre = param["param"]
            ref = param["ref"]
            res = examen_quimico.get(nombre, "") if examen_quimico else self.quimico_vars.get(nombre, tk.StringVar()).get()
            quimico_data.append([format_param_pdf(nombre), res, ref])
        quimico_table = Table(quimico_data, colWidths=[180, 180, 180])
        quimico_table.setStyle(self._tabla_estilo_con_bold())
        story.append(Paragraph("EXAMEN QUÍMICO", centered_bold_style))
        story.append(Spacer(1, 0.1 * inch))
        story.append(quimico_table)

        story.append(Spacer(1, 0.9 * inch))
        story.append(Paragraph(realizo_line, normal_style))
        story.append(PageBreak())

        # PÁGINA 2 - Celularidad
        story.append(self._create_patient_table(2, total_pages, paciente_data))
        story.append(Spacer(1, 0.2 * inch))

        celularidad = saved_data.get("celularidad", {})
        leuko_result = celularidad.get("LEUCOCITOS", "")
        eryth_result = celularidad.get("ERITROCITOS", "")
        levadura_result = celularidad.get("LEVADURAS", "AUSENTES")
        epith_result = celularidad.get("CÉLULAS URETRALES SUPERFICIALES", "AUSENTES")
        epithn_result = celularidad.get("CÉLULAS URETRALES INTERMEDIAS", "AUSENTES")
        cast_result = celularidad.get("CILINDROS", "AUSENTES")

        celularidad_data = [["PARÁMETRO", "RESULTADO", "VALORES DE REFERENCIA"]]
        for param_info in CELULARIDAD_PARAMS:
            nombre = param_info["param"]
            ref = param_info["ref"]
            if param_info.get("auto", False):
                if nombre == "LEUCOCITOS":
                    res = leuko_result
                elif nombre == "ERITROCITOS":
                    res = eryth_result
                elif nombre == "LEVADURAS":
                    res = levadura_result
                elif nombre == "CÉLULAS URETRALES SUPERFICIALES":
                    res = epith_result
                elif nombre == "CÉLULAS URETRALES INTERMEDIAS":
                    res = epithn_result
                elif nombre == "CILINDROS":
                    res = cast_result
                else:
                    res = ""
            else:
                res = self.celularidad_vars.get(nombre, tk.StringVar()).get()
            celularidad_data.append([format_param_pdf(nombre), res, ref])

        celularidad_table = Table(celularidad_data, colWidths=[180, 180, 180])
        celularidad_table.setStyle(self._tabla_estilo_con_bold())
        story.append(Paragraph("EXAMEN MICROSCÓPICO - CELULARIDAD", centered_bold_style))
        story.append(Spacer(1, 0.1 * inch))
        story.append(celularidad_table)
        story.append(Spacer(1, 0.1 * inch))

        story.append(Spacer(1, 1.6 * inch))
        story.append(Paragraph(realizo_line, normal_style))
        story.append(PageBreak())

        # PÁGINA 3 - Cristaluria
        story.append(self._create_patient_table(3, total_pages, paciente_data))
        story.append(Spacer(1, 0.2 * inch))

        cristaluria_data = [["PARÁMETRO", "RESULTADO", "VALORES DE REFERENCIA"]]
        examen_cristaluria = saved_data.get("cristaluria", {})
        for param in CRISTALURIA_PARAMS:
            nombre = param["param"]
            ref = param["ref"]
            res = examen_cristaluria.get(nombre, "") if examen_cristaluria else self.cristaluria_vars.get(nombre, tk.StringVar()).get()
            cristaluria_data.append([format_param_pdf(nombre), res, ref])
        cristaluria_table = Table(cristaluria_data, colWidths=[180, 180, 180])
        cristaluria_table.setStyle(self._tabla_estilo_con_bold())
        story.append(Paragraph("EXAMEN MICROSCÓPICO - CRISTALURIA", centered_bold_style))
        story.append(Spacer(1, 0.1 * inch))
        story.append(cristaluria_table)

        story.append(Spacer(1, 2 * inch))
        story.append(Paragraph(realizo_line, normal_style))
        story.append(PageBreak())

        # PÁGINA 4 - Imagen
        story.append(self._create_patient_table(4, total_pages, paciente_data))
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph("MUESTRA ANALIZADA", centered_bold_style))
        story.append(Spacer(1, 0.1 * inch))
        if os.path.exists(self.last_result_image):
            img = Image(self.last_result_image, width=5*inch, height=4*inch, kind='proportional')
            img.hAlign = 'CENTER'
            story.append(img)
        else:
            story.append(Paragraph("No se encontró la imagen de resultado.", normal_style))

        story.append(Spacer(1, 3.8 * inch))
        story.append(Paragraph(realizo_line, normal_style))
        story.append(Spacer(1, 0.3 * inch))

        doc.build(story)

    def export_pdf(self):
        if not self.last_result_image:
            messagebox.showwarning("Sin análisis", "No se ha realizado un análisis aún.")
            return
        
        # Obtener nombre completo del paciente
        nombre = self.nombre_var.get().strip()
        apellidos = self.apellidos_var.get().strip()
        nombre_completo = f"{nombre}_{apellidos}".replace(" ", "_") if nombre and apellidos else "Paciente"
        
        # Abrir diálogo de guardado
        pdf_name = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            initialdir=desktop_path,
            initialfile=f"EGO_{nombre_completo}.pdf"
        )
        
        # Si el usuario cancela el diálogo, pdf_name será vacío
        if not pdf_name:
            return
        
        try:
            self._generate_pdf_to_file(pdf_name)
            messagebox.showinfo("PDF", f"PDF generado exitosamente:\n{pdf_name}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo generar el PDF:\n{e}")

    def print_pdf(self):
        """Genera un PDF temporal e inicia la impresión directa."""
        if not self.last_result_image:
            messagebox.showwarning("Sin análisis", "No se ha realizado un análisis aún.")
            return
        
        # Crear PDF temporal en el escritorio
        temp_pdf = desktop_file(f"temp_print_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
        
        try:
            # Generar el PDF
            self._generate_pdf_to_file(temp_pdf)
            
            # Obtener la ruta absoluta del PDF
            pdf_path = os.path.abspath(temp_pdf)
            
            # Imprimir usando el programa predeterminado
            if os.name == 'nt':  # Windows
                # Intentar usar cmd.exe para abrir con la aplicación predeterminada
                try:
                    subprocess.Popen(['cmd', '/c', 'start', '/max', pdf_path])
                    messagebox.showinfo("Imprimir", "El documento se ha abierto.\nPor favor, use el menú Imprimir de la aplicación.")
                    # Programar eliminación después de 30 segundos
                    self.root.after(30000, lambda: self._delete_temp_file(pdf_path))
                except Exception as inner_e:
                    # Si falla, intentar de otra forma
                    subprocess.Popen(f'powershell -Command "Start-Process \'{pdf_path}\'"', shell=True)
                    messagebox.showinfo("Imprimir", "El documento se ha abierto.\nPor favor, use el menú Imprimir de la aplicación.")
                    self.root.after(30000, lambda: self._delete_temp_file(pdf_path))
            else:  # Linux/Mac
                subprocess.Popen(['xdg-open', pdf_path])
                messagebox.showinfo("Imprimir", "El documento se ha abierto.\nPor favor, use el menú Imprimir de la aplicación.")
                self.root.after(30000, lambda: self._delete_temp_file(pdf_path))
                
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir el PDF:\n{e}")
            if os.path.exists(temp_pdf):
                self._delete_temp_file(temp_pdf)
    
    def _delete_temp_file(self, filepath):
        """Elimina un archivo temporal."""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:

            pass

    def _create_patient_table(self, page_num, total_pages, paciente_data=None):
        if paciente_data is None:
            paciente_data = self.patient_data
        data = paciente_data
        nombre_completo = f"{data.get('nombre', '')} {data.get('apellidos', '')}".strip() or "—"
        nombre_completo = nombre_completo.upper()
        folio = data.get('folio', '—').upper()
        fecha = data.get('fecha', datetime.now().strftime("%d / %m / %Y")).upper()
        edad = data.get('edad', '—')
        sexo = data.get('sexo', '—').upper()
        diagnostico = "CHECK UP"
        medico = "A QUIEN CORRESPONDA"

        styles = getSampleStyleSheet()
        compact_style = ParagraphStyle('Compact', parent=styles['Normal'],
                                       fontSize=9, leading=10, spaceAfter=0)

        nombre_para = Paragraph(nombre_completo, compact_style)
        folio_para = Paragraph(folio, compact_style)
        fecha_para = Paragraph(fecha, compact_style)
        edad_sexo_para = Paragraph(f"{edad} / {sexo}".upper(), compact_style)
        medico_para = Paragraph(medico, compact_style)
        hoja_para = Paragraph(f"{page_num} de {total_pages}", compact_style)
        diagnostico_para = Paragraph(diagnostico, compact_style)
        ego_para = Paragraph("EGO", compact_style)

        table_data = [
            ["NOMBRE DEL PACIENTE", nombre_para, "FOLIO LAB.", folio_para],
            ["ESTUDIOS SOLICITADOS", ego_para, "FECHA ANÁLISIS", fecha_para],
            ["EDAD / GÉNERO", edad_sexo_para, "MÉDICO", medico_para],
            ["DIAGNÓSTICO", diagnostico_para, "HOJA", hoja_para],
        ]

        col_widths = [120, 190, 90, 152]
        table = Table(table_data, colWidths=col_widths, rowHeights=None)

        style = TableStyle([

            ('GRID', (0,0), (-1,-1), 0, colors.white),
            ('BOX', (0,0), (-1,-1), 0, colors.white),
            ('INNERGRID', (0,0), (-1,-1), 0, colors.white),


            ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
            ('FONTNAME', (2,0), (2,-1), 'Helvetica-Bold'),

            # Valores normales
            ('FONTNAME', (1,0), (1,-1), 'Helvetica'),
            ('FONTNAME', (3,0), (3,-1), 'Helvetica'),

            # Tipografía y espaciado
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (0,-1), 'LEFT'),
            ('ALIGN', (1,0), (1,-1), 'LEFT'),
            ('ALIGN', (2,0), (2,-1), 'LEFT'),
            ('ALIGN', (3,0), (3,-1), 'LEFT'),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ])
        table.setStyle(style)
        return table

    def _tabla_estilo_con_bold(self):
        return TableStyle([
            # Encabezado
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#c1d9fc")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.black),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 10),

            # Cuerpo general
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,1), (-1,-1), 9),


            ('FONTNAME', (0,1), (0,-1), 'Helvetica-Bold'),  # Parámetros
            ('FONTNAME', (2,1), (2,-1), 'Helvetica-Bold'),  # Referencias

            # Alineaciones
            ('ALIGN', (0,1), (0,-1), 'RIGHT'),
            ('ALIGN', (1,1), (1,-1), 'CENTER'),
            ('ALIGN', (2,1), (2,-1), 'LEFT'),

            # Alineación encabezado
            ('ALIGN', (0,0), (-1,0), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),

            # Espaciado elegante
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('TOPPADDING', (0,0), (-1,-1), 6),


        ])

# EJECUCIÓN CON SISTEMA DE CARGA
# 1. Crear ventana (oculta)
# 2. Crear app (sin cargar modelo)
# 3. Mostrar splash con barra de progreso
# 4. Cargar modelo en segundo plano (HILO DAEMON)
# 5. Cerrar splash y mostrar interfaz cuando esté lista
if __name__ == "__main__":
    root = tk.Tk()
    
    # 1. Crear app (con ventana oculta)
    app = AnalizadorSedimento(root)
    
    # 2. Mostrar splash screen inmediatamente
    splash = mostrar_carga(root)
    root.update_idletasks()

    # 3. Iniciar carga en segundo plano cuando la UI esté idle
    root.after_idle(lambda: iniciar_carga_asincronico(app, splash))
    
    # 4. Iniciar loop principal
    root.mainloop()
