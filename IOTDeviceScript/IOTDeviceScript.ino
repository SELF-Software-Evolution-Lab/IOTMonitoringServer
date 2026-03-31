#include <Wire.h>
#include <U8g2lib.h>
#include <ESP8266WiFi.h>
#include <time.h>
#include <PubSubClient.h>
#include <DHT.h>

// =====================
//      DEFINICIONES
// =====================

#define DHTPIN 2
#define DHTTYPE DHT11

#define MEASURE_INTERVAL 2
#define ALERT_DURATION 60
#define LED_PIN 12          // D6 en NodeMCU (LED externo en protoboard: D6 y GND)
#define LED_EVENT_DURATION 60  // segundos que parpadea el LED
#define LED_BLINK_MS 400    // intervalo de parpadeo en ms

// =====================
//     DECLARACIONES
// =====================

// OLED SH1106 128x64 I2C (sin pin reset)
U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, /* reset=*/ U8X8_PIN_NONE);

// Sensor DHT
DHT dht(DHTPIN, DHTTYPE);

// Cliente WiFi / MQTT
WiFiClient net;
PubSubClient client(net);

// =====================
//   VARIABLES A EDITAR
// =====================

// WiFi
const char ssid[] = "FAMILIA FRANCO";
const char pass[] = "1014290398";

// Mosquitto
#define USER "ironman"
const char MQTT_HOST[] = "18.207.213.158";
const int MQTT_PORT = 8082;
const char MQTT_USER[] = USER;
const char MQTT_PASS[] = "jarvis123";

// Topics
const char MQTT_TOPIC_PUB[] = "colombia/cundinamarca/bogota/" USER "/out";
const char MQTT_TOPIC_SUB[] = "colombia/cundinamarca/bogota/" USER "/in";

// =====================
//     GLOBALES
// =====================

time_t now;

unsigned long measureTime = 0;
unsigned long alertTime = 0;

String alert = "";
float temp = NAN;
float humi = NAN;

// Evento LED (parpadeo + mensaje en OLED)
bool ledEventActive = false;
unsigned long ledEventStartTime = 0;
unsigned long ledBlinkLastToggle = 0;
bool ledBlinkState = false;

// =====================
//     MQTT CONNECT
// =====================

void mqtt_connect() {
  while (!client.connected()) {
    Serial.print("MQTT connecting ... ");

    if (client.connect(MQTT_USER, MQTT_USER, MQTT_PASS)) {
      Serial.println("connected.");
      client.subscribe(MQTT_TOPIC_SUB);
      Serial.print("Subscrito a: ");
      Serial.println(MQTT_TOPIC_SUB);
    } else {
      Serial.println("Problema con la conexión, revise los valores de las constantes MQTT");
      int state = client.state();
      Serial.print("Código de error = ");
      alert = "MQTT error: " + String(state);
      Serial.println(state);

      if (client.state() == MQTT_CONNECT_UNAUTHORIZED) {
        ESP.deepSleep(0);
      }
      delay(5000);
    }
  }
}

void sendSensorData(float temperatura, float humedad) {
  String data = "{";
  data += "\"temperatura\": " + String(temperatura, 1) + ", ";
  data += "\"humedad\": " + String(humedad, 1);
  data += "}";

  char payload[data.length() + 1];
  data.toCharArray(payload, data.length() + 1);

  client.publish(MQTT_TOPIC_PUB, payload);
}

// =====================
//      SENSOR DHT
// =====================

float readTemperatura() {
  float t = dht.readTemperature();
  return t;
}

float readHumedad() {
  float h = dht.readHumidity();
  return h;
}

bool checkMeasures(float t, float h) {
  if (isnan(t) || isnan(h)) {
    Serial.println("Error obteniendo los datos del sensor DHT11");
    return false;
  }
  return true;
}

// =====================
//       DISPLAY
// =====================

void startDisplay() {
  // ESP8266 I2C: SDA=D2 (GPIO4), SCL=D1 (GPIO5)
  Wire.begin(D2, D1);
  Wire.setClock(100000);

  u8g2.begin();
}

void displayNoSignal() {
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB08_tr);
  u8g2.drawStr(10, 18, "No hay senal");
  u8g2.drawStr(10, 34, "WiFi/MQTT...");
  u8g2.sendBuffer();
}

void displayConnecting(const char* ssidName) {
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_6x12_tf);
  u8g2.drawStr(0, 14, "Connecting to:");
  u8g2.drawStr(0, 30, ssidName);
  u8g2.sendBuffer();
}

String getHourString() {
  long long int milli = now + millis() / 1000;
  struct tm* tinfo = localtime(&milli);
  String hour = String(asctime(tinfo)).substring(11, 19);
  return hour;
}

void renderScreen(const String& message) {
  u8g2.clearBuffer();

  // Header
  u8g2.setFont(u8g2_font_6x12_tf);
  String header = "IOT Sensors " + getHourString();
  u8g2.drawStr(0, 12, header.c_str());
  u8g2.drawHLine(0, 14, 128);

  // Medidas
  u8g2.setFont(u8g2_font_6x12_tf);

  char line1[32];
  char line2[32];

  // Formato con 1 decimal, evita strings gigantes
  if (!isnan(temp)) snprintf(line1, sizeof(line1), "T: %.1f C", temp);
  else snprintf(line1, sizeof(line1), "T: --.- C");

  if (!isnan(humi)) snprintf(line2, sizeof(line2), "H: %.1f %%", humi);
  else snprintf(line2, sizeof(line2), "H: --.- %%");

  u8g2.drawStr(0, 30, line1);
  u8g2.drawStr(0, 42, line2);

  // Mensaje / alerta
  u8g2.drawStr(0, 54, "Msg:");
  u8g2.setFont(u8g2_font_6x10_tf);

    if (message == "OK") {
    u8g2.drawStr(40, 54, "OK");
  } else {
    // recorta a lo que cabe (pantalla 128; "Evento: LED activado" = 21)
    String msg = message;
    if (msg.length() > 21) msg = msg.substring(0, 21);
    u8g2.drawStr(40, 54, msg.c_str());
  }

  u8g2.sendBuffer();
}

// =====================
//      ALERTAS MQTT
// =====================

String checkAlert() {
  String message = "OK";
  if (alert.length() != 0) {
    message = alert;
    if ((millis() - alertTime) >= (unsigned long)ALERT_DURATION * 1000UL) {
      alert = "";
      alertTime = millis();
    }
  }
  return message;
}

// Actualiza parpadeo del LED por evento y devuelve mensaje para OLED
String updateLedEventAndMessage() {
  if (!ledEventActive) return checkAlert();

  unsigned long elapsed = millis() - ledEventStartTime;
  if (elapsed >= (unsigned long)LED_EVENT_DURATION * 1000UL) {
    ledEventActive = false;
    digitalWrite(LED_PIN, LOW);   // LED off (D6: HIGH = on, LOW = off)
    return checkAlert();
  }

  if (millis() - ledBlinkLastToggle >= (unsigned long)LED_BLINK_MS) {
    ledBlinkLastToggle = millis();
    ledBlinkState = !ledBlinkState;
    digitalWrite(LED_PIN, ledBlinkState ? HIGH : LOW);  // D6: HIGH = encendido
  }
  return "Evento: LED activado";
}

void receivedCallback(char* topic, byte* payload, unsigned int length) {
  Serial.println("");
  Serial.println(">>> MENSAJE MQTT RECIBIDO <<<");
  Serial.print("Topic: ");
  Serial.println(topic);
  Serial.print("Payload: ");

  String data = "";
  for (unsigned int i = 0; i < length; i++) {
    data += (char)payload[i];
  }
  Serial.println(data);
  Serial.println("================================");
  Serial.println("");

  if (data.indexOf("ALERT") >= 0) {
    alert = data;
    alertTime = millis(); // importante: marca inicio de la alerta
  }

  if (data.indexOf("LED_ON") >= 0) {
    Serial.println("");
    Serial.println("*** EVENTO LED DETECTADO: temperatura_promedio > umbral ***");
    Serial.println("    -> LED parpadeando y OLED: Evento: LED activado");
    Serial.println("");
    ledEventActive = true;
    ledEventStartTime = millis();
    ledBlinkLastToggle = millis();
    ledBlinkState = false;
    digitalWrite(LED_PIN, LOW);   // apagado al inicio (D6: LOW = off)
  }

}

// =====================
//        WIFI
// =====================

void checkWiFi() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.print("Checking wifi");
    while (WiFi.waitForConnectResult() != WL_CONNECTED) {
      WiFi.begin(ssid, pass);
      Serial.print(".");
      displayNoSignal();
      delay(300);
    }
    Serial.println("connected");
  } else {
    if (!client.connected()) {
      mqtt_connect();
    } else {
      client.loop();
    }
  }
}

void listWiFiNetworks() {
  int numberOfNetworks = WiFi.scanNetworks();
  Serial.println("\nNumber of networks: ");
  Serial.println(numberOfNetworks);
  for (int i = 0; i < numberOfNetworks; i++) {
    Serial.println(WiFi.SSID(i));
  }
}

void startWiFi() {
  WiFi.hostname(USER);
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, pass);

  Serial.println("\nAttempting to connect to SSID: ");
  Serial.println(ssid);

  while (WiFi.status() != WL_CONNECTED) {
    Serial.print(".");
    delay(1000);
  }
  Serial.println("\nconnected!");
}

// =====================
//        TIME
// =====================

void setTime() {
  Serial.print("Setting time using SNTP");
  configTime(-5 * 3600, 0, "pool.ntp.org", "time.nist.gov");

  now = time(nullptr);
  while (now < 1510592825) {
    delay(500);
    Serial.print(".");
    now = time(nullptr);
  }
  Serial.println("done!");

  struct tm timeinfo;
  gmtime_r(&now, &timeinfo);
  Serial.print("Current time: ");
  Serial.println(asctime(&timeinfo));
}

// =====================
//        MQTT
// =====================

void configureMQTT() {
  client.setServer(MQTT_HOST, MQTT_PORT);
  client.setCallback(receivedCallback);
  mqtt_connect();
}

// =====================
//      MEASURES
// =====================

void measure() {
  if ((millis() - measureTime) >= (unsigned long)MEASURE_INTERVAL * 1000UL) {
    measureTime = millis();

    float t = readTemperatura();
    float h = readHumedad();

    if (checkMeasures(t, h)) {
      temp = t;
      humi = h;
      sendSensorData(temp, humi);
    }
  }
}

// =====================
//      ARDUINO
// =====================

void setup() {
  Serial.begin(115200);

  listWiFiNetworks();

  startDisplay();
  displayConnecting(ssid);

  startWiFi();

  dht.begin();

  setTime();

  configureMQTT();

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);    // LED apagado al inicio (D6)

  measureTime = millis();
  alertTime = millis();
}

void loop() {
  checkWiFi();
  String message = updateLedEventAndMessage();
  measure();
  renderScreen(message);
}
