from datetime import datetime
import traceback
from django.contrib.auth.models import User
from receiver.models import Measurement, Station, Data, Location, City, State, Country
from receiver.utils import get_coordinates
from django.db.models import Avg, Max, Min, Sum
import dateutil.relativedelta


def get_measurements():
    measurements = Measurement.objects.all()
    return list(measurements)


def get_data_user_for_location(city, state, country, request_user):
    """
    Devuelve el username a usar para get_last_week_data en esa ubicación.
    Si el usuario tiene estación ahí, es él; si no pero es superuser, el dueño de cualquier estación ahí.
    """
    try:
        cityO = City.objects.get(name=city)
        stateO = State.objects.get(name=state)
        countryO = Country.objects.get(name=country)
        location = Location.objects.get(city=cityO, state=stateO, country=countryO)
    except Exception:
        return request_user.username
    station = Station.objects.filter(user=request_user, location=location).first()
    if station:
        return request_user.username
    if request_user.is_superuser:
        any_station = Station.objects.filter(location=location, active=True).select_related('user').first()
        if any_station:
            return any_station.user.username
    return request_user.username


def get_last_week_data(user, city, state, country):
    result = {}
    start = datetime.now()
    start = start - dateutil.relativedelta.relativedelta(days=1)
    try:
        userO = User.objects.get(username=user)
        location = None
        try:
            cityO = City.objects.get(name=city)
            stateO = State.objects.get(name=state)
            countryO = Country.objects.get(name=country)
            location = Location.objects.get(
                city=cityO, state=stateO, country=countryO
            )
        except:
            print("Specified location does not exist")
        print("LAST_WEEK: Got user and lcoation:",
              user, city, state, country)
        if userO == None or location == None:
            raise "No existe el usuario o ubicación indicada"
        stationO = Station.objects.get(user=userO, location=location)
        print("LAST_WEEK: Got station:", user, location, stationO)
        if stationO == None:
            raise "No hay datos para esa ubicación"
        measurementsO = get_measurements()
        print("LAST_WEEK: Measurements got: ", measurementsO)
        for measure in measurementsO:
            print("LAST_WEEK: Filtering measure: ", measure)
            # time__gte=start.date() Filtro para último día
            start_ts = int(start.timestamp() * 1000000)
            raw_data = Data.objects.filter(
                station=stationO, time__gte=start_ts, measurement=measure
            ).order_by("-base_time")[:2]
            print("LAST_WEEK: Raw data: ", len(raw_data))
            data = []
            for reg in raw_data:
                values = reg.values
                times = reg.times
                print("Len vals: ", len(values), "Len times: ", len(times))
                for i in range(len(values)):
                    data.append(
                        (
                            ((reg.base_time.timestamp() +
                             times[i]) * 1000 // 1),
                            values[i],
                        )
                    )

            minVal = raw_data.aggregate(Min("min_value"))["min_value__min"]
            maxVal = raw_data.aggregate(Max("max_value"))["max_value__max"]
            avgVal = sum(reg.avg_value * reg.length for reg in raw_data) / sum(
                reg.length for reg in raw_data
            )
            result[measure.name] = {
                "min": minVal if minVal != None else 0,
                "max": maxVal if maxVal != None else 0,
                "avg": round(avgVal if avgVal != None else 0, 2),
                "data": data,
            }
    except Exception as error:
        print("Error en consulta de datos:", error)
        traceback.print_exc()

    return result, measurementsO


def get_realtime_context(request):
    """
Se procesan los datos para cargar el contexto del template.
El template espera un contexto de este tipo:
{
    "data": {
        "temperatura": {
            "min": float,
            "max": float,
            "avg": float,
            "data": [
                (timestamp1, medición1),
                (timestamp2, medición2),
                (timestamp3, medición3),
                ...
            ]
        },
        "variable2" : {min,max,avg,data},
        ...
    },
    "measurements": [Measurement0, Measurement1, ...],
    "selectedCity": City,
    "selectedState": State,
    "selectedCountry": Country,
    "selectedLocation": Location
}
"""
    context = {}
    print("CONTEXT: getting context data")
    try:
        userParam = request.user.username
        cityParam = request.GET.get("city", None)
        stateParam = request.GET.get("state", None)
        countryParam = request.GET.get("country", None)
        print(
            "CONTEXT: getting user, city, state, country: ",
            userParam,
            cityParam,
            stateParam,
            countryParam,
        )
        if not cityParam and not stateParam and not countryParam:
            user = User.objects.get(username=userParam)
            print("CONTEXT: getting user db: ", user)
            stations = Station.objects.filter(user=user)
            # Si el usuario no tiene estaciones pero es superuser, usar la primera estación disponible (ej. ironman)
            if not stations.exists() and user.is_superuser:
                first_station = Station.objects.filter(active=True).select_related('location').first()
                if first_station:
                    stations = Station.objects.filter(pk=first_station.pk)
            print("CONTEXT: getting stations db: ", stations)
            station = stations.first()
            print("CONTEXT: getting first station: ", station)
            if station != None:
                cityParam = station.location.city.name
                stateParam = station.location.state.name
                countryParam = station.location.country.name
                data_user = station.user.username  # datos de quien tenga la estación (ej. ironman)
            else:
                return context
        else:
            data_user = userParam
        print("CONTEXT: getting last week data and measurements")
        context["data"], context["measurements"] = get_last_week_data(
            data_user, cityParam, stateParam, countryParam
        )
        print(
            "CONTEXT: got last week data, now getting city, state, country: ",
            cityParam,
            stateParam,
            countryParam,
        )
        context["selectedCity"] = City.objects.get(name=cityParam)
        context["selectedState"] = State.objects.get(name=stateParam)
        context["selectedCountry"] = Country.objects.get(name=countryParam)
        context["selectedLocation"] = Location.objects.get(
            city=context["selectedCity"],
            state=context["selectedState"],
            country=context["selectedCountry"],
        )
    except Exception as e:
        print("Error get_context_data. User: " + userParam, e)
    return context


def get_map_context(request):
    context = {}

    measureParam = request.GET.get("measure", None)
    selectedMeasure = None
    measurements = Measurement.objects.all()

    if measureParam != None:
        selectedMeasure = Measurement.objects.filter(name=measureParam)[0]
    elif measurements.count() > 0:
        selectedMeasure = measurements[0]

    locations = Location.objects.all()
    try:
        start = datetime.fromtimestamp(
            float(request.GET.get("from", None)) / 1000
        )
    except:
        start = None
    try:
        end = datetime.fromtimestamp(
            float(request.GET.get("to", None)) / 1000)
    except:
        end = None
    if start == None and end == None:
        start = datetime.now()
        start = start - dateutil.relativedelta.relativedelta(weeks=1)
        end = datetime.now()
        end += dateutil.relativedelta.relativedelta(days=1)
    elif end == None:
        end = datetime.now()
    elif start == None:
        start = datetime.fromtimestamp(0)

    data = []

    start_ts = int(start.timestamp() * 1000000)
    end_ts = int(end.timestamp() * 1000000)

    for location in locations:
        stations = Station.objects.filter(location=location)
        if not selectedMeasure:
            continue
        locationData = Data.objects.filter(
            station__in=stations, measurement__name=selectedMeasure.name, time__gte=start_ts, time__lte=end_ts,
        )
        if locationData.count() <= 0:
            continue
        minVal = locationData.aggregate(Min("min_value"))["min_value__min"]
        maxVal = locationData.aggregate(Max("max_value"))["max_value__max"]
        avgVal = locationData.aggregate(Avg("avg_value"))["avg_value__avg"]
        lat = location.lat
        lng = location.lng
        if lat is None or lng is None:
            try:
                lat, lng = get_coordinates(
                    location.city.name, location.state.name, location.country.name
                )
                if lat and lng:
                    location.lat = lat
                    location.lng = lng
                    location.save()
            except Exception:
                pass
        if lat is None or lng is None:
            continue
        data.append(
            {
                "name": f"{location.city.name}, {location.state.name}, {location.country.name}",
                "lat": float(lat),
                "lng": float(lng),
                "population": stations.count(),
                "min": minVal if minVal is not None else 0,
                "max": maxVal if maxVal is not None else 0,
                "avg": round(float(avgVal) if avgVal is not None else 0, 2),
            }
        )

    startFormatted = start.strftime("%d/%m/%Y") if start != None else " "
    endFormatted = end.strftime("%d/%m/%Y") if end != None else " "

    context["measurements"] = measurements
    context["selectedMeasure"] = selectedMeasure
    context["locations"] = locations
    context["start"] = startFormatted
    context["end"] = endFormatted
    context["data"] = data

    return context
