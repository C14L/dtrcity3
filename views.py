# -*- coding: utf-8 -*-
from __future__ import (unicode_literals, absolute_import, division,
                        print_function)

import json

from django.conf import settings
from django.http import HttpResponseBadRequest          # 400
from django.http import HttpResponseNotFound            # 404
from django.http import HttpResponseNotAllowed          # 405 eg ['GET','POST']
from django.http import QueryDict, HttpResponse, Http404
from django.shortcuts import render_to_response, get_object_or_404
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django.utils.translation import get_language

from dtrcity.models import Country, Region, City, AltName

@require_http_methods(["GET"])
def all_countries(request):
    lang = get_language()[:2]
    countries = Country.objects.all()
    an = AltName.objects.filter(geoname_id__in=countries, is_main=1, type=1,
                                language=lang).order_by('name')
    li = [(x.geoname_id, x.name) for x in an]
    return HttpResponse(json.dumps(li), content_type="application/json")

@require_http_methods(["GET"])
def cities_in_country(request):
    """Returns a list of (geoname_id, crc) pairs."""
    # The client may request only cities larger than GET "population".
    population = int(request.GET.get('population', 5000))
    # Use only the first two chars of user' language selection.
    language = get_language()[:2]
    # Max item count to be returned.
    size = int(request.GET.get('size', 10000))
    # Find the Country object GET "q"
    try:
        country = get_object_or_404(Country, pk=request.GET.get('q', None))
    except ValueError as e: # not an int
        raise Http404('No Country matches the given query.')
    # Find all City objects in the country of the required size.
    cities = City.objects.filter(country=country, population__gt=population)
    # Finally, look up the localized names of the City objects.
    data = AltName.objects.filter(geoname_id__in=cities, is_main=1, type=3,
                                  language=get_language()[:2]).order_by('crc')
    li = [(x.geoname_id, x.crc) for x in data[:size]]
    return HttpResponse(json.dumps(li), content_type="application/json")

def city_by_latlng(request):
    """The client sends values from the HTML5 geolocation API: accuracy,
    longitude, latitude. Find the city closest to the location and
    return its data.
    """
    try:
        lat = float(request.GET.get('latitude', None))
        lng = float(request.GET.get('longitude', None))
    except TypeError:
        return HttpResponseBadRequest()
    city = City.by_latlng(lat, lng)
    data = { "id": city.pk, "lat": city.lat, "lng": city.lng,
             "population": city.population, "country": city.country.pk,
             "crc": city.get_crc(), }
    return HttpResponse(json.dumps(data), content_type="application/json")

@require_http_methods(["GET", "HEAD"])
def city_autocomplete_crc(request):
    """Returns a json list of matching AltName.crc values.

    For the string GET "q", return a simple list of matching strings.
    Result is ordered alphabetically with those values first that begin
    with q, followed by values that contain q somewhere else in the
    string.

    Only crc values of type=3 (city) and in the user's selected language
    are returned.
    """
    CITY_AUTOCOMPELTE_MIN_LEN = getattr(settings,
                                        'CITY_AUTOCOMPELTE_MIN_LEN', 4)
    lg = get_language()[:2]
    q = request.GET.get('q', '')
    size = int(request.GET.get('size', 20))
    if len(q) < CITY_AUTOCOMPELTE_MIN_LEN:
        return HttpResponseBadRequest()
    # First lookup all crc values in AltName that begin with q.
    an = AltName.objects.filter(crc__istartswith=q, language=lg, type=3)
    li = [x['crc'] for x in an.order_by('crc')[:size].values('crc')]
    # If there are less than "size" values, lookup names that just
    # contain q.
    if len(li) < size:
        rsize = size - len(li)
        an = AltName.objects.filter(crc__icontains=q, language=lg,
                                    type=3).exclude(crc__istartswith=q)
        li += [x['crc'] for x in an.order_by('crc')[:rsize].values('crc')]
    return HttpResponse(json.dumps(li), content_type="application/json")
