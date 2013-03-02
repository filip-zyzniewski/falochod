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

import functools

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

def total_seconds(delta):
	total = delta.seconds
	total += delta.days * 60*60*24
	total += delta.microseconds/1000.0
	return total
