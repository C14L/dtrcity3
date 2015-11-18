# -*- coding: utf-8 -*-
from __future__ import (unicode_literals, absolute_import, division,
                        print_function)

from django.conf.urls import patterns, url  # , include
# from django.conf import settings
from dtrcity import views as city_views


urlpatterns = patterns(
    url(r'^api/v1/all-countries.json$',
        city_views.all_countries, name='all_countries'),

    url(r'^api/v1/autocomplete-crc.json$',
        city_views.city_autocomplete_crc, name='city_autocomplete_crc'),

    url(r'^api/v1/cities-in-country.json$',
        city_views.cities_in_country, name='cities_in_country'),

    url(r'^api/v1/city-by-latlng.json$',
        city_views.city_by_latlng, name='city_by_latlng'),

    url(r'^api/v1/(?P<country>[a-z0-9-]+)/(?P<region>[a-z0-9-]+)/'
        r'(?P<city>[a-z0-9-]+).json$',
        city_views.city_item, name='city_item'),
)
