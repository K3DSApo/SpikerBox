#include <esp_now.h>
#include <WiFi.h>

// -----------------------------
// Pines EMG (ADC)
// -----------------------------
const int EMG1_PIN = 34;
const int EMG2_PIN = 35;

// -----------------------------
// MAC del receptor (ESP32 del carro)
// Cámbiala por la MAC real de tu receptor
// -----------------------------
uint8_t broadcastAddress[] = {
  0x88, 0x57, 0x21, 0x8B, 0x5A, 0xC4
};

// -----------------------------
// Estructura ESP-NOW
// (debe ser idéntica a la del receptor)
// -----------------------------
typedef struct struct_message {
  int boton1;
  int boton2;
} struct_message;

struct_message datos;

// -----------------------------
// Botones — los escribe Python
// vía Serial, los lee el .ino
// -----------------------------
int boton1 = 0;
int boton2 = 0;

// -----------------------------
// Callback de envío ESP-NOW
// -----------------------------
void OnDataSent(const uint8_t *mac_addr,
                esp_now_send_status_t status) {
  // Silencioso para no contaminar el Serial que usa Python
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);   // 12 bits → 0-4095
  delay(500);

  // ESP-NOW
  WiFi.mode(WIFI_STA);

  if (esp_now_init() != ESP_OK) {
    Serial.println("[ERROR] ESP-NOW init falló");
    return;
  }

  esp_now_register_send_cb(OnDataSent);

  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, broadcastAddress, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;

  if (esp_now_add_peer(&peerInfo) != ESP_OK) {
    Serial.println("[ERROR] No se pudo agregar peer");
    return;
  }

  Serial.println("[OK] Emisora lista");
}

void loop() {

  // -----------------------------
  // 1. Leer CH1 y CH2 crudos
  //    y mandarlos a Python
  // -----------------------------
  int ch1 = analogRead(EMG1_PIN);
  int ch2 = analogRead(EMG2_PIN);

  // Formato: "CH1,CH2\n"  — Python lo parsea
  Serial.print(ch1);
  Serial.print(",");
  Serial.println(ch2);

  // -----------------------------
  // 2. Leer comando de Python
  //    Formato esperado: "B1,B2\n"
  //    Ejemplo: "1,0" / "0,1" / "1,1" / "0,0"
  // -----------------------------
  if (Serial.available() > 0) {
    String linea = Serial.readStringUntil('\n');
    linea.trim();

    // Parsear "B1,B2"
    int coma = linea.indexOf(',');
    if (coma > 0) {
      boton1 = linea.substring(0, coma).toInt();
      boton2 = linea.substring(coma + 1).toInt();
    }
  }

  // -----------------------------
  // 3. Mandar botones por ESP-NOW
  //    al carro receptor
  // -----------------------------
  datos.boton1 = boton1;
  datos.boton2 = boton2;

  esp_now_send(broadcastAddress,
               (uint8_t *) &datos,
               sizeof(datos));

  delay(10);  // ~100 muestras/segundo
}