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
                data["result"], measurement = utils.get_last_week_data(
                    userParam, cityName, stateName, countryName
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
