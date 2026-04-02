#define SPIKERBOX_CH1 34

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  Serial.println("Listo, enviando datos del SpikerBox...");
}

void loop() {
  int valor = analogRead(SPIKERBOX_CH1);
  Serial.println(valor);
  delay(10); // 100 muestras/segundo
}