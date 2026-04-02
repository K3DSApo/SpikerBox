import serial
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from collections import deque
import numpy as np
import time
from scipy.signal import iirnotch, butter, sosfilt, sosfilt_zi, tf2sos

# =============================================================================
# CONFIGURACIÓN
# =============================================================================
PORT              = "COM3"
BAUDRATE         = 115200
TIMEOUT          = 0.01
WINDOW_SIZE      = 800
REFRESH_INTERVAL = 5
SMOOTH_WINDOW    = 15
NOTCH_FREQ       = 60
Q_FACTOR         = 30
FS               = 1000
HIGHPASS_CUTOFF  = 10

UMBRAL       = 30      # RMS mínimo para considerar músculo activo
HOLD_TIME_MS = 250     # ms que el botón se mantiene activo tras el último pico
WARMUP_S     = 5.0     # segundos de estabilización — sin detección ni comandos

# =============================================================================
# BUFFERS
# =============================================================================
data_ch1 = deque([0] * WINDOW_SIZE, maxlen=WINDOW_SIZE)
data_ch2 = deque([0] * WINDOW_SIZE, maxlen=WINDOW_SIZE)
out_ch1  = deque([0.0] * WINDOW_SIZE, maxlen=WINDOW_SIZE)
out_ch2  = deque([0.0] * WINDOW_SIZE, maxlen=WINDOW_SIZE)

# =============================================================================
# CONEXIÓN SERIAL
# =============================================================================
try:
    ser = serial.Serial(PORT, BAUDRATE, timeout=TIMEOUT)
    print(f"[OK] Conectado a {PORT}")
except Exception as e:
    print(f"[ERROR] {e}")
    exit()

# =============================================================================
# FILTROS — sosfilt con estado persistente (sin distorsión en bordes)
# =============================================================================
_b_notch, _a_notch = iirnotch(NOTCH_FREQ, Q_FACTOR, FS)
_sos_notch          = tf2sos(_b_notch, _a_notch)
_sos_hp             = butter(4, HIGHPASS_CUTOFF / (0.5 * FS), btype='high', output='sos')

_zi_notch_ch1 = sosfilt_zi(_sos_notch)
_zi_notch_ch2 = sosfilt_zi(_sos_notch).copy()
_zi_hp_ch1    = sosfilt_zi(_sos_hp)
_zi_hp_ch2    = sosfilt_zi(_sos_hp).copy()

def filtrar_muestra(valor, zi_notch, zi_hp):
    x = np.array([float(valor)])
    y_notch, zi_notch = sosfilt(_sos_notch, x, zi=zi_notch)
    y_hp,    zi_hp    = sosfilt(_sos_hp,    y_notch, zi=zi_hp)
    return float(y_hp[0]), zi_notch, zi_hp

def moving_average(buffer, window):
    arr = np.array(buffer, dtype=float)
    if len(arr) < window:
        return arr
    return np.convolve(arr, np.ones(window) / window, mode='same')

# =============================================================================
# FIGURA
# =============================================================================
plt.style.use("seaborn-v0_8-darkgrid")
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
fig.suptitle("SpikerBox — Canal 1 y Canal 2  |  Notch 60Hz + Highpass 10Hz + Media Móvil",
             fontsize=12)

zeros = [0.0] * WINDOW_SIZE
line_ch1, = ax1.plot(zeros, color='skyblue',    linewidth=1.5, label="Canal 1")
line_ch2, = ax2.plot(zeros, color='lightcoral', linewidth=1.5, label="Canal 2")

for ax in [ax1, ax2]:
    ax.set_ylabel("ADC (centrado)")
    ax.set_xlim(0, WINDOW_SIZE)
    ax.set_ylim(-200, 200)
    ax.legend(loc="upper right")
ax2.set_xlabel("Muestras")

# Métricas (esquina superior izquierda)
text_ch1 = ax1.text(0.02, 0.88, "", transform=ax1.transAxes, fontsize=9,
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.7))
text_ch2 = ax2.text(0.02, 0.88, "", transform=ax2.transAxes, fontsize=9,
                    bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.7))

# Indicadores de estado — solo reflejan si se está mandando 1 o 0 a la ESP32
ind_ch1 = ax1.text(0.82, 0.88, "●  REPOSO  → ESP32: 0", transform=ax1.transAxes,
                   fontsize=9, color="gray",
                   bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.7))
ind_ch2 = ax2.text(0.82, 0.88, "●  REPOSO  → ESP32: 0", transform=ax2.transAxes,
                   fontsize=9, color="gray",
                   bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.7))

# =============================================================================
# ESTADO GLOBAL
# =============================================================================
paused      = False
last_update = time.time()
_inicio     = time.time()

boton1    = False
boton2    = False
last_act1 = 0.0
last_act2 = 0.0

_ultimo_comando = ""

# =============================================================================
# ENVÍO A ESP32
# =============================================================================
def enviar_comando(b1, b2):
    global _ultimo_comando
    cmd = f"{int(b1)},{int(b2)}\n"
    if cmd != _ultimo_comando:
        try:
            ser.write(cmd.encode('utf-8'))
            _ultimo_comando = cmd
            print(f"[ESP32] → boton1={int(b1)}  boton2={int(b2)}")
        except Exception as e:
            print(f"[ERROR] Serial write: {e}")

# =============================================================================
# ANÁLISIS AL PAUSAR
# =============================================================================
def analizar_segmento():
    for nombre, buf in [("Canal 1", out_ch1), ("Canal 2", out_ch2)]:
        arr = np.array(buf, dtype=float)
        print(f"\n[🔎 {nombre}]")
        print(f"  RMS:             {np.sqrt(np.mean(arr**2)):.2f}")
        print(f"  Pico a Pico:     {np.max(arr) - np.min(arr):.2f}")
        freqs = np.fft.rfftfreq(len(arr), 1 / FS)
        print(f"  Freq. dominante: {freqs[np.argmax(np.abs(np.fft.rfft(arr)))]:.2f} Hz")
    print()

# =============================================================================
# PAUSA
# =============================================================================
def toggle_pause(event):
    global paused
    if event.key == ' ':
        paused = not paused
        print("[PAUSA]" if paused else "[REANUDANDO]")
        text_ch1.set_text("[PAUSA]" if paused else "")
        if paused:
            analizar_segmento()
            enviar_comando(0, 0)

fig.canvas.mpl_connect('key_press_event', toggle_pause)

# =============================================================================
# UPDATE
# =============================================================================
def update(frame):
    global paused, last_update, boton1, boton2, last_act1, last_act2
    global _zi_notch_ch1, _zi_notch_ch2, _zi_hp_ch1, _zi_hp_ch2

    if paused:
        return line_ch1, line_ch2

    try:
        # --- Leer Serial y filtrar muestra a muestra ---
        while ser.in_waiting:
            linea  = ser.readline().decode('utf-8').strip()
            partes = linea.split(',')
            if len(partes) == 2 and partes[0].isdigit() and partes[1].isdigit():
                raw1 = int(partes[0]) - 2048
                raw2 = int(partes[1]) - 2048

                f1s, _zi_notch_ch1, _zi_hp_ch1 = filtrar_muestra(raw1, _zi_notch_ch1, _zi_hp_ch1)
                f2s, _zi_notch_ch2, _zi_hp_ch2 = filtrar_muestra(raw2, _zi_notch_ch2, _zi_hp_ch2)

                out_ch1.append(f1s)
                out_ch2.append(f2s)

        # Media móvil para visualización
        f1 = moving_average(out_ch1, SMOOTH_WINDOW)
        f2 = moving_average(out_ch2, SMOOTH_WINDOW)

        ahora    = time.time() * 1000
        restante = WARMUP_S - (time.time() - _inicio)

        if restante > 0:
            # ── WARMUP — sin detección, sin comandos ──────────────────────
            enviar_comando(0, 0)
            ind_ch1.set_text(f"⏳ Estabilizando... {restante:.0f}s")
            ind_ch1.set_color("orange")
            ind_ch2.set_text(f"⏳ Estabilizando... {restante:.0f}s")
            ind_ch2.set_color("orange")

        else:
            # ── DETECCIÓN ACTIVA ──────────────────────────────────────────
            seg1 = f1[-50:]
            seg2 = f2[-50:]

            rms1 = np.sqrt(np.mean(seg1 ** 2))
            rms2 = np.sqrt(np.mean(seg2 ** 2))

            # Canal 1
            if rms1 > UMBRAL:
                boton1    = True
                last_act1 = ahora
            if boton1 and (ahora - last_act1 > HOLD_TIME_MS):
                boton1 = False

            # Canal 2
            if rms2 > UMBRAL:
                boton2    = True
                last_act2 = ahora
            if boton2 and (ahora - last_act2 > HOLD_TIME_MS):
                boton2 = False

            # Mandar comando — el indicador refleja exactamente lo que recibe la ESP32
            enviar_comando(boton1, boton2)

            if boton1:
                ind_ch1.set_text("🟢 ACTIVO  → ESP32: 1")
                ind_ch1.set_color("green")
            else:
                ind_ch1.set_text("●  REPOSO  → ESP32: 0")
                ind_ch1.set_color("gray")

            if boton2:
                ind_ch2.set_text("🟢 ACTIVO  → ESP32: 1")
                ind_ch2.set_color("green")
            else:
                ind_ch2.set_text("●  REPOSO  → ESP32: 0")
                ind_ch2.set_color("gray")

        # --- Métricas cada 100 ms ---
        if time.time() - last_update > 0.1:
            for arr, txt in [(f1[-FS:], text_ch1), (f2[-FS:], text_ch2)]:
                if len(arr) > 0:
                    rms   = np.sqrt(np.mean(arr ** 2))
                    pp    = np.max(arr) - np.min(arr)
                    freqs = np.fft.rfftfreq(len(arr), 1 / FS)
                    fd    = freqs[np.argmax(np.abs(np.fft.rfft(arr)))]
                    txt.set_text(f"RMS:{rms:.0f} | P-P:{pp:.0f} | {fd:.1f}Hz")

            ax1.set_ylim(np.min(f1) - 50, np.max(f1) + 50)
            ax2.set_ylim(np.min(f2) - 50, np.max(f2) + 50)
            last_update = time.time()

        line_ch1.set_ydata(f1)
        line_ch2.set_ydata(f2)
        return line_ch1, line_ch2

    except Exception as e:
        print(f"[ERROR] {e}")
        return line_ch1, line_ch2

# =============================================================================
# ANIMACIÓN
# =============================================================================
ani = animation.FuncAnimation(fig, update, interval=REFRESH_INTERVAL, blit=False)
plt.tight_layout()
plt.show()
