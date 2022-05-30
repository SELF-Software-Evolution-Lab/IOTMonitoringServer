from django.contrib import admin

from receiver.models import City, State, Country, Location, Station, Measurement, Data

admin.site.register(City)
admin.site.register(State)
admin.site.register(Country)
admin.site.register(Location)
admin.site.register(Station)
admin.site.register(Measurement)
admin.site.register(Data)
