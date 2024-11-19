import os
import subprocess
import re
import shutil
import sys
import configparser
import wx
import wx.lib.agw.genericmessagedialog as GMD
from wx.lib.buttons import GenButton
from threading import Thread

# Ruta del archivo .ini para guardar la configuración
CONFIG_FILE = os.path.expanduser("~/.mrs_vocal_remover.ini")

# Verificación de instalación de Demucs
def verificar_demucs():
    """Verifica si el comando `demucs` está disponible en el entorno actual."""
    try:
        result = subprocess.run(['demucs'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode == 0 or "usage" in result.stderr.lower() or "usage" in result.stdout.lower():
            return True
    except FileNotFoundError:
        pass

    # Verificamos si `demucs` está en las rutas del sistema
    if shutil.which('demucs'):
        return True

    return False

# Instalación de Demucs
def instalar_demucs():
    """Intenta instalar Demucs usando pip."""
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", 'demucs'], check=True)
        subprocess.run([sys.executable, "-m", "pip", "install", 'museval'], check=True)
        return True
    except subprocess.CalledProcessError:
        return False

# Función para ejecutar Demucs
def separar_audio(input_path, output_dir, separar_en_4, formato_salida, progress_callback):
    """Ejecuta Demucs con los parámetros especificados y actualiza el progreso."""
    try:
        if not os.path.exists(input_path):
            raise FileNotFoundError("El archivo no existe.")

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Construcción del comando
        command = ['demucs', '-n', 'htdemucs', input_path, '-d', 'cpu', '-o', output_dir]
        if not separar_en_4:
            command.insert(1, '--two-stems=vocals')  # Separar solo en vocales y no vocales

        if formato_salida == 'mp3':
            command.append('--mp3')  # Convertir a MP3

        # Ejecución del comando
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, command, result.stderr)

        # Actualizar progreso
        for line in result.stdout.splitlines():
            match = re.search(r'progress\s(\d+)%', line)
            if match:
                progress = int(match.group(1))
                progress_callback(progress)

        return f"Separación completada. Archivos guardados en: {output_dir}"

    except subprocess.CalledProcessError as e:
        return f"Error al procesar el archivo: {str(e)}\n{e.stderr}"
    except FileNotFoundError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"Error inesperado: {str(e)}"


# Hilo para ejecutar la separación de audio sin bloquear la interfaz
class Worker(Thread):
    def __init__(self, input_path, output_dir, separar_en_4, formato_salida, progress_callback, result_callback):
        super().__init__()
        self.input_path = input_path
        self.output_dir = output_dir
        self.separar_en_4 = separar_en_4
        self.formato_salida = formato_salida
        self.progress_callback = progress_callback
        self.result_callback = result_callback

    def run(self):
        resultado = separar_audio(self.input_path, self.output_dir, self.separar_en_4, self.formato_salida, self.progress_callback)
        self.result_callback(resultado)


class PantallaBienvenida(wx.Frame):
    def __init__(self, parent, title):
        super().__init__(parent, title=title, size=(500, 350))
        
        # Verificar si Demucs está disponible
        self.demucs_disponible = verificar_demucs()
        if not self.demucs_disponible:
            respuesta = wx.MessageBox(
                "Demucs no está instalado en el sistema. ¿Deseas instalarlo ahora?", 
                "Demucs no encontrado", 
                wx.YES_NO | wx.ICON_QUESTION
            )
            if respuesta == wx.YES:
                if instalar_demucs():
                    self.demucs_disponible = verificar_demucs()
                    wx.MessageBox("Demucs se instaló correctamente.", "Éxito", wx.OK | wx.ICON_INFORMATION)
                else:
                    wx.MessageBox("No se pudo instalar Demucs. Por favor, intente manualmente.", "Error", wx.OK | wx.ICON_ERROR)
                    self.Close()
            else:
                wx.MessageBox("Demucs es necesario para usar esta aplicación. Cerrando...", "Error", wx.OK | wx.ICON_ERROR)
                self.Close()

        self.panel = wx.Panel(self)
        self.sizer = wx.BoxSizer(wx.VERTICAL)

        bienvenida_label = wx.StaticText(self.panel, label="Bienvenido a MRS Vocal Remover")
        bienvenida_label.SetFont(wx.Font(18, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        self.sizer.Add(bienvenida_label, 0, wx.ALL | wx.CENTER, 10)

        descripcion_label = wx.StaticText(self.panel, label="MRS Vocal Remover puede separar archivos en instrumental y voz, o en 4 partes: bajo, batería, voz e instrumentos.")
        descripcion_label.Wrap(400)
        self.sizer.Add(descripcion_label, 0, wx.ALL | wx.CENTER, 10)

        contacto_label = wx.StaticText(self.panel, label="Creado por Ale Sánchez.\nEmail: alexsanagui.00@gmail.com")
        contacto_label.SetFont(wx.Font(12, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        contacto_label.SetForegroundColour(wx.Colour(169, 169, 169))
        self.sizer.Add(contacto_label, 0, wx.ALL | wx.CENTER, 10)

        continuar_button = wx.Button(self.panel, label="Continuar")
        continuar_button.Bind(wx.EVT_BUTTON, self.on_continuar)
        self.sizer.Add(continuar_button, 0, wx.ALL | wx.CENTER, 10)

        cancelar_button = wx.Button(self.panel, label="Cancelar")
        cancelar_button.Bind(wx.EVT_BUTTON, self.on_cancelar)
        self.sizer.Add(cancelar_button, 0, wx.ALL | wx.CENTER, 10)

        self.panel.SetSizer(self.sizer)

    def on_continuar(self, event):
        self.Close()
        ventana_principal.Show()

    def on_cancelar(self, event):
        self.Close()


class MainWindow(wx.Frame):
    def __init__(self, parent, title):
        super().__init__(parent, title=title, size=(600, 400))

        # Variables
        self.input_file = ""
        self.output_folder = self.cargar_configuracion()
        self.separar_en_4 = True
        self.formato_salida = "wav"

        self.panel = wx.Panel(self)
        self.sizer = wx.BoxSizer(wx.VERTICAL)

        self.create_widgets()
        
    def create_widgets(self):
        self.archivo_label = wx.StaticText(self.panel, label="Archivo de audio:")
        self.sizer.Add(self.archivo_label, 0, wx.ALL, 5)
        self.archivo_entry = wx.TextCtrl(self.panel, style=wx.TE_READONLY)
        self.sizer.Add(self.archivo_entry, 0, wx.ALL | wx.EXPAND, 5)
        self.archivo_button = wx.Button(self.panel, label="Seleccionar archivo")
        self.archivo_button.Bind(wx.EVT_BUTTON, self.seleccionar_archivo)
        self.sizer.Add(self.archivo_button, 0, wx.ALL | wx.CENTER, 5)

        self.carpeta_label = wx.StaticText(self.panel, label="Carpeta de salida:")
        self.sizer.Add(self.carpeta_label, 0, wx.ALL, 5)
        self.carpeta_entry = wx.TextCtrl(self.panel, value=self.output_folder, style=wx.TE_READONLY)
        self.sizer.Add(self.carpeta_entry, 0, wx.ALL | wx.EXPAND, 5)
        self.carpeta_button = wx.Button(self.panel, label="Seleccionar carpeta")
        self.carpeta_button.Bind(wx.EVT_BUTTON, self.seleccionar_carpeta)
        self.sizer.Add(self.carpeta_button, 0, wx.ALL | wx.CENTER, 5)

        self.opciones_label = wx.StaticText(self.panel, label="Seleccione el tipo de separación:")
        self.sizer.Add(self.opciones_label, 0, wx.ALL, 5)
        self.opcion1 = wx.RadioButton(self.panel, label="Separar en dos pistas: Vocal e Instrumental", style=wx.RB_GROUP)
        self.opcion2 = wx.RadioButton(self.panel, label="Separar en cuatro pistas: Bajo, Batería, Vocal, Instrumental")
        self.opcion1.SetValue(True)
        self.sizer.Add(self.opcion1, 0, wx.ALL, 5)
        self.sizer.Add(self.opcion2, 0, wx.ALL, 5)

        self.formato_label = wx.StaticText(self.panel, label="Seleccione el formato de salida:")
        self.sizer.Add(self.formato_label, 0, wx.ALL, 5)
        self.formato_box = wx.ComboBox(self.panel, choices=["wav", "mp3"], style=wx.CB_READONLY)
        self.formato_box.SetValue("wav")
        self.sizer.Add(self.formato_box, 0, wx.ALL | wx.EXPAND, 5)

        self.progreso = wx.Gauge(self.panel, range=100, size=(400, 25))
        self.sizer.Add(self.progreso, 0, wx.ALL | wx.CENTER, 5)

        self.comenzar_button = wx.Button(self.panel, label="Comenzar")
        self.comenzar_button.Bind(wx.EVT_BUTTON, self.comenzar_proceso)
        self.sizer.Add(self.comenzar_button, 0, wx.ALL | wx.CENTER, 5)

        self.panel.SetSizer(self.sizer)

    def seleccionar_archivo(self, event):
        with wx.FileDialog(self, "Selecciona un archivo de audio", wildcard="Archivos de audio (*.mp3;*.wav)|*.mp3;*.wav", style=wx.FD_OPEN) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.input_file = dlg.GetPath()
                self.archivo_entry.SetValue(self.input_file)

    def seleccionar_carpeta(self, event):
        with wx.DirDialog(self, "Selecciona la carpeta de salida") as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.output_folder = dlg.GetPath()
                self.carpeta_entry.SetValue(self.output_folder)

    def cargar_configuracion(self):
        if os.path.exists(CONFIG_FILE):
            config = configparser.ConfigParser()
            config.read(CONFIG_FILE)
            return config.get("Configuracion", "output_folder", fallback=os.path.expanduser("~"))
        return os.path.expanduser("~")

    def guardar_configuracion(self):
        config = configparser.ConfigParser()
        config.read(CONFIG_FILE)
        if "Configuracion" not in config.sections():
            config.add_section("Configuracion")
        config.set("Configuracion", "output_folder", self.output_folder)
        with open(CONFIG_FILE, "w") as configfile:
            config.write(configfile)

    def comenzar_proceso(self, event):
        if self.input_file:
            self.separar_en_4 = self.opcion2.GetValue()
            self.formato_salida = self.formato_box.GetValue()

            self.worker = Worker(self.input_file, self.output_folder, self.separar_en_4, self.formato_salida, self.actualizar_progreso, self.proceso_completado)
            self.worker.start()
        else:
            wx.MessageBox("Por favor selecciona un archivo para procesar.", "Error", wx.OK | wx.ICON_ERROR)

    def actualizar_progreso(self, progreso):
        self.progreso.SetValue(progreso)

    def proceso_completado(self, resultado):
        wx.MessageBox(resultado, "Resultado", wx.OK | wx.ICON_INFORMATION)
        

if __name__ == "__main__":
    app = wx.App(False)

    ventana_bienvenida = PantallaBienvenida(None, "Bienvenido a MRS Vocal Remover")
    ventana_bienvenida.Show()

    ventana_principal = MainWindow(None, "MRS Vocal Remover")

    app.MainLoop()
