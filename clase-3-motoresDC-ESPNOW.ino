#include <esp_now.h>
#include <WiFi.h>

// -----------------------------
// Pines de motores (L298N)
// -----------------------------
#define MOTOR1_IN1 27
#define MOTOR1_IN2 26

#define MOTOR2_IN1 25
#define MOTOR2_IN2 33

// -----------------------------
// Estructura de datos recibidos
// -----------------------------
typedef struct struct_message {
  int boton1;
  int boton2;
} struct_message;

struct_message datosRecibidos;

// -----------------------------
// Callback de recepción ESP-NOW
// -----------------------------
void OnDataRecv(const esp_now_recv_info_t *recv_info,
                const uint8_t *incomingData,
                int len) {

  memcpy(&datosRecibidos, incomingData, sizeof(datosRecibidos));

  // -----------------------------
  // Motor 1
  // -----------------------------
  if (datosRecibidos.boton1 == HIGH) {
    digitalWrite(MOTOR1_IN1, HIGH);
    digitalWrite(MOTOR1_IN2, LOW);
  } else {
    digitalWrite(MOTOR1_IN1, LOW);
    digitalWrite(MOTOR1_IN2, LOW);
  }

  // -----------------------------
  // Motor 2
  // -----------------------------
  if (datosRecibidos.boton2 == HIGH) {
    digitalWrite(MOTOR2_IN1, HIGH);
    digitalWrite(MOTOR2_IN2, LOW);
  } else {
    digitalWrite(MOTOR2_IN1, LOW);
    digitalWrite(MOTOR2_IN2, LOW);
  }

  // Debug
  Serial.print("Botón 1: ");
  Serial.print(datosRecibidos.boton1);
  Serial.print(" | Botón 2: ");
  Serial.println(datosRecibidos.boton2);
}

void setup() {
  Serial.begin(115200);

  // Configurar pines de motores
  pinMode(MOTOR1_IN1, OUTPUT);
  pinMode(MOTOR1_IN2, OUTPUT);
  pinMode(MOTOR2_IN1, OUTPUT);
  pinMode(MOTOR2_IN2, OUTPUT);

  // Motores detenidos al inicio
  digitalWrite(MOTOR1_IN1, LOW);
  digitalWrite(MOTOR1_IN2, LOW);
  digitalWrite(MOTOR2_IN1, LOW);
  digitalWrite(MOTOR2_IN2, LOW);

  WiFi.mode(WIFI_STA);

  if (esp_now_init() != ESP_OK) {
    Serial.println("Error inicializando ESP-NOW");
    return;
  }

  esp_now_register_recv_cb(OnDataRecv);

  Serial.println("Receptor listo: control inalámbrico de motores");
}

void loop() {
  delay(100);
}

