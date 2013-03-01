#!/usr/bin/env python

"""
An utility calculating power and energy requirements
for a commute recorded in GPX files.

Author: Filip Zyzniewski <filip.zyzniewski@gmail.com>

License:

    This file is part of gpx2energy.

    gpx2energy is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    Foobar is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with gpx2energy.  If not, see <http://www.gnu.org/licenses/>.
"""

import datetime
import functools
import math
import operator
import sys
import urllib
import xml.etree.ElementTree

gpx_namespaces = {'gpx': 'http://www.topografix.com/GPX/1/1'}

class prop(property):
    "A property that caches the result for future accesses."

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
    "Class representing the Earth."

    # http://en.wikipedia.org/wiki/Earth_radius
    radius = 6371*1000 # [m]

    # gravitational acceleration [m/s^2]
    # http://pl.wikipedia.org/wiki/Przyspieszenie_ziemskie#Wybrane_warto.C5.9Bci_przyspieszenia_ziemskiego_.5Bm.2Fs.C2.B2.5D
    # for Krakow
    g = 9.8105

    # http://en.wikipedia.org/wiki/Density_of_air
    # at 0 degrees C
    air_density = 1.2922 # [kg/m^3]

class Car(object):
    # smart fortwo

    # Drag coefficient
    # http://clubsmartcar.com/index.php?showtopic=9972
    cx = 0.37

    # http://clubsmartcar.com/index.php?showtopic=9972
    frontal_area = 1.95 # [m^2]

    # Drag area
    # http://en.wikipedia.org/wiki/Drag_area
    cda = cx * frontal_area # [m^2]

    # including the driver and batteries
    mass = 880 # [kg]

    # tyres and brakes/steering
    # rolling resistance coefficient
    rrc = 0.01355 # [kg/kg]

    # ICE power of the vehicle used to create
    # the GPX file [W]
    power = 40000
    
    # max speed [m/s]
    max_speed = 100*1000/3600
    
    battery_pack_efficiency = 0.95
    controller_efficiency = 0.95
    motor_efficiency = 0.87
    gearbox_efficiency = 0.9


    def __init__(self, properties={}):
        vars(self).update(properties)

    @prop
    def weight(self):
        "Weight of the car [N]."
        # http://en.wikipedia.org/wiki/Weight#ISO_definition
        return self.mass * Earth.g

    @prop
    def electrical_efficiency(self):
        return self.battery_pack_efficiency * \
               self.controller_efficiency * \
               self.motor_efficiency

    @prop
    def mechanical_efficiency(self):
        return self.gearbox_efficiency

    @prop
    def efficiency(self):
        return self.electrical_efficiency * self.mechanical_efficiency

class Point(object):
    "Class representing a single point of a track."

    gpx_path = 'gpx:trkpt'

    def __init__(self, track, index, trkpt):
        self.track = track
        self.car = track.car
        self.index = index
        self.lat = float(trkpt.attrib['lat'])
        self.lon = float(trkpt.attrib['lon'])
        self.elevation = float(trkpt.find('gpx:ele', gpx_namespaces).text)
        time = trkpt.find('gpx:time', gpx_namespaces).text
        self.time = datetime.datetime.strptime(time[:-1],'%Y-%m-%dT%H:%M:%S.%f')

    @prop
    def previous(self):
        "Previous point of the track."
        if self.index > 0:
            return self.track.points[self.index - 1]

    @prop
    def next(self):
        "Next point of the track."
        if self.index < len(self.track.points) - 1:
            return self.track.points[self.index + 1]

    def url(self, other=None):
        """Google maps URL of the point or
        a route from the point to another."""

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
        "Distance from the previous point as seen from the sky [m]."
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
        "Actual road distance from the previous point [m]."
        # http://en.wikipedia.org/wiki/Pythagorean_theorem
        return math.sqrt(self.flat_distance**2 + self.climb**2)

    @prop
    def climb(self):
        "Height increase [m]."
        # unfortunately my Android phone provides 1m elevation
        # resolution, which affects momentary
        # calculations precision badly
        if self.previous:
            return self.elevation - self.previous.elevation
        else:
            return 0

    @prop
    def incline_sine(self):
        "Sine of the climb angle."
        try:
            # http://en.wikipedia.org/wiki/Trigonometric_functions#Right-angled_triangle_definitions
            sine = self.climb / self.distance
        except ZeroDivisionError:
            sine = 1

        if -0.25 < sine < 0.25:
            # reasonable value
            return sine
        else:
            if self.previous:
                return self.previous.incline_sine
            else:
                return 0

    @prop
    def incline_cosine(self):
        "Cosine of the climb angle."
        try:
            # http://en.wikipedia.org/wiki/Trigonometric_functions#Right-angled_triangle_definitions
            cosine = self.flat_distance / self.distance
        except ZeroDivisionError:
            cosine = 0
        if 0.75 < cosine <= 1: 
            # reasonable value
            return cosine
        else:
            if self.previous:
                return self.previous.incline_cosine
            else:
                return 1

    @prop
    def period(self):
        "Time since the previous point [s]."
        if self.previous:
            return (self.time - self.previous.time).total_seconds()
        else:
            return 1

    @prop
    def speed(self):
        "Vehicle speed [m/s]."
        # http://en.wikipedia.org/wiki/Speed#Definition
        speed = self.distance / self.period
        if 0 <= speed < self.car.max_speed:
            return speed
        elif self.previous:
            return self.previous.speed
        else:
            return 0


    @prop
    def acceleration(self):
        "Vehicle acceleration [m/s^2]."
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
        "Force of air drag [N]."
        # http://en.wikipedia.org/wiki/Drag_equation
        return 0.5 * Earth.air_density * self.car.cda * self.speed**2

    @prop
    def rolling_resistance(self):
        "Force of rolling resistance [N]."
        # http://en.wikipedia.org/wiki/Rolling_resistance#Rolling_resistance_coefficient
        return self.car.rrc * self.car.mass * Earth.g * self.incline_cosine

    @prop
    def incline_force(self):
        "Gravitational backwards force of the incline [N]."
        # http://en.wikipedia.org/wiki/Inclined_plane#Frictionless_inclined_plane
        return self.car.mass * Earth.g * self.incline_sine


    @prop
    def acceleration_force(self):
        "Force needed for acceleration [N]."
        # http://en.wikipedia.org/wiki/Force
        return self.car.mass * self.acceleration

    @prop
    def force(self):
        "Total force generated by the drivetrain [N]."
        return self.air_drag + self.rolling_resistance + self.incline_force + self.acceleration_force

    @prop
    def power_at_wheels(self):
        "Driving power without drivetrain losses [W]."
        # http://en.wikipedia.org/wiki/Power_(physics)#Mechanical_power
        power = self.force * self.speed

        assert -self.car.power * 2 < power < self.car.power * 1.2

        return power

    @prop
    def output_power(self):
        "Power generated by the motor [W]."
        if self.power_at_wheels > 0:
            return self.power_at_wheels / self.car.mechanical_efficiency
        else:
            return 0

    @prop
    def regen_power(self):
        "Regen power reaching the batteries [W]."
        if self.power_at_wheels > 0:
            return 0
        else:
            return - self.power_at_wheels / self.car.efficiency

    @prop
    def motor_power(self):
        "Motor power requirement [W]."
        if self.power_at_wheels > 0:
            return self.power_at_wheels / self.car.mechanical_efficiency
        else:
            # Regen stresses the motor too
            return - self.power_at_wheels * self.car.mechanical_efficiency

    @prop
    def energy(self):
        "Energy used to travel from the previous point [J]."
        power = self.output_power / self.car.electrical_efficiency
        power -= self.regen_power * self.car.electrical_efficiency
        # http://en.wikipedia.org/wiki/Power_(physics)#Average_power
        return power * self.period

    def __repr__(self):
        return '%s(%f, %f)' % (
            type(self).__name__,
            self.lat,
            self.lon
        )


class Track(object):
    "Class representing a track recorded with a GPS device."

    gpx_path = 'gpx:trk/gpx:trkseg'

    def __init__(self, commute, file):
        self.commute = commute
        self.car = commute.car
        if hasattr(file, 'read'):
            self.file = file
            self.filename = self.file.name
        else:
            self.file = file
            self.filename = file

    @property
    def tree(self):
        "Parsed XML tree."
        return xml.etree.ElementTree.parse(self.file)

    @property
    def trk(self):
        "Track segment from the XML tree."
        # For now I assume one trkseg per file.
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
        "Start time of the journey."
        return self.points[0].time

    @prop
    def end_time(self):
        "End time of the journey."
        return self.points[-1].time

    @prop
    def duration(self):
        "Duration of the journey [s]."
        return (self.end_time - self.start_time).total_seconds() / 60.0

    @prop
    def distance(self):
        "Travelled distance [km]."
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
        "Sliding average window with width points."
        for i in xrange(len(self.points)-width):
            window = self.points[i:i+width]
            values = [getattr(point, attribute) for point in window]
            yield sum(values)/len(values), window
    
    @prop
    def top_speed(self):
        "Max speed [km/h] and points where it has been rached."
        peak = max(self.sliding_window('speed', 15))
        return peak[0]*3600/1000, peak[1][0], peak[1][-1]

    @prop
    def peak_output_power(self):
        "Peak power needed [W] and points where it was needed."
        peak = max(self.sliding_window('output_power'))
        return peak[0], peak[1][0], peak[1][-1]

    @prop
    def peak_regen_power(self):
        "Peak power available for regen [W] and points where it was available."
        peak = max(self.sliding_window('regen_power'))
        return peak[0], peak[1][0], peak[1][-1]

    @prop
    def average_motor_power(self):
        "Average power generated and regen'd by the motor [W]."
        return sum(point.motor_power for point in self.points)/len(self.points)

    @prop
    def steepest_incline(self):
        "Steepest incline [%]."
        steepest = max(self.sliding_window('incline_sine'))

        return steepest[0]*100, steepest[1][0], steepest[1][-1]
   
    @prop
    def steepest_decline(self):
        "Steepest decline [%]."
        steepest = min(self.sliding_window('incline_sine'))

        return -steepest[0]*100, steepest[1][0], steepest[1][-1]

    @prop
    def stats(self):
        "Track stats."
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
    """Groups together tracks, for example two tracks
    for both directions of the commute."""

    def __init__(self, car, files):
        self.car = car
        self.files = files

    @prop
    def tracks(self):
        "Tracks making up this commute."
        tracks = []
        for file in self.files:
            tracks.append(Track(self, file))
        return tracks

    @prop
    def energy(self):
        "Energy needed for this commute [Wh]."
        return sum(track.energy for track in self.tracks)

    @prop
    def distance(self):
        "Total distance travelled [km]"
        return sum(track.distance for track in self.tracks)

    @prop
    def duration(self):
        "Total duration of the commute."
        return sum(track.duration for track in self.tracks)

    @prop
    def average_speed(self):
        "Average speed [km/h]."
        return self.distance/(self.duration/60)
    
    @prop
    def top_speed(self):
        "Max speed reached during the commute [km/h]."
        return max(track.top_speed[0] for track in self.tracks)

    @prop
    def energy_rate(self):
        "Energy consumption rate of the commute [Wh/km]."
        return self.energy/self.distance

    @prop
    def peak_output_power(self):
        "Peak output power needed during the commute [W]."
        return max(track.peak_output_power[0] for track in self.tracks)
    
    @prop
    def average_motor_power(self):
        "Average power generated and regen'd by the motor during the commute [W]."
        return sum(track.average_motor_power for track in self.tracks)/len(self.tracks)

    @prop
    def peak_regen_power(self):
        "Peak power available for regen during the commute [W]."
        return max(track.peak_regen_power[0] for track in self.tracks)

    @prop
    def steepest_incline(self):
        "Steepest incline during the commute [%]."
        return max(track.steepest_incline[0] for track in self.tracks)
        
    @prop
    def steepest_decline(self):
        "Steepest decline during the commute [%]."
        return max(track.steepest_decline[0] for track in self.tracks)

    @prop
    def stats(self):
        "Commute stats."
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

stats_units = (
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

def print_stats(stats):
    for stat, unit in stats_units:
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

    if len(sys.argv) > 1:
        commute = Commute(Car(), sys.argv[1:])

        for track in commute.tracks:
            print 'Track', track.filename
            print_stats(track.stats)
            print

        print 'Total commute'
        print_stats(commute.stats)
    else:
        sys.stderr.write('Usage: %s file.gps [...]\n' % sys.argv[0])
        sys.exit(1)
        

