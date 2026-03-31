"""
Comando para verificar si hay datos de temperatura y si se dispararía el evento LED.
Uso: python manage.py check_led_event
      python manage.py check_led_event --send          # envía LED_ON si temp > umbral
      python manage.py check_led_event --send --force # envía LED_ON sin importar la temperatura (prueba)

El comando usa un client_id distinto al de start_control para no desconectar el broker.
"""
import time
import paho.mqtt.client as mqtt
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Avg
from datetime import timedelta, datetime
from django.utils import timezone
from receiver.models import Data, Station

from control.monitor import LED_EVENT_TEMP_THRESHOLD, evaluate_led_event


def send_led_on_to_topics(topics):
    """
    Envía LED_ON a los tópicos usando un cliente MQTT propio (client_id distinto a start_control).
    Así no se desconecta el proceso start_control que ya está corriendo.
    """
    client_id = settings.MQTT_USER_PUB + "_check_led"
    c = mqtt.Client(client_id=client_id)
    c.username_pw_set(settings.MQTT_USER_PUB, settings.MQTT_PASSWORD_PUB)
    c.connect(settings.MQTT_HOST, settings.MQTT_PORT, keepalive=60)
    c.loop_start()
    time.sleep(1)  # dar tiempo a conectar
    for topic in topics:
        c.publish(topic, 'LED_ON')
    time.sleep(0.5)
    c.loop_stop()
    c.disconnect()


def get_topics_from_db():
    """Obtiene los tópicos in de todas las estaciones (para enviar LED_ON)."""
    stations = Station.objects.select_related(
        'user', 'location', 'location__city', 'location__state', 'location__country'
    ).filter(active=True)
    topics = []
    for s in stations:
        topic = '{}/{}/{}/{}/in'.format(
            s.location.country.name,
            s.location.state.name,
            s.location.city.name,
            s.user.username,
        )
        topics.append(topic)
    return topics


class Command(BaseCommand):
    help = 'Verifica datos de temperatura y opcionalmente envía LED_ON (--send). Use --send --force para probar sin esperar 22°C.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--send',
            action='store_true',
            help='Enviar LED_ON (si temp > umbral o si usa --force)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Enviar LED_ON a todas las estaciones sin comprobar temperatura (solo para prueba)',
        )

    def handle(self, *args, **options):
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

        if not aggregation and not options['force']:
            self.stdout.write(
                self.style.WARNING(
                    'No hay datos de temperatura en la última hora. '
                    '¿El receptor (start_mqtt) está corriendo y el dispositivo publicando?'
                )
            )
            if options['send'] and options['force']:
                topics = get_topics_from_db()
                if not topics:
                    self.stdout.write(self.style.WARNING('No hay estaciones en la BD. Publique algo desde el dispositivo primero.'))
                    return
                self.stdout.write('Enviando LED_ON (--force) a: ' + ', '.join(topics))
                send_led_on_to_topics(topics)
                self.stdout.write(self.style.SUCCESS('LED_ON enviado. Revisa el NodeMCU.'))
            return

        if aggregation:
            self.stdout.write('Umbral para LED: {} °C\n'.format(LED_EVENT_TEMP_THRESHOLD))
            for item in aggregation:
                temp = item.get('temperatura_promedio')
                topic = '{}/{}/{}/{}/in'.format(
                    item['station__location__country__name'],
                    item['station__location__state__name'],
                    item['station__location__city__name'],
                    item['station__user__username'],
                )
                dispara = temp is not None and temp > LED_EVENT_TEMP_THRESHOLD
                self.stdout.write(
                    '  {} | temp_prom = {:.1f} °C | ¿Dispara LED? {}'.format(
                        topic, temp or 0, 'Sí' if dispara else 'No'
                    )
                )

        if options['send']:
            self.stdout.write('')
            if options['force']:
                topics = get_topics_from_db() if not aggregation else [
                    '{}/{}/{}/{}/in'.format(
                        item['station__location__country__name'],
                        item['station__location__state__name'],
                        item['station__location__city__name'],
                        item['station__user__username'],
                    )
                    for item in aggregation
                ]
                send_led_on_to_topics(topics)
                self.stdout.write(self.style.SUCCESS('LED_ON enviado (--force) a {} tópico(s). Revisa el NodeMCU.'.format(len(topics))))
            else:
                from control import monitor
                monitor.setup_mqtt()
                evaluate_led_event()
                self.stdout.write(self.style.SUCCESS('Listo. Si había temp > umbral, se envió LED_ON. Revisa el NodeMCU (Serial/OLED/LED).'))
