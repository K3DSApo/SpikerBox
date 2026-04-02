import serial
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque
import numpy as np
import time
from scipy.signal import iirnotch, filtfilt, butter
import threading

# --- CONFIGURACIÓN ---
PORT = "COM3"
BAUDRATE = 115200
TIMEOUT = 0.01
WINDOW_SIZE = 800
REFRESH_INTERVAL = 5  # ms
SMOOTH_WINDOW = 15    # Tamaño de la media móvil
NOTCH_FREQ = 60       # Frecuencia del notch
Q_FACTOR = 30         # Calidad del notch
FS = 1000             # Frecuencia de muestreo en Hz
HIGHPASS_CUTOFF = 10  # Hz (para eliminar la señal lenta)

# --- BUFFER ---
data = deque([0]*WINDOW_SIZE, maxlen=WINDOW_SIZE)

# --- CONEXIÓN SERIAL ---
try:
    ser = serial.Serial(PORT, BAUDRATE, timeout=TIMEOUT)
    print(f"[OK] Conectado al puerto {PORT}")
except Exception as e:
    print(f"[ERROR] No se pudo abrir el puerto {PORT}: {e}")
    exit()

# --- FIGURA Y ESTILO ---
plt.style.use("seaborn-v0_8-darkgrid")
fig, ax = plt.subplots()
line_filtered, = ax.plot(data, color='skyblue', linewidth=1.5, label="EMG filtrada")
ax.set_title("Señal EMG Filtrada (Media Móvil + Notch + Highpass)", fontsize=12)
ax.set_xlabel("Muestras")
ax.set_ylabel("Valor ADC")
ax.set_ylim(0, 4095)
ax.set_xlim(0, WINDOW_SIZE)
ax.legend(loc="upper right")
text_info = ax.text(0.02, 0.93, "", transform=ax.transAxes)

paused = False
last_update = time.time()

# --- FUNCIONES DE FILTRADO ---
def moving_average(values, window):
    if len(values) < window:
        return np.mean(values)
    return np.convolve(values, np.ones(window)/window, mode='same')

def apply_notch_filter(data, notch_freq, fs, q):
    b, a = iirnotch(notch_freq, q, fs)
    return filtfilt(b, a, data)

def butter_highpass_filter(data, cutoff, fs, order=4):
    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='high', analog=False)
    return filtfilt(b, a, data)

# --- ANÁLISIS DE SEGMENTO (usado al pausar) ---
def analizar_segmento():
    segmento = np.array(data)
    smoothed = moving_average(segmento, SMOOTH_WINDOW)
    filtered_notch = apply_notch_filter(smoothed, NOTCH_FREQ, FS, Q_FACTOR)
    final_filtered = butter_highpass_filter(filtered_notch, HIGHPASS_CUTOFF, FS)

    amp_rms = np.sqrt(np.mean(final_filtered**2))
    amp_pp = np.max(final_filtered) - np.min(final_filtered)
    freqs = np.fft.rfftfreq(len(final_filtered), 1/FS)
    spectrum = np.abs(np.fft.rfft(final_filtered))
    freq_dom = freqs[np.argmax(spectrum)]

    print("\n[🔎 ANÁLISIS DE SEGMENTO PAUSADO]")
    print(f"Amplitud RMS: {amp_rms:.2f}")
    print(f"Amplitud Pico a Pico: {amp_pp:.2f}")
    print(f"Frecuencia Dominante: {freq_dom:.2f} Hz\n")

# --- PAUSAR / REANUDAR ---
def toggle_pause(event):
    global paused
    if event.key == ' ':
        paused = not paused
        estado = "[PAUSA]" if paused else "[REANUDANDO]"
        print(estado)
        text_info.set_text(estado)
        if paused:
            analizar_segmento()

fig.canvas.mpl_connect('key_press_event', toggle_pause)

# --- ACTUALIZACIÓN DE LA GRÁFICA (TIEMPO REAL) ---
def update(frame):
    global paused, last_update
    if paused:
        return line_filtered,

    try:
        while ser.in_waiting:
            linea = ser.readline().decode('utf-8').strip()
            if linea.isdigit():
                valor = int(linea)
                data.append(valor)

        # Filtrado
        data_np = np.array(data)
        smoothed = moving_average(data_np, SMOOTH_WINDOW)
        filtered_notch = apply_notch_filter(smoothed, NOTCH_FREQ, FS, Q_FACTOR)
        final_filtered = butter_highpass_filter(filtered_notch, HIGHPASS_CUTOFF, FS)

        # --- Cálculo en vivo de amplitud y frecuencia ---
        if time.time() - last_update > 0.1:  # cada 100 ms
            segmento = final_filtered[-FS:]  # 1 segundo de señal
            if len(segmento) > 0:
                amp_rms = np.sqrt(np.mean(segmento**2))
                amp_pp = np.max(segmento) - np.min(segmento)
                freqs = np.fft.rfftfreq(len(segmento), 1/FS)
                spectrum = np.abs(np.fft.rfft(segmento))
                freq_dom = freqs[np.argmax(spectrum)]

                text_info.set_text(f"RMS: {amp_rms:.1f} | P-P: {amp_pp:.1f} | Freq: {freq_dom:.1f} Hz")

            # Actualizar eje Y dinámico
            ax.set_ylim(np.min(final_filtered) - 100, np.max(final_filtered) + 100)
            last_update = time.time()

        # Actualizar gráfica
        line_filtered.set_ydata(final_filtered)
        return line_filtered,

    except Exception as e:
        print(f"[ERROR] Lectura: {e}")
        return line_filtered,

# --- ANIMACIÓN ---
ani = animation.FuncAnimation(fig, update, interval=REFRESH_INTERVAL, blit=True)
plt.tight_layout()
plt.show()

# --- MEDIR FRECUENCIA DE MUESTREO ---
def medir_fs():
    contador = 0
    tiempo_inicio = time.time()
    while contador < 1000:
        if ser.in_waiting:
            linea = ser.readline()
            if linea.decode().strip().isdigit():
                contador += 1
    tiempo_total = time.time() - tiempo_inicio
    fs_estimado = contador / tiempo_total
    print(f"\n[INFO] Frecuencia de muestreo estimada: {fs_estimado:.2f} Hz\n")

threading.Thread(target=medir_fs, daemon=True).start()
