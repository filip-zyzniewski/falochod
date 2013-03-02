import flask
import track_gpx
import utils

"""
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

app = flask.Flask(__name__)


def stats2table(stats):
    for stat, unit in utils.stats_units:
        value = stats[stat]
        if isinstance(value, tuple):
            url = value[1]
            value = value[0]
        else:
            url = None

        if isinstance(value, float):
            value = '%.02f' % value

        yield stat, url, value, unit

@app.route('/', methods=['GET', 'POST'])
def index():
    files = flask.request.files.values()
    files = [file for file in files if file.filename]

    if flask.request.method == 'POST' and files:
        form = dict(flask.request.form)
        form.pop('submit')

        form = dict((k, float(v[0])) for (k,v) in form.iteritems())

        form['power'] *= 1000
        form['max_speed'] *= 1000/3600.0
        for efficiency in [
            'battery_pack_efficiency',
            'controller_efficiency',
            'motor_efficiency',
            'gearbox_efficiency'
        ]:
            form[efficiency] /= 100.0

        car = track_gpx.Car()
        vars(car).update(form)

        for file in files:
            file.name = file.filename


        commute = track_gpx.Commute(car, files)
    else:
        commute = None

    return flask.render_template('gpx2energy.html',
        commute=commute,
        stats2table=stats2table,
        getattr=getattr
    )

@app.route('/manual')
def manual():
    return flask.render_template('manual.html')

if __name__ == '__main__':
    app.run()
