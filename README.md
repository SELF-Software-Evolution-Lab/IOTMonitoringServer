# Reto: Procesamiento de eventos con consulta a BD y actuador

**Repositorio:** https://github.com/HectorFranco-MISO/IOTMonitoringServer

---

## 1. Objetivo del reto

Se modificó el código del tutorial de la capa de aplicación (lógica) para agregar el **procesamiento de un nuevo evento** que cumple:

- **Condición:** con pre-requisito de **consulta a la base de datos** (temperatura promedio por estación en la última hora).
- **Acción:** ejecutada por un **actuador del dispositivo IoT** (LED en protoboard + mensaje en pantalla OLED).

---

## 2. Descripción del nuevo evento

| Aspecto | Descripción |
|--------|-------------|
| **Condición** | Si la **temperatura promedio** (última hora, por estación) es **mayor a 22 °C**. El valor de temperatura promedio se obtiene mediante una consulta a la base de datos. |
| **Acción** | El servidor envía el comando `LED_ON` por MQTT al dispositivo. El dispositivo **parpadea un LED** conectado en D6 y muestra en la **OLED** el mensaje *"Evento: LED activado"* durante 60 segundos. |
| **Frecuencia** | La evaluación se ejecuta cada 2 minutos (junto con el resto del servicio de control). |

---

## 3. Modificaciones realizadas

### 3.1 Servidor (capa de aplicación) — `control/monitor.py`

Se agregó un **nuevo evento** independiente del de alertas ya existente:

1. **Umbral y función del evento LED**

La condición usa un umbral de temperatura (en °C) y una función que consulta la BD y publica `LED_ON` cuando se cumple la condición:

```python
# Umbral de temperatura (ºC) para activar el evento LED
LED_EVENT_TEMP_THRESHOLD = 22.0

def evaluate_led_event():
    """
    Nuevo evento: si temperatura_promedio (última hora, por estación) > umbral,
    se envía LED_ON al dispositivo. La temperatura_promedio se obtiene por consulta a la BD.
    Acción: el dispositivo parpadea el LED y muestra "Evento: LED activado" en la OLED.
    """
    # ...
```

2. **Consulta a la base de datos (pre-requisito de la condición)**

La **temperatura promedio** se obtiene con una consulta al modelo `Data`, filtrando por la última hora y por la medición `temperatura`, agrupando por estación y calculando el promedio de `avg_value`:

```python
    # Consulta a la BD: promedio de temperatura por estación en la última hora
    data = Data.objects.filter(
        base_time__gte=timezone.now() - timedelta(hours=1),
        measurement__name='temperatura'
    )
    aggregation = data.values(
        'station__user__username',
        'station__location__city__name',
        'station__location__state__name',
        'station__location__country__name'
    ).annotate(temperatura_promedio=Avg('avg_value'))
```

3. **Evaluación de la condición y envío de la acción**

Se recorre la agregación y, para cada estación cuyo `temperatura_promedio` supere el umbral, se publica `LED_ON` en el tópico MQTT de entrada del dispositivo:

```python
    for item in aggregation:
        temp_prom = item.get('temperatura_promedio')
        if temp_prom is not None and temp_prom > LED_EVENT_TEMP_THRESHOLD:
            # ... arma topic desde item ...
            if mqtt_connected:
                client.publish(topic, 'LED_ON')
                # ...
```

4. **Programación en el cron**

La función del nuevo evento se ejecuta periódicamente junto con el análisis de alertas:

```python
    schedule.every(2).minutes.do(analyze_data)
    schedule.every(2).minutes.do(evaluate_led_event)
```

---

### 3.2 Dispositivo (sketch) — `IOTDeviceScript.ino`

1. **Definiciones para el actuador LED y duración del evento**

```cpp
#define LED_PIN 12          // D6 en NodeMCU (LED externo en protoboard: D6 y GND)
#define LED_EVENT_DURATION 60  // segundos que parpadea el LED
#define LED_BLINK_MS 400    // intervalo de parpadeo en ms
```

2. **Variables de estado del evento LED**

```cpp
// Evento LED (parpadeo + mensaje en OLED)
bool ledEventActive = false;
unsigned long ledEventStartTime = 0;
unsigned long ledBlinkLastToggle = 0;
bool ledBlinkState = false;
```

3. **Recepción del comando MQTT y activación del evento**

En el callback de MQTT, si el mensaje contiene `LED_ON`, se activa el evento (parpadeo + mensaje en OLED):

```cpp
  if (data.indexOf("LED_ON") >= 0) {
    Serial.println("*** EVENTO LED DETECTADO: temperatura_promedio > umbral ***");
    ledEventActive = true;
    ledEventStartTime = millis();
    ledBlinkLastToggle = millis();
    ledBlinkState = false;
    digitalWrite(LED_PIN, LOW);   // apagado al inicio (D6: LOW = off)
  }
```

4. **Lógica del parpadeo y mensaje para la OLED**

En cada iteración del `loop`, se actualiza el estado del LED y se elige el mensaje que se envía a la pantalla; mientras el evento está activo se devuelve *"Evento: LED activado"* y se hace parpadear el LED:

```cpp
// Actualiza parpadeo del LED por evento y devuelve mensaje para OLED
String updateLedEventAndMessage() {
  if (!ledEventActive) return checkAlert();

  unsigned long elapsed = millis() - ledEventStartTime;
  if (elapsed >= (unsigned long)LED_EVENT_DURATION * 1000UL) {
    ledEventActive = false;
    digitalWrite(LED_PIN, LOW);
    return checkAlert();
  }

  if (millis() - ledBlinkLastToggle >= (unsigned long)LED_BLINK_MS) {
    ledBlinkLastToggle = millis();
    ledBlinkState = !ledBlinkState;
    digitalWrite(LED_PIN, ledBlinkState ? HIGH : LOW);  // D6: HIGH = encendido
  }
  return "Evento: LED activado";
}
```

5. **Uso en `setup` y `loop`**

En `setup` se configura el pin del LED como salida y estado inicial:

```cpp
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);    // LED apagado al inicio (D6)
```

En `loop` se usa el mensaje devuelto por `updateLedEventAndMessage()` para actualizar la pantalla:

```cpp
void loop() {
  checkWiFi();
  String message = updateLedEventAndMessage();
  measure();
  renderScreen(message);
}
```

---

## 4. Configuración física (NodeMCU, protoboard y actuadores)

---

### 4.1 Conexiones utilizadas

| Componente | Conexión en NodeMCU |
|------------|---------------------|
| DHT11      | GND, 3V3, D4 (datos) |
| OLED       | D1 (SCL), D2 (SDA), 3V3, GND |
| LED        | D6 (ánodo con resistencia ~220Ω) y GND |

