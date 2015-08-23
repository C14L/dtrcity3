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

@require_http_methods(["GET", "HEAD"])
def city_item(request, country, region, city):
    url = '/'.join([country, region, city])
    lg = get_language()[:2]
    an = get_object_or_404(AltName, url=url, language=lg, type=3,is_main=True)
    city = get_object_or_404(City, pk=an.geoname_id)
    city_name, region_name, country_name = an.crc.split(', ', 2)
    x = { 'id': city.id, 'lat': city.lat, 'lng': city.lng,
          'timezone': city.timezone, 'population': city.population,
          'language': an.language, 'city_name': city_name, 
          'region_name': region_name, 'country_name': country_name,
          'url': an.url, 'crc': an.crc, 'name': an.name, 'slug': an.slug }
    return HttpResponse(json.dumps(x), content_type="application/json")

@require_http_methods(["GET", "HEAD"])
def all_countries(request):
    lang = get_language()[:2]
    countries = Country.objects.all()
    an = AltName.objects.filter(geoname_id__in=countries, is_main=True, type=1,
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
    data = AltName.objects.filter(geoname_id__in=cities, is_main=True, type=3,
                                  language=get_language()[:2]).order_by('crc')
    li = [(x.geoname_id, x.crc) for x in data[:size]]
    return HttpResponse(json.dumps(li), content_type="application/json")

@require_http_methods(["GET", "HEAD"])
def city_by_latlng(request):
    """Receive GET lat/lng and return localized info on nearest city.

    The client sends values from the HTML5 geolocation API: longitude
    and latitude. Find the city closest to the location and return its
    data in the language set in the LANGUAGE setting.
    """
    try:
        lat = float(request.GET.get('latitude', None))
        lng = float(request.GET.get('longitude', None))
    except TypeError:
        return HttpResponseBadRequest()
    try:
        city = City.by_latlng(lat, lng)
    except City.DoesNotExist:
        raise Http404
    try:
        an = AltName.objects.get(geoname_id=city.pk, type=3,
                                 is_main=True, language=settings.LANGUAGE_CODE)
    except AltName.DoesNotExist:
        raise Http404

    return HttpResponse(json.dumps({
        "id": city.id,
        "lat": city.lat,
        "lng": city.lng,
        "region": city.region.pk,
        "country": city.country.pk,
        "population": city.population,
        "slug": an.slug,
        "name": an.name,
        "crc": an.crc,
        "url": an.url,
    }), content_type="application/json")

@require_http_methods(["GET", "HEAD"])
def city_autocomplete_crc(request):
    """Returns a json list of matching AltName.crc objects.

    GET "q" 
        Partial city name to be searched for.
    GET "lg" (optional) 
        A language code, must be in settings.LANGUAGES.
    GET "size" (optional) 
        Max number of items in results list.
    GET "result_fields" (default: crc) 
        Space separated list of data fields to return.
    GET "flat" (default: True) 
        Only if one result field is requsted.

    Example with flat=False:
        [{"crc":"Some, where, place"},{"crc":"Another, some, place"}]
    Same example with flat=True:
        ["Some, where, place","Another, some, place"]

    Result is ordered alphabetically with those values first that begin
    with q, followed by values that contain q somewhere else in the
    string.

    Only crc values of type=3 (city) and in the selected language are
    returned.
    """
    min_len = getattr(settings, 'CITY_AUTOCOMPELTE_MIN_LEN', 2)
    q = request.GET.get('q', '')
    lg = request.GET.get('lg', get_language()[:2])
    size = int(request.GET.get('size', 20))
    fields = list(request.GET.get('fields', 'crc').split(' '))
    flat = request.GET.get('flat', True)

    if len(fields) < 1:
        return HttpResponseBadRequest('No result fields defined.')
    if len(fields) > 1: # Can't be flat.
        flat = False
    if not q or len(q) < min_len:
        return HttpResponseBadRequest('Min. length {} chars.'.format(min_len))

    # First lookup all crc values in AltName that begin with q.
    an = AltName.objects.filter(crc__istartswith=q, language=lg, type=3)
    if flat:
        an = an.values_list(*fields, flat=True)
    else:
        an = an.values(*fields)
    li = [x for x in an.order_by('crc')[:size]]

    # If there are less than "size" values, lookup names that just
    # contain q.
    if len(li) < size:
        rsize = size - len(li)
        an = AltName.objects.filter(crc__icontains=q, language=lg, type=3)\
                            .exclude(crc__istartswith=q)
        if flat:
            an = an.values_list(*fields, flat=True)
        else:
            an = an.values(*fields)
        li += [x for x in an.order_by('crc')[:rsize]]
    # Finally, clean up.
    if flat:
        li = list_uniq(li)
    #else:
    #    li = list_uniq(li)
    return HttpResponse(json.dumps(li), content_type="application/json")

### HELPERS ###################################################################

def list_uniq(seq):
    # http://stackoverflow.com/questions/480214/how-do-you-remove-duplicates
    #                            -from-a-list-in-python-whilst-preserving-order
    seen = set()
    seen_add = seen.add
    return [x for x in seq if not (x in seen or seen_add(x))]
