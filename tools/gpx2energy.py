#!/usr/bin/env python

import datetime
import functools
import math
import sys
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

    electrical_efficiency = battery_pack_efficiency * controller_efficiency

    mechanical_efficiency = motor_efficiency * gearbox_efficiency


    regen_efficiency = electrical_efficiency

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
            raise ValueError("impossible speed %s" % speed)


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
    def power(self):
        # http://en.wikipedia.org/wiki/Power_(physics)#Mechanical_power
        power = self.force * self.speed

        assert -Car.power * 2 < power < Car.power * 1.2

        if power >= 0:
            power /= Car.mechanical_efficiency
        else:
            power *= Car.regen_efficiency

        return power

    @prop
    def energy(self):
        # http://en.wikipedia.org/wiki/Power_(physics)#Average_power
        energy = self.power * self.period
        if energy > 0:
            energy /= Car.electrical_efficiency
        else:
            energy *= Car.electrical_efficiency

        return energy

    def __repr__(self):
        return '%s(%f, %f)' % (
            type(self).__name__,
            self.lat,
            self.lon
        )


class Track(object):
    gpx_path = 'gpx:trk/gpx:trkseg'

    def __init__(self, tree):
        tracks = tree.findall(self.gpx_path, gpx_namespaces)
        self.trk, = tracks

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
    def distance(self):
        "Track distance [km]."
        return sum(point.distance for point in self.points) / 1000

    @prop
    def energy(self):
        "Energy needed for this track [Wh]"
        return sum(point.energy for point in self.points)/3600

    @prop
    def energy_rate(self):
        "Energy needed per km [Wh/km]."
        return self.energy/self.distance

    @prop
    def max_power(self):
        "Peak power needed [W]."
        return max(point.power for point in self.points)

    @prop
    def max_regen_power(self):
        "Peak power available for regen [W]."
        return -min(point.power for point in self.points)

    @prop
    def stats(self):
        return {
            'distance': self.distance,
            'energy': self.energy,
            'energy_rate': self.energy_rate,
            'max_power': self.max_power,
            'max_regen_power': self.max_regen_power
        }


class Commute(object):
    def __init__(self, filenames):
        self.filenames = filenames

    @prop
    def tracks(self):
        tracks = {}
        for filename in self.filenames:
            tree = xml.etree.ElementTree.parse(filename)
            tracks[filename] = Track(tree)
        return tracks

    @prop
    def energy(self):
        return sum(track.energy for track in self.tracks.values())

    @prop
    def distance(self):
        return sum(track.distance for track in self.tracks.values())

    @prop
    def energy_rate(self):
        return self.energy/self.distance

    @prop
    def max_power(self):
        return max(track.max_power for track in self.tracks.values())

    @prop
    def max_regen_power(self):
        return max(track.max_regen_power for track in self.tracks.values())

    @prop
    def stats(self):
        return {
            'distance': self.distance,
            'energy': self.energy,
            'energy_rate': self.energy_rate,
            'max_power': self.max_power,
            'max_regen_power': self.max_regen_power
        }


def print_stats(stats):
    units = {
        'distance': 'km',
        'energy': 'Wh',
        'energy_rate': 'Wh/km',
        'max_power': 'W',
        'max_regen_power': 'W',
    }
    
    for stat, value in stats.iteritems():
        print '   %s: %.02f %s' % (
            stat,
            value,
            units[stat]
        )

if __name__ == '__main__':


    commute = Commute(sys.argv[1:])

    for filename, track in commute.tracks.iteritems():
        print 'Track', filename
        print_stats(track.stats)
        print

    print 'Total commute'
    print_stats(commute.stats)
        

