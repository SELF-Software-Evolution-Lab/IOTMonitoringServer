from . import utils
import json
from django.utils import timezone
import ssl
import paho.mqtt.client as mqtt
from django.conf import settings


def on_message(client: mqtt.Client, userdata, message: mqtt.MQTTMessage):
    """
    Función que se ejecuta cada que llega un mensaje al tópico.
    """
    try:
        time = timezone.now()
        payload = message.payload.decode("utf-8")
        print("Payload recibido:", payload)

        payloadJson = json.loads(payload)
        country, state, city, user = utils.get_topic_data(message.topic)

        user_obj = utils.get_user(user)
        location_obj = utils.get_or_create_location(city, state, country)

        for measure in payloadJson:
            variable = measure
            unit = utils.get_units(str(variable).lower())
            variable_obj = utils.get_or_create_measurement(variable, unit)
            sensor_obj = utils.get_or_create_station(user_obj, location_obj)

            utils.create_data(
                float(payloadJson[measure]),
                sensor_obj,
                variable_obj,
                time
            )

    except Exception as e:
        print("❌ Error procesando mensaje MQTT:", e)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ Conectado al broker")
        print("Suscribiendo al tópico:", settings.TOPIC)
        client.subscribe(settings.TOPIC)
        print("Servicio de recepción de datos iniciado")
    else:
        print("❌ Error de conexión:", mqtt.connack_string(rc))


def on_disconnect(client, userdata, rc):
    print("⚠️ Desconectado:", mqtt.connack_string(rc))
    print("Intentando reconectar...")


print("🚀 Iniciando cliente MQTT...", settings.MQTT_HOST, settings.MQTT_PORT)

try:
    # ✅ MQTT TCP normal (Mosquitto en 8082 sin websockets)
    client = mqtt.Client(client_id=settings.MQTT_USER)

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    if settings.MQTT_USE_TLS:
        client.tls_set(
            ca_certs=settings.CA_CRT_PATH,
            tls_version=ssl.PROTOCOL_TLSv1_2,
            cert_reqs=ssl.CERT_NONE
        )

    client.username_pw_set(settings.MQTT_USER, settings.MQTT_PASSWORD)
    client.connect(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=60)

    # Loop bloqueante (mantiene conexión viva)
    client.loop_forever()

except Exception as e:
    print("❌ Error conectando al broker MQTT:", e)