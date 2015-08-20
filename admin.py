# -*- coding: utf-8 -*-
from __future__ import (unicode_literals, absolute_import, division,
                        print_function)

from django.contrib import admin
from dtrcity.models import Country, Region, City, AltName

admin.site.register(Country)
admin.site.register(Region)
admin.site.register(City)
admin.site.register(AltName)
