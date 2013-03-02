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
import math
import sys
import urllib
import track_physics
import xml.etree.ElementTree

from utils import prop, print_stats

gpx_namespaces = {'gpx': 'http://www.topografix.com/GPX/1/1'}

Earth = track_physics.Earth
Car = track_physics.Car

class Point(track_physics.Point):
    "Class representing a single point of a track."

    gpx_path = '{%s}trkpt' % gpx_namespaces['gpx']
    ele_path = '{%s}ele' % gpx_namespaces['gpx']
    time_path = '{%s}time' % gpx_namespaces['gpx']

    def __init__(self, track, index, trkpt):
        self.track = track
        self.car = track.car
        self.index = index
        self.lat = float(trkpt.attrib['lat'])
        self.lon = float(trkpt.attrib['lon'])
        self.elevation = float(trkpt.find(self.ele_path).text)
        time = trkpt.find(self.time_path).text
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

    def __repr__(self):
        return '%s(%f, %f)' % (
            type(self).__name__,
            self.lat,
            self.lon
        )


class Track(track_physics.Track):
    "Class representing a track recorded with a GPS device."

    gpx_path = '{%s}trk/{%s}trkseg' % (
        gpx_namespaces['gpx'],
        gpx_namespaces['gpx']
    )

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
        trk, = self.tree.findall(self.gpx_path)
        return trk

    @prop
    def points(self):
        "A list of track points."
        trkpts = self.trk.findall(Point.gpx_path)
        return  [
            Point(self, index, trkpt) for
            (index, trkpt) in enumerate(trkpts)
        ]
        
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


class Commute(track_physics.Commute):
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
        

