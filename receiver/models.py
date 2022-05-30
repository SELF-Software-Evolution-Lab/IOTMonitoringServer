from django.db import models, IntegrityError
from django.db.models.fields import DateTimeField
from datetime import datetime, timedelta
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField
from typing import Any, MutableMapping, Optional
import psycopg2


class City(models.Model):
    name = models.CharField(max_length=50, unique=True, blank=False)
    code = models.CharField(max_length=50, null=True)

    def str(self):
        return "{}".format(self.name)


class State(models.Model):
    name = models.CharField(max_length=50, unique=False, blank=False)
    code = models.CharField(max_length=50, null=True)

    def str(self):
        return "{}".format(self.name)


class Country(models.Model):
    name = models.CharField(max_length=50, unique=False, blank=False)
    code = models.CharField(max_length=50, null=True)

    def str(self):
        return "{}".format(self.name)


class Location(models.Model):
    description = models.CharField(max_length=200, blank=True)
    lat = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True)
    lng = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True)
    city = models.ForeignKey(City, on_delete=models.CASCADE)
    state = models.ForeignKey(State, on_delete=models.CASCADE)
    country = models.ForeignKey(Country, on_delete=models.CASCADE)
    active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("city", "state", "country")

    def str(self):
        return "{} {} {}".format(self.city.name, self.state.name, self.country.name)


class Measurement(models.Model):
    name = models.CharField(max_length=50, blank=False)
    unit = models.CharField(max_length=50, blank=False)
    max_value = models.FloatField(null=True, blank=True, default=None)
    min_value = models.FloatField(null=True, blank=True, default=None)
    active = active = models.BooleanField(default=True)

    def str(self):
        return "{} {}".format(self.name, self.unit)


class Station(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, default=None)
    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, default=None)

    class Meta:
        unique_together = ("user", "location")

    last_activity = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)

    def str(self):
        return "%s %s %s" % (self.user, self.location, self.last_activity)


class DataQuerySet(models.query.QuerySet):

    def get_or_create(
        self, defaults: Optional[MutableMapping[str, Any]] = ..., **kwargs: Any,
    ):
        try:
            return (
                Data.objects.get(**kwargs),
                False,
            )
        except Data.DoesNotExist:
            kwargs.update(defaults or {})
            data = Data(
                **kwargs
            )
            data.save()
            return data, True


class DataManager(models.Manager):
    def get_queryset(self):
        return DataQuerySet(self.model)


class Data(models.Model):

    objects = DataManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["time", "base_time", "station_id", "measurement_id"],
                name="unique data measure",
            )
        ]

    def base_time_now():
        now = timezone.now()
        return datetime(now.year, now.month, now.day, now.hour, tzinfo=now.tzinfo)

    def timestamp_now():
        now = timezone.now()
        return int(now.timestamp() * 1000000)

    time = models.BigIntegerField(default=timestamp_now, primary_key=True)
    base_time = models.DateTimeField(default=base_time_now)
    station = models.ForeignKey(Station, on_delete=models.CASCADE)
    measurement = models.ForeignKey(Measurement, on_delete=models.CASCADE)
    min_value = models.FloatField(null=True, blank=True, default=None)
    max_value = models.FloatField(null=True, blank=True, default=None)
    length = models.IntegerField(default=0)
    avg_value = models.FloatField(null=True, blank=True, default=None)
    times = ArrayField(models.FloatField(), default=list)
    values = ArrayField(models.FloatField(), default=list)

    def save(self, *args, **kwargs):
        self.save_and_smear_timestamp(*args, **kwargs)

    def save_and_smear_timestamp(self, *args, **kwargs):
        """Intenta guardar recursivamente si hay colisión de exactamente el mismo timestamp y aumenta el timestamp en microsegundos hasta que no haya colisión"""
        try:
            super().save(*args, **kwargs)
        except IntegrityError as exception:
            # Solo maneja el error:
            #   psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint "procesor_data_time_pkey"
            #   DETAIL:  Key ("time")=(2020-10-01 22:33:52.507782+00) already exists.
            if all(k in exception.args[0] for k in ("time", "already exists")):
                # Incrementa el timestamp en 1 microsegundo hasta que no haya colisión
                self.time = self.time + 1
                self.save_and_smear_timestamp(*args, **kwargs)

    def __str__(self):
        return "Data: %s %s %s %s %s %s %s %s %s" % (
            str(self.time),
            str(self.station),
            str(self.measurement),
            str(self.min_value),
            str(self.max_value),
            str(self.length),
            str(self.avg_value),
            str(self.times),
            str(self.values),
        )

    def toDict(self):
        return {
            "station": str(self.station),
            "measurement": str(self.measurement),
            "times": self.times,
            "values": self.values,
            "base_time": self.base_time,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "avg_value": self.avg_value,
        }
