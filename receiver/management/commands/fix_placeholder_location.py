"""
Corrige ubicaciones que tienen los placeholders "ciudad", "estado", "pais":
reasigna sus estaciones a la Location real (bogota, cundinamarca, colombia) y elimina la placeholder.
Si la Location real no existe, la crea.

Uso:
  python manage.py fix_placeholder_location
  python manage.py fix_placeholder_location --city bogota --state cundinamarca --country colombia
"""
from django.core.management.base import BaseCommand
from receiver.models import Location, City, State, Country
from receiver.utils import get_coordinates


class Command(BaseCommand):
    help = 'Reasigna estaciones de ciudad/estado/pais a la ubicación real (ej. bogota, cundinamarca, colombia)'

    def add_arguments(self, parser):
        parser.add_argument('--city', default='bogota', help='Nombre de ciudad (default: bogota)')
        parser.add_argument('--state', default='cundinamarca', help='Nombre de estado/departamento (default: cundinamarca)')
        parser.add_argument('--country', default='colombia', help='Nombre de país (default: colombia)')

    def handle(self, *args, **options):
        city_name = options['city']
        state_name = options['state']
        country_name = options['country']

        placeholder_locations = Location.objects.filter(
            city__name='ciudad',
            state__name='estado',
            country__name='pais'
        ).select_related('city', 'state', 'country')

        if not placeholder_locations.exists():
            self.stdout.write(self.style.WARNING('No hay ubicaciones con "ciudad, estado, pais". Nada que corregir.'))
            return

        city_o, _ = City.objects.get_or_create(name=city_name, defaults={})
        state_o, _ = State.objects.get_or_create(name=state_name, defaults={})
        country_o, _ = Country.objects.get_or_create(name=country_name, defaults={})

        # Location real (donde deben quedar las estaciones)
        real_location, created = Location.objects.get_or_create(
            city=city_o, state=state_o, country=country_o,
            defaults={'active': True}
        )
        if created:
            try:
                lat, lng = get_coordinates(city_name, state_name, country_name)
                if lat and lng:
                    real_location.lat = lat
                    real_location.lng = lng
                    real_location.save()
            except Exception as e:
                self.stdout.write(self.style.WARNING('Coordenadas no actualizadas: {}'.format(e)))
            self.stdout.write('Creada Location {}, {}, {}'.format(city_name, state_name, country_name))

        # Reasignar todas las estaciones de las placeholder locations a la Location real
        from receiver.models import Station, Data
        moved = 0
        for loc in placeholder_locations:
            stations = Station.objects.filter(location=loc)
            for st in stations:
                existing = Station.objects.filter(user=st.user, location=real_location).first()
                if existing:
                    # El usuario ya tiene estación en la Location real: mover los Data a esa estación y borrar la duplicada
                    Data.objects.filter(station=st).update(station=existing)
                    st.delete()
                    self.stdout.write('Estación id={} (user={}) fusionada en estación id={}'.format(st.pk, st.user.username, existing.pk))
                else:
                    st.location = real_location
                    st.save()
                    self.stdout.write('Estación id={} (user={}) -> {}, {}, {}'.format(
                        st.pk, st.user.username, city_name, state_name, country_name))
                moved += 1
            loc.delete()
            self.stdout.write('Eliminada Location placeholder id={}'.format(loc.pk))

        # Borrar City/State/Country placeholder si ya no los usa nadie
        old_city = City.objects.filter(name='ciudad').first()
        old_state = State.objects.filter(name='estado').first()
        old_country = Country.objects.filter(name='pais').first()
        if old_city and not Location.objects.filter(city=old_city).exists():
            old_city.delete()
            self.stdout.write('Eliminada City "ciudad"')
        if old_state and not Location.objects.filter(state=old_state).exists():
            old_state.delete()
            self.stdout.write('Eliminado State "estado"')
        if old_country and not Location.objects.filter(country=old_country).exists():
            old_country.delete()
            self.stdout.write('Eliminado Country "pais"')

        self.stdout.write(self.style.SUCCESS('Listo. {} estación(es) reasignada(s) a {}, {}, {}. Recarga el mapa.'.format(moved, city_name, state_name, country_name)))
