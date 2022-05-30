from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from receiver.models import Measurement


class NewUserForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def save(self, commit=True):
        user = super(NewUserForm, self).save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user


class NewVariableForm(forms.Form):
    name = forms.CharField(label="Nombre", required=True,
                           min_length=3, max_length=50)
    unit = forms.CharField(label="Unidad", required=True, max_length=3)
    min_value = forms.FloatField(label="Valor mínimo", required=True)
    max_value = forms.FloatField(label="Valor máximo", required=True)

    class Meta:
        model = Measurement
        fields = ("name", "unit", "min_value", "max_value")

    def save(self, commit=True):
        name = self.cleaned_data['name']
        unit = self.cleaned_data['unit']
        min_value = self.cleaned_data['min_value']
        max_value = self.cleaned_data['max_value']
        variable = Measurement(name=name, unit=unit,
                               min_value=min_value, max_value=max_value)
        if commit:
            variable.save()
        return variable


class MeasurementForm(forms.ModelForm):
    class Meta:
        model = Measurement
        exclude = ('active', "name")
