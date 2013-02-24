#!/usr/bin/env python

import collections
import datetime
import itertools
import math
import pdb
import sys
import xml.etree.ElementTree

gpx_namespaces = {
    'gpx': 'http://www.topografix.com/GPX/1/1'
}

_earth_radius = 6371*1000

def dt_fromiso(iso):
    return datetime.datetime.strptime(iso[:-1],'%Y-%m-%dT%H:%M:%S.%f')

def distance(a, b):
    """
    Calculates distance between two points
    This is the `Haversine formula <http://en.wikipedia.org/wiki/Haversine_formula>`__.

    :param a: first point (lat, lon)
    :type a: (float, float)
    :param b: second point (lat, lon)
    :type b: (float, float):
    :return: distance between a and b in meters
    :rtype: float
    """
    
    dlat = math.radians(b[0] - a[0])
    dlon = math.radians(b[1] - a[1])

    a = math.sin(dlat/2) ** 2 + math.cos(math.radians(a[0])) \
        * math.cos(math.radians(b[0])) * math.sin(dlon/2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    d = _earth_radius * c

    return d

DataPoint = collections.namedtuple(
    'DataPoint',
    ['distance', 'elevation', 'time']
)

def datapoints(tree):
    path = 'gpx:trk/gpx:trkseg/gpx:trkpt'
    oldpos = None
    for point in tree.findall(path, gpx_namespaces):
        pos  = float(point.attrib['lat']), float(point.attrib['lon'])
        ele = float(point.find('gpx:ele', gpx_namespaces).text)
        timestamp = point.find('gpx:time', gpx_namespaces).text
        timestamp = dt_fromiso(timestamp)
        if oldpos:
            time = (timestamp-oldtimestamp).total_seconds()
            yield DataPoint(
                distance = distance(pos, oldpos),
                elevation = ele - oldele,
                time = time
            )
        oldpos = pos
        oldele = ele
        oldtimestamp = timestamp

if __name__ == '__main__':
    filenames = sys.argv[1:]
    trees = (xml.etree.ElementTree.parse(f) for f in filenames)
    datasets = itertools.imap(datapoints, trees)
    for point in itertools.chain.from_iterable(datasets):
        print point
