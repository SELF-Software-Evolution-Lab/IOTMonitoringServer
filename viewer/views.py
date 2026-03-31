import json
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.contrib.auth import login
from .forms import MeasurementForm, NewUserForm, NewVariableForm
from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from receiver.models import Measurement
from . import filters, utils

'''
    Vistas:
    1. Login
    2. Logout
    3. Home: Descripción?
    4. Datos en tiempo real (para admin igual que usuario normal)
    5. Mapa histórico (Todos)
    6. Descarga de datos (Todos)
    7. Usuarios (Admin)
    8. Variables (Admin)
'''
from django.http import HttpResponse, HttpResponsePermanentRedirect, HttpResponseRedirect, JsonResponse
from django.utils import timezone
from receiver.models import Data
import dateutil.relativedelta
from datetime import datetime
import csv
import io


@login_required
def index(request):
    return render(request, 'home.html')


@login_required
@csrf_exempt
def realtime_data(request):
    if request.method == 'POST':
        data = {}
        try:
            body = json.loads(request.body.decode("utf-8"))
            action = body["action"]
            print("action:", action)
            userParam = request.user.username
            if action == "get_data":
                cityName = body["city"]
                stateName = body["state"]
                countryName = body["country"]
                data_user = utils.get_data_user_for_location(
                    cityName, stateName, countryName, request.user
                )
                data["result"], measurement = utils.get_last_week_data(
                    data_user, cityName, stateName, countryName
                )
            else:
                data["error"] = "Ha ocurrido un error"
        except Exception as e:
            data["error"] = str(e)
        return JsonResponse(data)
    return render(request, 'realtime.html', utils.get_realtime_context(request))


@login_required
def map_data(request):
    return render(request, 'map.html', utils.get_map_context(request))


@login_required
def download_data(request):
    return render(request, 'historical.html')


@login_required
def download_historical_csv(request):
    """Genera CSV de datos históricos para el rango from/to (GET, timestamps en ms)."""
    try:
        from_ts = request.GET.get('from')
        to_ts = request.GET.get('to')
        if from_ts and to_ts:
            start = datetime.fromtimestamp(float(from_ts) / 1000.0)
            end = datetime.fromtimestamp(float(to_ts) / 1000.0)
        else:
            end = timezone.now()
            start = end - dateutil.relativedelta.relativedelta(weeks=1)
    except (TypeError, ValueError):
        end = timezone.now()
        start = end - dateutil.relativedelta.relativedelta(weeks=1)

    start_ts = int(start.timestamp() * 1000000)
    end_ts = int(end.timestamp() * 1000000)

    rows = Data.objects.filter(
        time__gte=start_ts, time__lte=end_ts
    ).select_related('station', 'station__user', 'station__location', 'station__location__city',
                     'station__location__state', 'station__location__country', 'measurement').order_by('time')

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['Usuario', 'Ciudad', 'Estado', 'Pais', 'Fecha', 'Variable', 'Valor'])

    for d in rows:
        user = d.station.user.username
        city = d.station.location.city.name
        state = d.station.location.state.name
        country = d.station.location.country.name
        var = d.measurement.name
        for i, (t, v) in enumerate(zip(d.times or [], d.values or [])):
            try:
                base_ts = d.base_time.timestamp() if hasattr(d.base_time, 'timestamp') else 0
                secs = float(t) if t is not None else 0
                dt = datetime.fromtimestamp(base_ts + secs)
                fecha = dt.strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                fecha = str(d.base_time) if d.base_time else ''
            writer.writerow([user, city, state, country, fecha, var, v])

    response = HttpResponse(buffer.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="datos-historicos-iot.csv"'
    return response


@user_passes_test(lambda u: u.is_superuser)
def users(request):
    users = User.objects.all().order_by('id')
    return render(request, 'users/user_list.html', {'users': list(users)})


@user_passes_test(lambda u: u.is_superuser)
def delete_user(request, username):
    try:
        user = User.objects.get(username=username)
        user.delete()
        messages.success(
            request, f'Usuario {user.username} eliminado correctamente')
    except Exception as e:
        messages.error(request, "Ocurrió un error al eliminar el usuario")
    return HttpResponsePermanentRedirect('/users/')


@user_passes_test(lambda u: u.is_superuser)
def register_request(request):
    if request.method == "POST":
        form = NewUserForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Registro exitoso.")
            return HttpResponsePermanentRedirect("/users/")
        messages.error(
            request, "Registro fallido. Información inválida.")
    form = NewUserForm()
    return render(request=request, template_name="users/user_register.html", context={"register_form": form})


@user_passes_test(lambda u: u.is_superuser)
def variables(request):
    variables = Measurement.objects.all().order_by('id')
    return render(request, 'variables/variable_list.html', {'variables': list(variables)})


@user_passes_test(lambda u: u.is_superuser)
def edit_variable(request, id):
    variable = get_object_or_404(Measurement, pk=id)
    if request.method == "POST":
        form = MeasurementForm(request.POST or None, instance=variable)
        if form.is_valid():
            form.save()
            messages.success(request, "Edición exitosa.")
            return HttpResponsePermanentRedirect("/variables/")
        messages.error(
            request, "Edición fallida. Información inválida.")
    form = MeasurementForm(request.POST or None, instance=variable)
    return render(request=request, template_name="variables/variable_edit.html", context={"register_variable_form": form, "variable": variable})


@user_passes_test(lambda u: u.is_superuser)
def register_variable_request(request):
    if request.method == "POST":
        form = NewVariableForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Registro exitoso.")
            return HttpResponsePermanentRedirect("/variables/")
        messages.error(
            request, "Registro fallido. Información inválida.")
    form = NewVariableForm()
    return render(request=request, template_name="variables/variable_register.html", context={"register_variable_form": form})
