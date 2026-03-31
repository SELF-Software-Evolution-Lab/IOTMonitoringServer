from argparse import ArgumentError
import ssl
from django.db.models import Avg
from datetime import timedelta, datetime
from django.utils import timezone
from receiver.models import Data, Measurement
import paho.mqtt.client as mqtt
import schedule
import time
from django.conf import settings

# Client ID único para no chocar con el receptor (admin/admin2 en el broker)
client = mqtt.Client(client_id=settings.MQTT_USER_PUB + "_control")
mqtt_connected = False


def analyze_data():
    # Consulta todos los datos de la última hora, los agrupa por estación y variable
    # Compara el promedio con los valores límite que están en la base de datos para esa variable.
    # Si el promedio se excede de los límites, se envia un mensaje de alerta.

    print("Calculando alertas...")

    data = Data.objects.filter(
        base_time__gte=timezone.now() - timedelta(hours=1))
    aggregation = data.annotate(check_value=Avg('avg_value')) \
        .select_related('station', 'measurement') \
        .select_related('station__user', 'station__location') \
        .select_related('station__location__city', 'station__location__state',
                        'station__location__country') \
        .values('check_value', 'station__user__username',
                'measurement__name',
                'measurement__max_value',
                'measurement__min_value',
                'station__location__city__name',
                'station__location__state__name',
                'station__location__country__name')
    alerts = 0
    for item in aggregation:
        alert = False

        variable = item["measurement__name"]
        max_value = item["measurement__max_value"] or 0
        min_value = item["measurement__min_value"] or 0

        country = item['station__location__country__name']
        state = item['station__location__state__name']
        city = item['station__location__city__name']
        user = item['station__user__username']

        if item["check_value"] > max_value or item["check_value"] < min_value:
            alert = True

        if alert:
            message = "ALERT {} {} {}".format(variable, min_value, max_value)
            topic = '{}/{}/{}/{}/in'.format(country, state, city, user)
            if not mqtt_connected:
                try:
                    client.reconnect()
                    time.sleep(1)
                except Exception as e:
                    print("Reconnect falló:", e)
            if mqtt_connected:
                client.publish(topic, message)
                print(timezone.now(), "Sending alert to {} {}".format(topic, variable))
            else:
                print(timezone.now(), "NO enviado (desconectado): alert a", topic)
            alerts += 1

    print(len(aggregation), "dispositivos revisados")
    print(alerts, "alertas enviadas")


# Umbral de temperatura (ºC) para activar el evento LED
LED_EVENT_TEMP_THRESHOLD = 22.0


def evaluate_led_event():
    """
    Nuevo evento: si temperatura_promedio (última hora, por estación) > umbral,
    se envía LED_ON al dispositivo. La temperatura_promedio se obtiene por consulta a la BD.
    Acción: el dispositivo parpadea el LED y muestra "Evento: LED activado" en la OLED.
    """
    print("Evaluando evento LED (temperatura_promedio > {} °C)...".format(LED_EVENT_TEMP_THRESHOLD))

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

    sent = 0
    for item in aggregation:
        temp_prom = item.get('temperatura_promedio')
        if temp_prom is not None and temp_prom > LED_EVENT_TEMP_THRESHOLD:
            country = item['station__location__country__name']
            state = item['station__location__state__name']
            city = item['station__location__city__name']
            user = item['station__user__username']
            topic = '{}/{}/{}/{}/in'.format(country, state, city, user)
            if not mqtt_connected:
                try:
                    client.reconnect()
                    time.sleep(1)
                except Exception as e:
                    print("Reconnect falló:", e)
            if mqtt_connected:
                client.publish(topic, 'LED_ON')
                print(timezone.now(), "LED_ON enviado a", topic, "(temperatura_promedio = {:.1f} °C)".format(temp_prom))
                sent += 1
            else:
                print(timezone.now(), "NO enviado LED_ON (desconectado):", topic)

    print(sent, "comandos LED_ON enviados")


def on_connect(client, userdata, flags, rc):
    '''
    Función que se ejecuta cuando se conecta al bróker.
    '''
    global mqtt_connected
    if rc == 0:
        mqtt_connected = True
        print("Conectado al broker MQTT correctamente.")
    else:
        mqtt_connected = False
        print("Error al conectar al broker MQTT:", mqtt.connack_string(rc))


def on_disconnect(client: mqtt.Client, userdata, rc):
    '''
    Función que se ejecuta cuando se desconecta del broker.
    '''
    global mqtt_connected
    mqtt_connected = False
    print("Desconectado del broker:", mqtt.connack_string(rc))


def setup_mqtt():
    '''
    Configura el cliente MQTT y se conecta al broker. Usa loop_start() para
    mantener la conexión en un hilo en segundo plano.
    '''
    global client, mqtt_connected
    mqtt_connected = False
    print("Iniciando cliente MQTT...", settings.MQTT_HOST, settings.MQTT_PORT)
    try:
        client = mqtt.Client(client_id=settings.MQTT_USER_PUB + "_control")
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect

        if settings.MQTT_USE_TLS:
            client.tls_set(ca_certs=settings.CA_CRT_PATH,
                           tls_version=ssl.PROTOCOL_TLSv1_2, cert_reqs=ssl.CERT_NONE)

        client.username_pw_set(settings.MQTT_USER_PUB,
                               settings.MQTT_PASSWORD_PUB)
        client.connect(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=60)
        # Mantener la conexión en un hilo (importante: sin esto la conexión se pierde)
        client.loop_start()
        # Dar tiempo a que on_connect se ejecute
        for _ in range(20):
            if mqtt_connected:
                break
            time.sleep(0.5)
        if not mqtt_connected:
            print("Aviso: conexión MQTT aún no confirmada. ¿El broker acepta usuario", settings.MQTT_USER_PUB, "? ¿La EC2 puede alcanzar", settings.MQTT_HOST, ":", settings.MQTT_PORT, "?")
    except Exception as e:
        print('Error al conectar con el bróker MQTT:', e)


def start_cron():
    '''
    Inicia el cron: analyze_data y evaluate_led_event cada 2 minutos.
    '''
    print("Iniciando cron...")
    schedule.every(2).minutes.do(analyze_data)
    schedule.every(2).minutes.do(evaluate_led_event)
    print("Servicio de control iniciado (eventos cada 2 min)")
    while 1:
        if not mqtt_connected:
            try:
                client.reconnect()
                time.sleep(1)
            except Exception:
                pass
        schedule.run_pending()
        time.sleep(1)
