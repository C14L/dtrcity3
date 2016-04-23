from django.contrib import admin
from dtrcity.models import Country, Region, City, AltName

admin.site.register(Country)
admin.site.register(Region)
admin.site.register(City)
admin.site.register(AltName)
