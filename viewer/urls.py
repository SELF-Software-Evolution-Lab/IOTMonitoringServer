from django.urls import include, path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path("", include("django.contrib.auth.urls")),
    path('realtime-data/', views.realtime_data, name='realtime_data'),
    path('map/', views.map_data, name='map'),
    path('historic/', views.download_data, name='historical'),
    path('users/', views.users, name='users'),
    path('users/delete/<username>', views.delete_user, name='delete_users'),
    path("users/register/", views.register_request, name="register"),
    path('variables/', views.variables, name='variables'),
    path("variables/register/", views.register_variable_request,
         name="register_variable"),
    path('variables/<id>/', views.edit_variable, name='edit_variable'),
]
