#include "DHT.h"

#define DHTPIN 4
#define DHTTYPE DHT11

#define PIR_PIN 13
#define LED_PIN 2
#define BUZZER_PIN 15

DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(115200);

  pinMode(PIR_PIN, INPUT);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  digitalWrite(LED_PIN, LOW);
  digitalWrite(BUZZER_PIN, LOW);

  dht.begin();
}

void handleTrigger() {
  digitalWrite(LED_PIN, HIGH);
  digitalWrite(BUZZER_PIN, HIGH);
  delay(200);
  digitalWrite(BUZZER_PIN, LOW);
  delay(100);
  digitalWrite(LED_PIN, LOW);
}

void loop() {
  // =========================
  // 1. READ COMMANDS FROM FLASK
  // =========================
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd == "TRIGGER") {
      handleTrigger();
    }
  }

  // =========================
  // 2. SENSOR READ
  // =========================
  float temp = dht.readTemperature();
  float hum = dht.readHumidity();
  int motion = digitalRead(PIR_PIN);

  if (isnan(temp) || isnan(hum)) {
    Serial.println("ERR");
    delay(1000);
    return;
  }

  // =========================
  // 3. LOCAL ACTION (motion)
  // =========================
  if (motion == HIGH) {
    digitalWrite(LED_PIN, HIGH);
    digitalWrite(BUZZER_PIN, HIGH);
    delay(100);
    digitalWrite(BUZZER_PIN, LOW);
  } else {
    digitalWrite(LED_PIN, LOW);
    digitalWrite(BUZZER_PIN, LOW);
  }

  // =========================
  // 4. SEND DATA TO RPI
  // Format: T:xx.xx,H:xx.xx,M:0/1
  // =========================
  Serial.printf("T:%.2f,H:%.2f,M:%d\n", temp, hum, motion);

  delay(1000);
}