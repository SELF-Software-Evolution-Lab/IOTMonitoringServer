from django.template.defaulttags import register
import json


@register.filter
def get_statistic(dictionary, key):
    """
    Filtro para formatear datos en el template de index
    """
    if type(dictionary) == str:
        dictionary = json.loads(dictionary)
    if key is None:
        return None
    keys = [k.strip() for k in key.split(",")]
    return dictionary.get(keys[0]).get(keys[1])


@register.filter
def add_str(str1, str2):
    """
    Filtro para formatear datos en los templates
    """
    return str1 + str2
