"""Import all geo data from an online source.

This is "cities_very_light" but language aware. AltNames are imported in
various different languages (defined in settings.LANGUAGES list),
and different ways of spelling for the same location. Each location has
a main way to spell it "is_main" that should be used for display.
"""

import io, os, zipfile, time
from urllib.request import urlopen
from optparse import make_option
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from dtrcity.models import Country, Region, City, AltName

conf = {}
conf['URL_BASES'] = {
    'geonames': {
        'dump': 'http://download.geonames.org/export/dump/',
        'zip': 'http://download.geonames.org/export/zip/',
    },
}
conf['FILES'] = {
    'country':      {
        'filename': 'countryInfo.txt',
        'urls':     [conf['URL_BASES']['geonames']['dump']+'{filename}', ]
    },
    'region':       {
        'filename': 'admin1CodesASCII.txt',
        'urls':     [conf['URL_BASES']['geonames']['dump']+'{filename}', ]
    },
    'subregion':    {
        'filename': 'admin2Codes.txt',
        'urls':     [conf['URL_BASES']['geonames']['dump']+'{filename}', ]
    },
    'city':         {
        'filename': 'cities15000.zip',
        'urls':     [conf['URL_BASES']['geonames']['dump']+'{filename}', ]
    },
    'hierarchy':    {
        'filename': 'hierarchy.zip',
        'urls':     [conf['URL_BASES']['geonames']['dump']+'{filename}', ]
    },
    'alt_name':     {
        'filename': 'alternateNames.zip',
        'urls':     [conf['URL_BASES']['geonames']['dump']+'{filename}', ]
    },
    'postal_code':  {
        'filename': 'allCountries.zip',
        'urls':     [conf['URL_BASES']['geonames']['zip']+'{filename}', ]
    }
}

conf['COUNTRY_CODES'] = [
    'AD','AE','AF','AG','AI','AL','AM','AO','AQ','AR','AS','AT','AU','AW','AX','AZ',
    'BA','BB','BD','BE','BF','BG','BH','BI','BJ','BL','BM','BN','BO','BQ','BR','BS','BT','BV','BW','BY','BZ',
    'CA','CC','CD','CF','CG','CH','CI','CK','CL','CM','CN','CO','CR','CU','CV','CW','CX','CY','CZ',
    'DE','DJ','DK','DM','DO','DZ','EC','EE','EG','EH','ER','ES','ET','FI','FJ','FK','FM','FO','FR',
    'GA','GB','GD','GE','GF','GG','GH','GI','GL','GM','GN','GP','GQ','GR','GS','GT','GU','GW','GY',
    'HK','HM','HN','HR','HT','HU','ID','IE','IL','IM','IN','IO','IQ','IR','IS','IT','JE','JM','JO','JP',
    'KE','KG','KH','KI','KM','KN','KP','KR','XK','KW','KY','KZ','LA','LB','LC','LI','LK','LR','LS','LT','LU','LV','LY',
    'MA','MC','MD','ME','MF','MG','MH','MK','ML','MM','MN','MO','MP','MQ','MR','MS','MT','MU','MV','MW','MX','MY','MZ',
    'NA','NC','NE','NF','NG','NI','NL','NO','NP','NR','NU','NZ','OM',
    'PA','PE','PF','PG','PH','PK','PL','PM','PN','PR','PS','PT','PW','PY','QA','RE','RO','RS','RU','RW',
    'SA','SB','SC','SD','SS','SE','SG','SH','SI','SJ','SK','SL','SM','SN','SO','SR','ST','SV','SX','SY','SZ',
    'TC','TD','TF','TG','TH','TJ','TK','TL','TM','TN','TO','TR','TT','TV','TW','TZ','UA','UG','UM','US','UY','UZ',
    'VA','VC','VE','VG','VI','VN','VU','WF','WS','YE','YT','ZA','ZM','ZW',
]

# See http://www.geonames.org/export/codes.html
conf['CITY_TYPES'] = ['PPL','PPLA','PPLC','PPLA2','PPLA3','PPLA4']
conf['DISTRICT_TYPES'] = ['PPLX']

class Command(BaseCommand):
    #data_dir = os.path.join(settings.BASE_DIR, 'import_data')
    data_dir = '/home/chris/dev-data/dtrcity'
    option_list = BaseCommand.option_list + (
        make_option('--force', action='store_true', default=False,
            help='Import even if files are up-to-date.'
        ),
    )

    def handle(self, *args, **options):
        self.download_cache = {}
        self.options = options
        self.force = self.options['force']
        self.import_country()
        self.import_region()
        self.import_city()
        self.import_alt_name() # All altnames from geonames db.
        self.fillup_alt_name() # Add all orig names from country, region, city.
        self.define_main_alt_names() # Set exactly one name per lg to 'main'.
        self.make_crc_for_main_alt_names() # Create crc and url strings.

    def download(self, filekey):
        filename = conf['FILES'][filekey]['filename']
        web_file = None
        urls = [e.format(filename=filename) for e in conf['FILES'][filekey]['urls']]
        for url in urls:
            print('Trying to fetch "{}" ...'.format(url))
            try:
                print('Trying to open a connection ...')
                web_file = urlopen(url)
                print('Connection opened ...')
                if 'html' in web_file.headers['content-type']:
                    print('Warning: Received HTML header at "{}"'.format(url))
                    raise ValueError()
                print('Data received.')
                break
            except ValueError as e:
                print(e)
                print('Warning: An exception occured for "{}"'.format(url))
                web_file = None
                continue
        #else:
        #    print("ERROR: Web file not found: {}. Tried URLs:\n{}"\
        #        .format(filename, '\n'.join(urls)))

        uptodate = False
        filepath = os.path.join(self.data_dir, filename)
        if web_file is not None:
            web_file_time = time.strptime(
                web_file.headers['last-modified'], '%a, %d %b %Y %H:%M:%S %Z')
            web_file_size = int(web_file.headers['content-length'])
            if os.path.exists(filepath):
                file_time = time.gmtime(os.path.getmtime(filepath))
                file_size = os.path.getsize(filepath)
                if file_time >= web_file_time and file_size == web_file_size:
                    print("File up-to-date: " + filename)
                    uptodate = True
        else:
            print('Warning: Assuming file is up-to-date: "{}"'.format(filepath))
            uptodate = True

        if not uptodate and web_file is not None:
            print("Downloading: " + filename)
            if not os.path.exists(self.data_dir):
                os.makedirs(self.data_dir)
            file = open(os.path.join(self.data_dir, filename), 'wb')
            file.write(web_file.read())
            file.close()
        elif not os.path.exists(filepath):
            raise Exception("File not found and download failed: " + filename)

        return uptodate

    def download_once(self, filekey):
        if filekey in self.download_cache: return self.download_cache[filekey]
        uptodate = self.download_cache[filekey] = self.download(filekey)
        return uptodate

    def get_data(self, filekey):
        filename = conf['FILES'][filekey]['filename']
        name, ext = filename.rsplit('.',1)

        if (ext == 'zip'):
            with open(os.path.join(self.data_dir, filename), 'rb') as file:
                with zipfile.ZipFile(file, mode='r').open(name + '.txt', 'rU') as zip:
                    data = io.TextIOWrapper(io.BytesIO(zip.read()))
            print(data)
        else:
            with open(os.path.join(self.data_dir, filename), 'r') as file:
                data = file.read().split('\n')

        return data

    def parse(self, data):
        for line in data:
            if len(line) < 1 or line[0] == '#': continue
            items = [e.strip() for e in line.split('\t')]
            yield items

    def build_country_index(self):
        if hasattr(self, 'country_index'):
            s = 'Country index exists, with {} items in country_index.'
            print(s.format(len(self.country_index)))
            return
        print('Building country index...')
        self.country_index = {}
        for obj in Country.objects.all():
            self.country_index[obj.code] = obj
        print('{} items in country_index.'.format(len(self.country_index)))

    def build_region_index(self):
        if hasattr(self, 'region_index'):
            s = 'Region index exists, with {} items in region_index.'
            print(s.format(len(self.region_index)))
            return
        print('Building region index...')
        self.region_index = {}
        for obj in Region.objects.all():
            self.region_index[obj.code] = obj
        print('{} items in region_index.'.format(len(self.region_index)))

    def build_geo_index(self):
        if hasattr(self, 'geo_index'):
            s = 'Geo index exists, item count is country: {}, ' \
                'region: {}, and city: {} items.'
            print(s.format(len(self.geo_index['country']),
                           len(self.geo_index['region']),
                           len(self.geo_index['city'])))
            return
        print('Building geo index...')
        self.geo_index = { 'country':[], 'region':[], 'city':[] }
        for obj in Country.objects.all():
            self.geo_index['country'].append(obj.id)
        for obj in Region.objects.all():
            self.geo_index['region'].append(obj.id)
        for obj in City.objects.all():
            self.geo_index['city'].append(obj.id)
        s = 'Geo index built, item count is country: {}, ' \
            'region: {}, and city: {} items.'
        print(s.format(len(self.geo_index['country']),
                       len(self.geo_index['region']),
                       len(self.geo_index['city'])))

    def import_country(self):
        uptodate = self.download('country')
        if uptodate and not self.force: return
        data = self.get_data('country')
        s = 'Importing country data from {0} country datasets...'
        print(s.format(len(data)))
        cnt = 0
        for items in self.parse(data):
            cnt += 1
            country = Country()
            try: country.id = int(items[16]) # geoname_id
            except: continue # skip the row if no geoname_id.
            country.name = items[4]
            #country.slug = slugify(country.name)
            country.code = items[0]
            country.population = items[7]
            country.continent = items[8]
            country.tld = items[9][1:] # strip the leading .
            country.save()
        print('{} countries imported.'.format(cnt))

    def import_region(self):
        uptodate = self.download('region')
        if uptodate and not self.force: return
        data = self.get_data('region')
        self.build_country_index()
        cnt = 0
        print('Importing region data ...')
        for items in self.parse(data):
            cnt += 1
            region = Region()
            region.id = int(items[3]) # geoname_id
            region.code = items[0]
            region.name = items[1]

            # Find country
            country_code = region.code.split('.')[0]
            try:
                region.country = self.country_index[country_code]
                region.save()
            except:
                s = 'Skip region "{0}", no related country found!'
                print(s.format(region.code))
        print('{0} regions imported.'.format(cnt))

    def import_city(self):
        uptodate = self.download_once('city')
        if uptodate and not self.force: return
        data = self.get_data('city')
        self.build_country_index()
        self.build_region_index()
        cnt = 0
        print('Importing city data ...')
        for items in self.parse(data):
            cnt += 1
            type = items[7]
            if type not in conf['CITY_TYPES']: continue

            city = City()
            city.id = int(items[0]) # geoname_id
            city.name = items[1] # Real name
            city.lat = float(items[4]) # latitude in decimal degrees (wgs84)
            city.lng = float(items[5]) # longitude in decimal degrees (wgs84)
            city.population = items[14]

            # Find country
            try:
                city.country = self.country_index[items[8]]
            except:
                print('Skip city "{0}", no related country found!'\
                      .format(city.id))
                continue

            # Find region
            try:
                rc = '{0}.{1}'.format(items[8].upper(), items[10])
                city.region = self.region_index[rc]
            except:
                print('Skip city "{0}", no related region found!'\
                      .format(city.id))
                continue

            city.save()
        print('{0} cities imported.'.format(cnt))

    def import_alt_name(self):
        i = j = 0

        # Download the altnames file if necessary and fetch the data.
        uptodate = self.download('alt_name')
        if uptodate and not self.force: return

        print('Fetching fresh alt_name data...')
        data = self.get_data('alt_name')
        print('Successfully fetched alt_name data.')

        # Import only names in the languages set in settings.LANGUAGES
        languages = [e[0] for e in settings.LANGUAGES]
        print('Looking for languages: {0}'.format(languages))

        # The geo types used.
        types = ((1, 'country'), (2, 'region'), (3, 'city'))

        # Load only geoname_id numbers from country, region, city into memory.
        print('Building indexes...')
        self.build_geo_index()
        self.build_country_index()
        self.build_region_index()
        print('All indexes built.')

        print('Start importing of AltName data.')
        for items in self.parse(data):
            i += 1
            print('{} import geoname_id "{}" for language {}'.format(i,
                                                  items[1], items[2]), end=" ")

            # Verify that the "name" items[3] contains a string:
            item_name = items[3].strip()
            if not item_name:
                print('SKIP: Item had an empty strng for a name.')
                continue

            # Only get names for languages in use.
            if items[2] not in languages:
                print('SKIP: Unknown language.')
                continue

            # The geoname_id of the item.
            item_geoname_id = int(items[1])
            if not item_geoname_id:
                print('SKIP: Item had an empty strng for a name.')
                continue

            # Find the type (city, region, or country) for the item. Must be one
            # of the three types defined above.
            item_type = None
            for t in types:
                # The geo_index contains all geoname_id vals by type.
                if item_geoname_id in self.geo_index[t[1]]:
                    # Remember "types" id (city, region, coutnry) of the item.
                    item_type = t[0]
                    break
            if item_type is None:
                print('SKIP: Geoname type not found.')
                continue
            print('type "{}"'.format(item_type), end=' ')

            # All import data clean, create database object.
            alt = AltName()
            # Use altname_id from source database as pk. Not useful, because the
            # pk is actually never used hereafter.
            #alt.id = int(items[0])
            # The important identifier, the geoname_id of the geo object.
            alt.geoname_id = item_geoname_id
            alt.language = items[2]
            alt.crc = ''
            alt.name = item_name # items[3]
            alt.slug = slugify(item_name)
            alt.type = item_type
            alt.is_main = bool(0)
            alt.is_preferred = bool(items[4])
            alt.is_short = bool(items[5])
            alt.is_colloquial = bool(items[6])
            alt.is_historic = bool(items[7])
            alt.save()
            print('SAVED!')

    def fillup_alt_name(self):
        """
        Make sure that for every language there is a least ONE
        entry in the altnames table for each geoitem. Currently, when there is
        no translation, any entry in altname is often missing (for example
        there is no entry LIKE "%rotenburg%" in altname altogether. Loop all
        three (country, region, city) tables and loop all optional languages
        for the installation, and then check that there is an entry for the
        geoitem and language in altname and if not, then add the default
        (english) name from the (country, region, city) table.

        The reason is to be able to select just from altname for autocomplete
        and never query the names from (country, region, city).
        """
        languages = [e[0] for e in settings.LANGUAGES]
        types = ((1, 'country'), (2, 'region'), (3, 'city'))
        alt = AltName.objects.all()
        obj = { 'country': Country.objects.all(),
                'region': Region.objects.all(),
                'city': City.objects.all(), }

        for t in types:
            for c in obj[t[1]]:
                for lg in languages:
                    print('[t={0}] [c={1}] [lg={2}] Check entry for "{3}"...'\
                                                .format(t[1], c.id, lg, c.name))
                    for e in alt:
                        if e.geoname_id == c.id and e.language == lg:
                            print('Entry found with AltName id [{0}] as "{1}".'\
                                                          .format(e.id, e.name))
                            break
                    else:
                        # No entries, add one.
                        print('NO entry found, so add one...')
                        addalt = AltName()
                        addalt.geoname_id = c.id
                        addalt.language = lg
                        addalt.crc = ''
                        addalt.name = c.name
                        addalt.slug = slugify(c.name)
                        addalt.type = t[0]
                        addalt.is_main = False
                        addalt.is_preferred = True
                        addalt.is_short = True
                        addalt.is_colloquial = False
                        addalt.is_historic = False

                        if t == 2 or t == 3:
                            # If this is a city or region, find the country
                            addalt.country_id = c.country_id
                            if t == 3:
                                # If this is a city, also find the region.
                                addalt.region_id = c.region_id
                        addalt.save()
                        print('New entry added for "{0}".'.format(c.name))

    def define_main_alt_names(self):
        """
        Every geoname item needs one "main" AltName.

        That AltName's crc will be stored with UserProfile.crc and used as the
        geo item's URL path by converting crc "City, Region, Country" into
        "country/region/city" paths.
        """
        # Only for laguages that will be used, as defined in settings.LANGUAGES
        lgs = [e[0] for e in settings.LANGUAGES]

        def try_to_set_main(lg, go):
            try:
                # 0: Check if item has already a main set with this geoname_id
                # and language.
                anlist = AltName.objects.filter(language=lg,
                                                geoname_id=go.id, is_main=True)
                cnt = anlist.count()
                if cnt == 1:
                    print('Already EXIST main for {0}--{1}'.format(lg, go.name))
                    return True
                elif cnt > 1:
                    print('ERROR more than one main for {0}--{1}'.format(lg,
                                                                    go.name))
                    for an in anlist:
                        an.is_main=False
                        an.save()
                    print('ERROR FIXED. Trying again to find main...')
            except:
                pass

            try:
                # Try 1: Only works if there is only one single object with this
                # geoname_id and language.
                an = AltName.objects.get(language=lg, geoname_id=go.id)
                an.is_main = True
                an.save()
                print('Setting main for {0}--{1} to {2}'.format(
                                                        lg, go.name, an.name))
                return True
            except:
                pass

            try:
                # Try 2: Fetch the first available "short" name for the geoname
                # object. Like USA for United States of America or Hamburg for
                # Freie- und Hansestadt Hamburg, etc. If there is no short name,
                # this would fail.
                an = AltName.objects.filter(language=lg,
                                            geoname_id=go.id, is_short=1)[0]
                an.is_main = True
                an.save()
                print('Setting main for {0}--{1} to {2}'.format(
                                                        lg, go.name, an.name))
                return True
            except:
                pass

            try:
                # Try 3: Fetch the first "preferred" name for the object or fail
                # if there is no preferred name.
                an = AltName.objects.filter(language=lg,
                                            geoname_id=go.id, is_preferred=1)[0]
                an.is_main = True
                an.save()
                print('Setting main for {0}--{1} to {2}'.format(lg, go.name,
                                                                    an.name))
                return True
            except:
                pass

            try:
                # Try 4: Finally, just fetch the first of any names for this
                # object and set it as the default name. If this fails, too,
                # then this geoname object is not in the AltName table (which
                # would be odd, because we just added all of them).
                an = AltName.objects.filter(language=lg, geoname_id=go.id)[0]
                an.is_main = True
                an.save()
                print('Setting main for {0}--{1} to {2}'.format(lg, go.name,
                                                                    an.name))
                return True
            except:
                pass

            print('FAIL: Could not set "is_main" for {0}--{1} !'.format(lg,
                                                                    go.name))
            return False

        # Set a main AltName for each country name.
        for go in Country.objects.all():
            for lg in lgs:
                try_to_set_main(lg, go)

        # Set a main AltName for each region name.
        for go in Region.objects.all():
            for lg in lgs:
                try_to_set_main(lg, go)

        # Set a main AltName for each city name.
        for go in City.objects.all():
            for lg in lgs:
                try_to_set_main(lg, go)

    def make_crc_for_main_alt_names(self):
        """
        Add country_id and region_id for all city items, and country_id for all
        region items. Also, build the "City, Region, Country" for each AltName
        string for faster display of from name. Add a crc value to each item so
        that I only need to do lookups on the AltName.crc column when and would
        find even unusual spellings for a city. Since the geoname_id is the
        correct one, the geo object is still the same.

        Only add crc strings for cities. We will never do lookups on regions or
        countries. For "list by country" or "list by region", the lookup should
        be done by the geoname_id always.
        """

        # Add a country and region ID and crc to all "main" city (3) types
        # in the AltName table.
        print('----- make_crc_for_main_alt_names() -----')
        i = 0
        for obj in AltName.objects.filter(type=3, is_main=True).order_by('pk'):
            i += 1

            # Get the related City object.
            city = City.objects.get(pk=obj.geoname_id)
            print('{0}--Processing city {4} "{1}" (country {2}, region {3})...'\
                .format(i, city.name, city.country.id, city.region.id, city.id))

            # Set this AltName's values from the City object. This will help to
            # do faster lookups from user input.
            obj.country_id = city.country.id
            obj.region_id = city.region.id
            obj.lat = city.lat
            obj.lng = city.lng

            # For this City object, find the commonly used ("main") names of its
            # region and country, in the AltName object's language. So the
            # "City, Region, Country" string will all be in the same language.
            country = AltName.objects.get(type=1, geoname_id=obj.country.id,
                                            is_main=True, language=obj.language)
            region = AltName.objects.get(type=2, geoname_id=obj.region.id,
                                            is_main=True, language=obj.language)

            # Build the "City, Region, Country" string ("crc").
            obj.crc = '{0}, {1}, {2}'.format(obj.name, region.name,
                                                            country.name)[:200]
            print('crc "{0}"...'.format(obj.crc))

            # Build the "country/region/city" URL path ("url").
            obj.url = '{0}/{1}/{2}'.format(slugify(country.name),
                                 slugify(region.name), slugify(obj.name))[:100]
            print('url "{0}"...'.format(obj.url))

            obj.save()
            print('done.')
