from datetime import datetime
from . import utils
import json
import os
import ssl
import paho.mqtt.client as mqtt
from django.conf import settings


def on_message(client: mqtt.Client, userdata, message: mqtt.MQTTMessage):
    '''
    Función que se ejecuta cada que llega un mensaje al tópico.
    Recibe el mensaje con formato:
        {
            "variable1": mediciónVariable1,
            "variable2": mediciónVariable2
        }
    en un tópico con formato:
        pais/estado/ciudad/usuario
        ej: colombia/cundinamarca/cajica/ja.avelino
    Si el tópico tiene la forma de:
        pais/estado/ciudad/usuario/mensaje
    se salta el procesamiento pues el mensaje es para el dispositivo de medición.
    A partir de esos datos almacena la medición en el sistema.
    '''
    try:
        time = datetime.now()
        payload = message.payload.decode("utf-8")
        print("payload: " + payload)
        payloadJson = json.loads(payload)
        country, state, city, user = utils.get_topic_data(
            message.topic)

        user_obj = utils.get_user(user)
        location_obj = utils.get_or_create_location(city, state, country)

        for measure in payloadJson:
            variable = measure
            unit = utils.get_units(str(variable).lower())
            variable_obj = utils.get_or_create_measurement(variable, unit)
            sensor_obj = utils.get_or_create_station(user_obj, location_obj)
            utils.create_data(
                float(payloadJson[measure]), sensor_obj, variable_obj, time)

    except Exception as e:
        print('Ocurrió un error procesando el paquete MQTT', e)


def on_connect(client, userdata, flags, rc):
    print("Suscribiendo al tópico: " + settings.TOPIC)
    client.subscribe(settings.TOPIC)
    print("Servicio de recepcion de datos iniciado")


def on_disconnect(client: mqtt.Client, userdata, rc):
    '''
    Función que se ejecuta cuando se desconecta del broker.
    Intenta reconectar al bróker.
    '''
    print("Desconectado con mensaje:" + str(mqtt.connack_string(rc)))
    print("Reconectando...")
    client.reconnect()


print("Iniciando cliente MQTT...", settings.MQTT_HOST, settings.MQTT_PORT)
try:
    client = mqtt.Client(settings.MQTT_USER)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    if settings.MQTT_USE_TLS:
        client.tls_set(ca_certs=settings.CA_CRT_PATH,
                       tls_version=ssl.PROTOCOL_TLSv1_2, cert_reqs=ssl.CERT_NONE)

    client.username_pw_set(settings.MQTT_USER, settings.MQTT_PASSWORD)
    client.connect(settings.MQTT_HOST, settings.MQTT_PORT)

except Exception as e:
    print('Ocurrió un error al conectar con el bróker MQTT:', e)
