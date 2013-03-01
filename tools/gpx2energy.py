#!/usr/bin/env python

import datetime
import functools
import math
import operator
import sys
import urllib
import xml.etree.ElementTree

gpx_namespaces = {'gpx': 'http://www.topografix.com/GPX/1/1'}

class prop(property):
    "A property that caches the result."

    def __init__(self, function):

        attribute = function.__name__

        @functools.wraps(function)
        def cached(obj):
            try:
                return vars(obj)[attribute]
            except KeyError:
                value = function(obj)
                vars(obj)[attribute] = value
                return value

        super(prop, self).__init__(cached)

class Earth(object):
    # http://en.wikipedia.org/wiki/Earth_radius
    radius = 6371*1000 # m

    # http://pl.wikipedia.org/wiki/Przyspieszenie_ziemskie#Wybrane_warto.C5.9Bci_przyspieszenia_ziemskiego_.5Bm.2Fs.C2.B2.5D
    # for Krakow
    g = 9.8105 # m/s^2

    # http://en.wikipedia.org/wiki/Density_of_air
    # at 0 degrees C
    air_density = 1.2922 # kg/m^3

class Car(object):
    # smart fortwo

    # http://clubsmartcar.com/index.php?showtopic=9972
    cx = 0.37

    # http://clubsmartcar.com/index.php?showtopic=9972
    frontal_area = 1.95

    # http://en.wikipedia.org/wiki/Drag_area
    cda = cx * frontal_area

    # including driver and batteries
    mass = 880 # kg

    # tyres and brakes/steering
    rrc = 0.01355 # kg/kg

    # ICE power of the vehicle used to create
    # the GPX file
    power = 40000 # W
    
    # max speed in m/s
    max_speed = 100*1000/3600

    # http://en.wikipedia.org/wiki/Weight#ISO_definition
    weight = mass * Earth.g # N

    battery_pack_efficiency = 0.95
    controller_efficiency = 0.95
    motor_efficiency = 0.87
    gearbox_efficiency = 0.9

    electrical_efficiency = battery_pack_efficiency * controller_efficiency * motor_efficiency
    mechanical_efficiency = gearbox_efficiency

    efficiency = electrical_efficiency * mechanical_efficiency

class Point(object):
    gpx_path = 'gpx:trkpt'

    def __init__(self, track, index, trkpt):
        self.track = track
        self.index = index
        self.lat = float(trkpt.attrib['lat'])
        self.lon = float(trkpt.attrib['lon'])
        self.elevation = float(trkpt.find('gpx:ele', gpx_namespaces).text)
        time = trkpt.find('gpx:time', gpx_namespaces).text
        self.time = datetime.datetime.strptime(time[:-1],'%Y-%m-%dT%H:%M:%S.%f')

    @prop
    def previous(self):
        if self.index > 0:
            return self.track.points[self.index - 1]

    @prop
    def next(self):
        if self.index < len(self.track.points) - 1:
            return self.track.points[self.index + 1]

    def url(self, other=None):
        url = 'https://maps.google.pl/maps?%s'
        if other:
            query = 'from: %s %s to: %s %s' % (
                self.lat, self.lon,
                other.lat, other.lon
            )
        else:
            query = '%s %s' % (self.lat, self.lon)
        return url % urllib.urlencode({'q': query})

    @prop
    def flat_distance(self):
        # http://en.wikipedia.org/wiki/Haversine_formula
        
        if self.previous:
            dlat = math.radians(self.lat - self.previous.lat)
            dlon = math.radians(self.lon - self.previous.lon)

            a = math.sin(dlat/2) ** 2 + math.cos(math.radians(self.lat)) \
                * math.cos(math.radians(self.previous.lat)) * \
                math.sin(dlon/2) ** 2

            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

            return Earth.radius * c
        else:
            return 0

    @prop
    def distance(self):
        # http://en.wikipedia.org/wiki/Pythagorean_theorem
        return math.sqrt(self.flat_distance**2 + self.climb**2)

    @prop
    def climb(self):
        if self.previous:
            return self.elevation - self.previous.elevation
        else:
            return 0

    @prop
    def incline_sinus(self):
        try:
            # http://en.wikipedia.org/wiki/Trigonometric_functions#Right-angled_triangle_definitions
            sinus = self.climb / self.distance
        except ZeroDivisionError:
            sinus = 1

        if -0.25 < sinus < 0.25:
            # reasonable value
            return sinus
        else:
            if self.previous:
                return self.previous.incline_sinus
            else:
                return 0

    @prop
    def incline_cosinus(self):
        
        try:
            # http://en.wikipedia.org/wiki/Trigonometric_functions#Right-angled_triangle_definitions
            cosinus = self.flat_distance / self.distance
        except ZeroDivisionError:
            cosinus = 0
        if 0.75 < cosinus <= 1: 
            # reasonable value
            return cosinus
        else:
            if self.previous:
                return self.previous.incline_cosinus
            else:
                return 1

    @prop
    def period(self):
        if self.previous:
            return (self.time - self.previous.time).total_seconds()
        else:
            return 1

    @prop
    def speed(self):
        # http://en.wikipedia.org/wiki/Speed#Definition
        speed = self.distance / self.period
        if 0 <= speed < Car.max_speed:
            return speed
        elif self.previous:
            return self.previous.speed
        else:
            return 0


    @prop
    def acceleration(self):
        if self.previous and self.previous.previous:
            # http://en.wikipedia.org/wiki/Acceleration#Definition_and_properties
            acceleration = (self.speed - self.previous.speed)/self.period
        else:
            acceleration = 0

        # car accelerating/decelerating more than g/2 is unlikely
        if Earth.g/2 < acceleration < Earth.g/2:
            return acceleration
        elif self.previous:
            return self.previous.acceleration
        else:
            return 0

    @prop
    def air_drag(self):
        # http://en.wikipedia.org/wiki/Drag_equation
        return 0.5 * Earth.air_density * Car.cda * self.speed**2

    @prop
    def rolling_resistance(self):
        # http://en.wikipedia.org/wiki/Rolling_resistance#Rolling_resistance_coefficient
        return Car.rrc * Car.mass * Earth.g * self.incline_cosinus

    @prop
    def incline_force(self):
        # http://en.wikipedia.org/wiki/Inclined_plane#Frictionless_inclined_plane
        return Car.mass * Earth.g * self.incline_sinus


    @prop
    def acceleration_force(self):
        # http://en.wikipedia.org/wiki/Force
        return Car.mass * self.acceleration

    @prop
    def force(self):
        return self.air_drag + self.rolling_resistance + self.incline_force + self.acceleration_force

    @prop
    def power_at_wheels(self):
        # http://en.wikipedia.org/wiki/Power_(physics)#Mechanical_power
        power = self.force * self.speed

        assert -Car.power * 2 < power < Car.power * 1.2

        return power

    @prop
    def output_power(self):
        if self.power_at_wheels > 0:
            return self.power_at_wheels / Car.mechanical_efficiency
        else:
            return 0

    @prop
    def regen_power(self):
        if self.power_at_wheels > 0:
            return 0
        else:
            return - self.power_at_wheels / Car.efficiency

    @prop
    def motor_power(self):
        if self.power_at_wheels > 0:
            return self.power_at_wheels / Car.mechanical_efficiency
        else:
            return - self.power_at_wheels * Car.mechanical_efficiency

    @prop
    def energy(self):
        power = self.output_power / Car.electrical_efficiency
        power -= self.regen_power * Car.electrical_efficiency
        # http://en.wikipedia.org/wiki/Power_(physics)#Average_power
        return power * self.period

    def __repr__(self):
        return '%s(%f, %f)' % (
            type(self).__name__,
            self.lat,
            self.lon
        )


class Track(object):
    gpx_path = 'gpx:trk/gpx:trkseg'

    def __init__(self, filename):
        self.filename = filename

    @property
    def tree(self):
        return xml.etree.ElementTree.parse(self.filename)

    @property
    def trk(self):
        trk, = self.tree.findall(self.gpx_path, gpx_namespaces)
        return trk

    @prop
    def points(self):
        "A list of track points."

        trkpts = self.trk.findall(Point.gpx_path, gpx_namespaces)
        return  [
            Point(self, index, trkpt) for
            (index, trkpt) in enumerate(trkpts)
        ]
        
    @prop
    def start_time(self):
        return self.points[0].time

    @prop
    def end_time(self):
        return self.points[-1].time

    @prop
    def duration(self):
        return (self.end_time - self.start_time).total_seconds() / 60.0

    @prop
    def distance(self):
        "Track distance [km]."
        return sum(point.distance for point in self.points) / 1000

    @prop
    def average_speed(self):
        "Average speed [km/h]."
        return self.distance/(self.duration/60)

    @prop
    def energy(self):
        "Energy needed for this track [Wh]"
        return sum(point.energy for point in self.points)/3600

    @prop
    def energy_rate(self):
        "Energy needed per km [Wh/km]."
        return self.energy/self.distance

    def sliding_window(self, attribute, width=20):
        "Sliding window with width points."
        for i in xrange(len(self.points)-width):
            window = self.points[i:i+width]
            values = [getattr(point, attribute) for point in window]
            yield sum(values)/len(values), window
    
    @prop
    def top_speed(self):
        "Top speed [km/h]."
        peak = max(self.sliding_window('speed', 15))
        return peak[0]*3600/1000, peak[1][0], peak[1][-1]

    @prop
    def peak_output_power(self):
        "Peak power needed [W]."
        peak = max(self.sliding_window('output_power'))
        return peak[0], peak[1][0], peak[1][-1]

    @prop
    def peak_regen_power(self):
        "Peak power available for regen [W]."
        peak = max(self.sliding_window('regen_power'))
        return peak[0], peak[1][0], peak[1][-1]

    @prop
    def average_motor_power(self):
        return sum(point.motor_power for point in self.points)/len(self.points)

    @prop
    def steepest_incline(self):
        "Steepest incline [percentage]."
        # altitude seems to calculated with 1m resolution
        # so we need to look at averages
        steepest = max(self.sliding_window('incline_sinus'))

        return steepest[0]*100, steepest[1][0], steepest[1][-1]
   
    @prop
    def steepest_decline(self):
        "Steepest decline [percentage]."
        # altitude seems to calculated with 1m resolution
        # so we need to look at averages
        steepest = min(self.sliding_window('incline_sinus'))

        return -steepest[0]*100, steepest[1][0], steepest[1][-1]

    @prop
    def stats(self):
        return {
            'distance': self.distance,
            'duration': self.duration,
            'average speed': self.average_speed,
            'energy': self.energy,
            'energy rate': self.energy_rate,
            'top speed': (
                self.top_speed[0],
                self.top_speed[1].url(self.top_speed[2])
            ),
            'average motor power': self.average_motor_power,
            'peak output power': (
                self.peak_output_power[0],
                self.peak_output_power[1].url(self.peak_output_power[2])
            ),
            'peak regen power': (
                self.peak_regen_power[0],
                self.peak_regen_power[1].url(self.peak_regen_power[2])
            ),
            'steepest incline': (
                self.steepest_incline[0],
                self.steepest_incline[1].url(self.steepest_incline[2])
            ),
            'steepest decline': (
                self.steepest_decline[0],
                self.steepest_decline[1].url(self.steepest_decline[2])
            )
        }


class Commute(object):
    def __init__(self, filenames):
        self.filenames = filenames

    @prop
    def tracks(self):
        tracks = []
        for filename in self.filenames:
            tracks.append(Track(filename))
        return tracks

    @prop
    def energy(self):
        return sum(track.energy for track in self.tracks)

    @prop
    def distance(self):
        return sum(track.distance for track in self.tracks)

    @prop
    def duration(self):
        return sum(track.duration for track in self.tracks)

    @prop
    def average_speed(self):
        return self.distance/(self.duration/60),
    
    @prop
    def top_speed(self):
        return max(track.top_speed[0] for track in self.tracks)

    @prop
    def energy_rate(self):
        return self.energy/self.distance

    @prop
    def peak_output_power(self):
        return max(track.peak_output_power[0] for track in self.tracks)
    
    @prop
    def average_motor_power(self):
        return sum(track.average_motor_power for track in self.tracks)/len(self.tracks)

    @prop
    def peak_regen_power(self):
        return max(track.peak_regen_power[0] for track in self.tracks)

    @prop
    def steepest_incline(self):
        return max(track.steepest_incline[0] for track in self.tracks)
        
    @prop
    def steepest_decline(self):
        return max(track.steepest_decline[0] for track in self.tracks)

    @prop
    def stats(self):
        return {
            'distance': self.distance,
            'duration': self.duration,
            'average speed': self.average_speed,
            'top speed': self.top_speed,
            'energy': self.energy,
            'energy rate': self.energy_rate,
            'peak output power': self.peak_output_power,
            'average motor power': self.average_motor_power,
            'peak regen power': self.peak_regen_power,
            'steepest incline': self.steepest_incline,
            'steepest decline': self.steepest_decline,
        }


def print_stats(stats):
    units = (
        ('distance', 'km'),
        ('duration', 'min'),
        ('average speed', 'km/h'),
        ('top speed', 'km/h'),
        ('energy', 'Wh'),
        ('energy rate', 'Wh/km'),
        ('average motor power', 'W'),
        ('peak output power', 'W'),
        ('steepest incline', '%'),
        ('peak regen power', 'W'),
        ('steepest decline', '%')
    )
    dunits = dict(units)
    
    for stat, unit in units:
        value = stats[stat]
        if isinstance(value, float):
            value = '%.02f %s' % (value, unit)
        elif isinstance(value, tuple):
            if isinstance(value[0], float):
                subvalue = '%.02f %s' % (value[0], unit)
                value = (subvalue,) + value[1:]

            value = ' '.join(str(v) for v in value)

        print '   %s: %s' % (
            stat,
            value
        )

if __name__ == '__main__':


    commute = Commute(sys.argv[1:])

    for track in commute.tracks:
        print 'Track', track.filename
        print_stats(track.stats)
        print

    print 'Total commute'
    print_stats(commute.stats)
        

