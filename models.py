# -*- coding: utf-8 -*-
from __future__ import (unicode_literals, absolute_import, division,
                        print_function)

import math
from django.conf import settings
from django.db import models
from django.utils.translation import get_language

# settings: Default distance around a city.
DISTANCE_AROUND_CITY = getattr(settings, 'DISTANCE_AROUND_CITY', 20)

# calculate the bounding box for a given lat/lng location, from
# http://stackoverflow.com/questions/238260/how-to-calculate-the-
#                       bounding-box-for-a-given-lat-lng-location
def deg2rad(degrees):
    # degrees to radians
    return math.pi * degrees / 180.0
def rad2deg(radians):
    # radians to degrees
    return 180.0 * radians / math.pi
# Semi-axes of WGS-84 geoidal reference
WGS84_a = 6378137.0  # Major semiaxis [m]
WGS84_b = 6356752.3  # Minor semiaxis [m]
def WGS84EarthRadius(lat):
    # http://en.wikipedia.org/wiki/Earth_radius
    # Earth radius at a given latitude, according to the WGS-84 ellipsoid [m]
    An = WGS84_a * WGS84_a * math.cos(lat)
    Bn = WGS84_b * WGS84_b * math.sin(lat)
    Ad = WGS84_a * math.cos(lat)
    Bd = WGS84_b * math.sin(lat)
    return math.sqrt((An*An + Bn*Bn) / (Ad*Ad + Bd*Bd))
def boundingBox(latitudeInDegrees, longitudeInDegrees, halfSideInKm):
    # Bounding box surrounding the point at given coordinates, assuming local
    # approximation of Earth surface as a sphere of radius given by WGS84
    lat = deg2rad(latitudeInDegrees)
    lon = deg2rad(longitudeInDegrees)
    halfSide = 1000 * halfSideInKm
    # Radius of Earth at given latitude
    radius = WGS84EarthRadius(lat)
    # Radius of the parallel at given latitude
    pradius = radius * math.cos(lat)
    latMin = lat - halfSide/radius
    latMax = lat + halfSide/radius
    lonMin = lon - halfSide/pradius
    lonMax = lon + halfSide/pradius
    return (rad2deg(latMin), rad2deg(lonMin), rad2deg(latMax), rad2deg(lonMax))

class Country(models.Model):
    """Model that describes all countries."""

    # English name for admin only. Apps should use localized AltName values.
    name = models.CharField(max_length=100)
    # Lower-case ASCII version of name.
    slug = models.SlugField(max_length=100, default='')
    # Used for import.
    code = models.CharField(max_length=20)
    # de, us, cn, etc.
    tld = models.CharField(max_length=2, default='')
    # Could be used to limit locations to one continent only.
    continent = models.CharField(max_length=2, default='')
    # Could be used to limit locations to large countries only.
    population = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.name

class Region(models.Model):
    """Model that describes all regions within all countries."""

    # English name for admin only. Apps should use localized AltName values.
    name = models.CharField(max_length=100)
    # Used for import.
    code = models.CharField(max_length=20)
    # The country this region belongs to.
    # FIXME: add ", db_index=True" here!
    country = models.ForeignKey(Country, null=True, default=None)

    class Meta:
        ordering = ['country', 'name']

    def __str__(self):
        return self.name

class City(models.Model):
    """Model that describes all cities within all regions/countries.

    Each City comes with information to which region and country it
    belongs.

    Do not use the name field here, but rather find the correct
    localized name from the AltName table, using City.pk and the
    required language to find the "is_main" name from AltName.

    This model comes with a number of convenience methods to fetch
    cities by country or geolocation, or to fetch cities that are within
    a certain distance to another city.
    """

    # English name for admin only. Apps should use localized AltName values.
    name = models.CharField(max_length=100)
    # The region this city belongs to.
    # FIXME: add ", db_index=True" here!
    region = models.ForeignKey(Region, null=True, default=None)
    # The country this city belongs to.
    # FIXME: add ", db_index=True" here!
    country = models.ForeignKey(Country, null=True, default=None)
    # latitude and longitude in decimal degrees (wgs84)
    lat = models.FloatField(default=0.0)
    lng = models.FloatField(default=0.0)
    # These values may be missing for many cities.
    timezone = models.CharField(max_length=40, default='')
    population = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['name']
        index_together = ['lat', 'lng']

    def __str__(self):
        return self.name

    def get_crc(self, language=None):
        """Returns the crc for a city in a given language."""
        if language is None:
            language = get_language()
        try:
            # Only use the first two chars in language, e.g. "en-us" -> "en".
            return AltName.objects.get(geoname_id=self.pk, type=3,
                                       language=language[:2], is_main=True).crc
        except AltName.DoesNotExist:
            print('AltName not found for {0} ({1}).'.format(self.pk, self.name))
            return ''

    @classmethod
    def get_by_crc(cls, name):
        """Return a City object that matches the crc."""
        try:
            # Only use the first two chars in language, e.g. "en-us" -> "en".
            lang = get_language()[:2]
            geoname_id = AltName.objects.filter(crc=name, type=3, is_main=True,
                                                language=lang)[0].geoname_id
            return City.objects.get(pk=geoname_id)
        except AltName.DoesNotExist:
            return None

    @classmethod
    def get_by_url(cls, name):
        """Return a City object that matches the url."""
        try:
            lang = get_language()[:2]
            geoname_id = AltName.objects.filter(url=name, type=3, is_main=True,
                                                language=lang)[0].geoname_id
            return City.objects.get(pk=geoname_id)
        except AltName.DoesNotExist:
            return None

    @classmethod
    def get_cities_around_city(cls, city, dist=None):
        """Find all City objects within "dist" km from City, including City
        itself. Uses a simple 'square', not a circle, for the surrounding."""
        if dist is None:
            # some default distance
            dist = DISTANCE_AROUND_CITY
        latmin, lngmin, latmax, lngmax = boundingBox(city.lat, city.lng, dist)
        return City.objects.filter(lat__gte=latmin, lng__gte=lngmin,
                                   lat__lte=latmax, lng__lte=lngmax)

    @classmethod
    def get_cities_around_crc(cls, city_crc, dist=None):
        """Shortcut, first finds the city, then the surrounding cities."""
        city = cls.get_by_crc(city_crc)
        return cls.get_cities_around_city(city, dist)

    @classmethod
    def by_latlng(cls, lat, lng):
        """Return the City nearest to the given lat/lng. Returns None
        if there is no city within 2000 km from lat/lng."""
        # fetch some cities, first try near by
        for dist in [10, 50, 100, 200, 500, 2000]:
            latmin, lngmin, latmax, lngmax = boundingBox(lat, lng, dist)
            cities = list(City.objects.filter(lat__gte=latmin, lng__gte=lngmin,
                                              lat__lte=latmax, lng__lte=lngmax
                                              ).values('pk', 'lat', 'lng'))
            if len(cities) > 0:
                # found some cities! find the nearest.
                for city in cities:
                    # simplefied: distance without accounting for earth radius.
                    city['dist'] = math.sqrt(math.pow((lat - city['lat']), 2) +
                                             math.pow((lng - city['lng']), 2))
                # Sort to have the closest city first.
                cities.sort(key=lambda c: c['dist'])
                return City.objects.get(pk=cities[0]['pk'])
        # unlikely but possible: no city in ~2000 km from lat/lng.
        return None

class AltName(models.Model):
    """Model that lists all possible alternative names for locations.

    For each geolocation, there is exactly one "is_main" item for every
    language, that is the authoritve name for the geolocation. Any Other
    names are to be used only to look up the location from user input,
    e.g. for autocomplete form fields.

    To find the name of a geolocation, query with the geoname_id, the
    desired language, and the "is_main" value to find the primary name.
    """

    # The geoname_id from the geoname database. This will be repeated
    # for the different names of the same geoname object. It may be
    # the pk of a City, a Region, or a Country, depending on "type".
    geoname_id = models.PositiveIntegerField(db_index=True)
    # For country names, these are empty. For region names only the
    # country is referenced. For city names, the city's Region and
    # Country are referenced.
    country = models.ForeignKey(Country, null=True, default=None)
    region = models.ForeignKey(Region, null=True, default=None)
    # The language this geoname is in. e.g. en, es, de, fr, etc.
    # TODO: should use only notation with two characters.
    language = models.CharField(max_length=6)
    # "City, Region, Country" string (only stored for "city" values.
    # In the language defined in the "language" field.
    crc = models.CharField(max_length=200, db_index=True, default='')
    # "country/region/city" URL string, only stored for "city" values
    # with "is_main" field True and in the language defined in the
    # "language" field.
    url = models.CharField(max_length=100, db_index=True, default='')
    # The name in the original script (name) and its ASCII chars
    # transliteration (slug). In the language defined in "language"
    # field.
    name = models.CharField(max_length=200, default='')
    slug = models.SlugField(max_length=200, default='')
    # Type of geoname object. 1=countries, 2=regions, and 3=cities.
    type = models.PositiveSmallIntegerField(choices=((1, 'country'),
                                            (2, 'region'), (3, 'city')))
    # For every language, every geoname_id has exactly one main=1
    # object. Other entries are used for autocomplete user input only.
    is_main = models.BooleanField(default=False)
    is_preferred = models.BooleanField(default=False)
    is_short = models.BooleanField(default=False)
    is_colloquial = models.BooleanField(default=False)
    is_historic = models.BooleanField(default=False)

    class Meta:
        ordering = ["crc"]
        index_together = [
            ['geoname_id', 'language', 'is_main'],
            ['language', 'crc', 'is_main'],
        ]

    def __str__(self):
        return self.crc
