import os
import pandas as pd
import geopandas as gpd
from reegis_tools import coastdat
from reegis_tools import geometries
import reegis_tools.config as cfg
import multiprocessing
import pvlib
import deflex
import datetime
import logging
from oemof.tools import logger
from matplotlib import pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap


START = datetime.datetime.now()
YEARS = [2014, 2013, 2012, 2011, 2010, 2009, 2008, 2007, 2006, 2005, 2004,
         2003, 2002, 2001, 1999, 1998, 2000]


def pv_orientation(key, geom, weather, system, orientation, path):
    year = weather.index[0].year
    os.makedirs(path, exist_ok=True)
    latitude = geom.y
    longitude = geom.x

    start = datetime.datetime(year-1, 12, 31, 23, 30)
    end = datetime.datetime(year, 12, 31, 22, 30)
    naive_times = pd.DatetimeIndex(start=start, end=end, freq='1h')

    location = pvlib.location.Location(latitude=latitude, longitude=longitude)
    times = naive_times.tz_localize('Etc/GMT-1')
    solpos = pvlib.solarposition.get_solarposition(times, latitude, longitude)
    dni_extra = pvlib.irradiance.get_extra_radiation(times)
    airmass = pvlib.atmosphere.get_relative_airmass(solpos['apparent_zenith'])
    pressure = pvlib.atmosphere.alt2pres(location.altitude)
    am_abs = pvlib.atmosphere.get_absolute_airmass(airmass, pressure)

    # weather
    dhi = weather['dhi'].values
    ghi = dhi + weather['dirhi'].values
    dni = pvlib.irradiance.dni(ghi, dhi, solpos['zenith'],
                               clearsky_dni=None).fillna(0)
    wind_speed = weather['v_wind'].values
    temp_air = weather['temp_air'].values - 273.15

    s = pd.Series(index=pd.MultiIndex(levels=[[], []], labels=[[], []]))
    fix_tilt = -0.1
    for tilt, azimuth in orientation:
        if tilt > fix_tilt:
            dt = datetime.datetime.now() - START
            fix_tilt = tilt
            logging.info("{0} - {1}".format(tilt, dt))
        system['surface_azimuth'] = azimuth
        system['surface_tilt'] = tilt
        aoi = pvlib.irradiance.aoi(
            system['surface_tilt'], system['surface_azimuth'],
            solpos['apparent_zenith'], solpos['azimuth'])
        total_irrad = pvlib.irradiance.get_total_irradiance(
            system['surface_tilt'], system['surface_azimuth'],
            solpos['apparent_zenith'], solpos['azimuth'], dni, ghi, dhi,
            dni_extra=dni_extra, model='haydavies')
        temps = pvlib.pvsystem.sapm_celltemp(
            total_irrad['poa_global'], wind_speed, temp_air)
        effective_irradiance = pvlib.pvsystem.sapm_effective_irradiance(
            total_irrad['poa_direct'], total_irrad['poa_diffuse'], am_abs, aoi,
            system['module'])
        dc = pvlib.pvsystem.sapm(effective_irradiance, temps['temp_cell'],
                                 system['module'])
        ac = pvlib.pvsystem.snlinverter(dc['v_mp'], dc['p_mp'],
                                        system['inverter'])
        s[tilt, azimuth] = ac.sum() / system['installed_capacity']
    s.to_csv(os.path.join(path, str(key) + '.csv'))
    logging.info("{0}: {1} - {2}".format(
        year, key, datetime.datetime.now() - START))


def _pv_orientation(d):
    pv_orientation(**d)


def get_coastdat_onshore_polygons():
    cstd = geometries.load(
        cfg.get('paths', 'geometry'),
        cfg.get('coastdat', 'coastdatgrid_polygon'),
        index_col='gid')

    de02 = geometries.load(
        cfg.get('paths', 'geo_deflex'),
        cfg.get('geometry', 'deflex_polygon').format(
            type='polygon', map='de02', suffix='reegis'),
        index_col='region')

    cstd_pt = gpd.GeoDataFrame(cstd.centroid, columns=['geometry'])

    cstd_pt = geometries.spatial_join_with_buffer(
        cstd_pt, de02, 'coastdat', limit=0)
    reduced = cstd.loc[cstd_pt.coastdat == 1]
    return reduced.sort_index()


def pv_yield_by_orientation():
    global START
    START = datetime.datetime.now()

    reduced = get_coastdat_onshore_polygons()

    sandia_modules = pvlib.pvsystem.retrieve_sam('SandiaMod')
    sapm_inverters = pvlib.pvsystem.retrieve_sam('cecinverter')
    module = sandia_modules['LG_LG290N1C_G3__2013_']
    inverter = sapm_inverters['ABB__MICRO_0_25_I_OUTD_US_208_208V__CEC_2014_']
    system = {'module': module, 'inverter': inverter}

    system['installed_capacity'] = (system['module']['Impo'] *
                                    system['module']['Vmpo'])

    orientation_sets = []

    n = 2

    for n in range(18):
        ts = n * 10
        te = (n + 1) * 10
        if te == 90:
            te = 91
        orientation_sets.append(sorted(
            set((x/2, y/2) for x in range(ts, te) for y in range(0, 721))))

    year = 2014
    key = 1129089

    weather_file_name = os.path.join(
        cfg.get('paths', 'coastdat'),
        cfg.get('coastdat', 'file_pattern').format(year=year))
    if not os.path.isfile(weather_file_name):
        coastdat.get_coastdat_data(year, weather_file_name)
    weather = pd.read_hdf(weather_file_name, mode='r', key='/A' + str(key))

    path = os.path.join(
            cfg.get('paths', 'analysis'), 'pv_yield_by_orientation_c', '{0}')

    point = reduced.centroid[key]

    # pv_orientation(key, point, weather, system, orientation, path)
    coastdat_fields = []
    for orientation in orientation_sets:
        d = "tilt_{0}".format(str(orientation[0][0]).replace('.', ''))
        coastdat_fields.append({
            'key': key,
            'geom': point,
            'weather': weather,
            'system': system,
            'orientation': orientation,
            'path': path.format(d),
        })
    p = multiprocessing.Pool(6)
    p.map(_pv_orientation, coastdat_fields)
    p.close()
    p.join()


def optimal_pv_orientation():
    global START
    START = datetime.datetime.now()

    reduced = get_coastdat_onshore_polygons()

    sandia_modules = pvlib.pvsystem.retrieve_sam('SandiaMod')
    sapm_inverters = pvlib.pvsystem.retrieve_sam('cecinverter')
    module = sandia_modules['LG_LG290N1C_G3__2013_']
    inverter = sapm_inverters['ABB__MICRO_0_25_I_OUTD_US_208_208V__CEC_2014_']
    system = {'module': module, 'inverter': inverter}

    system['installed_capacity'] = (system['module']['Impo'] *
                                    system['module']['Vmpo'])

    orientation = sorted(
        set((x, y) for x in range(30, 46) for y in range(168, 193)))

    for year in YEARS:
        # Open coastdat-weather data hdf5 file for the given year or try to
        # download it if the file is not found.
        weather_file_name = os.path.join(
            cfg.get('paths', 'coastdat'),
            cfg.get('coastdat', 'file_pattern').format(year=year))
        if not os.path.isfile(weather_file_name):
            coastdat.get_coastdat_data(year, weather_file_name)

        path = os.path.join(
            cfg.get('paths', 'analysis'), 'pv_orientation_minus30', str(year))

        weather = pd.HDFStore(weather_file_name, mode='r')

        coastdat_fields = []
        for key, point in reduced.centroid.iteritems():
            coastdat_fields.append({
                'key': key,
                'geom': point,
                'weather': weather['/A' + str(key)],
                'system': system,
                'orientation': orientation,
                'path': path,
            })

        p = multiprocessing.Pool(4)
        p.map(_pv_orientation, coastdat_fields)
        p.close()
        p.join()
        weather.close()


def collect_orientation_files(year=None):
    base_path = os.path.join(cfg.get('paths', 'analysis'),
                             'pv_orientation_minus30')
    multi = pd.MultiIndex(levels=[[], []], labels=[[], []])
    df = pd.DataFrame(columns=multi, index=multi)

    if year is None:
        years = YEARS
    else:
        years = [year]

    for y in years:
        print(y)
        full_path = os.path.join(base_path, str(y))
        if os.path.isdir(full_path):
            for file in os.listdir(full_path):
                s = pd.read_csv(os.path.join(full_path, file),
                                index_col=[0, 1], squeeze=True,
                                header=None).sort_index()
                key = file[:-4]
                df[key, y] = s

    keys = df.columns.get_level_values(0).unique()

    new_df = pd.DataFrame(index=df.index)
    for key in keys:
        new_df[key] = df[key].sum(axis=1)
    new_df.index.set_names(['tilt', 'azimuth'], inplace=True)
    if year is None:
        outfile = 'multiyear_yield_sum.csv'
    else:
        outfile = 'yield_{0}.csv'.format(year)
    new_df.to_csv(os.path.join(base_path, outfile))


def collect_single_orientation_files():
    for year in YEARS:
        collect_orientation_files(year=year)


def combine_large_orientation_files():
    p = os.path.join(cfg.get('paths', 'analysis'), 'pv_yield_by_orientation')
    dfs = []
    key = None
    for root, dirs, files in os.walk(p):
        for f in files:
            if f[-4:] == '.csv':
                key = f[:-4]
                dfs.append(pd.read_csv(os.path.join(root, f),
                                       index_col=[0, 1], header=None))
    df = pd.concat(dfs).sort_index()
    df.to_csv(os.path.join(p, '{0}_combined.csv'.format(key)))
    print(df)


def analyse_multi_files():
    path = os.path.join(cfg.get('paths', 'analysis'), 'pv_orientation_minus30')
    fn = os.path.join(path, 'multiyear_yield_sum.csv')
    df = pd.read_csv(fn, index_col=[0, 1])
    gdf = get_coastdat_onshore_polygons()
    gdf.geometry = gdf.buffer(0.005)

    for key in gdf.index:
        s = df[str(key)]
        p = gdf.loc[key]
        gdf.loc[key, 'tilt'] = (
            s[s == s.max()].index.get_level_values('tilt')[0])
        gdf.loc[key, 'azimuth'] = (
            s[s == s.max()].index.get_level_values('azimuth')[0])
        gdf.loc[key, 'longitude'] = p.geometry.centroid.x
        gdf.loc[key, 'latitude'] = p.geometry.centroid.y
        gdf.loc[key, 'tilt_calc'] = round(p.geometry.centroid.y - 15)
        gdf.loc[key, 'tilt_diff'] = (gdf.loc[key, 'tilt_calc'] -
                                     gdf.loc[key, 'tilt'])
    cmap = plt.get_cmap('viridis', 8)
    cm_gyr = LinearSegmentedColormap.from_list(
        'mycmap', [
            (0, 'red'),
            (0.25, 'yellow'),
            (0.5, 'green'),
            (0.75, 'yellow'),
            (1, 'red')], 11)
    print(gdf.azimuth.max(), gdf.azimuth.min())
    print(gdf.tilt.max(), gdf.tilt.min())
    print(gdf.tilt_diff.max(), gdf.tilt_diff.min())
    f, ax_ar = plt.subplots(1, 3, figsize=(15, 3))
    # gdf.plot('azimuth', legend=True, cmap=cmap, vmin=172.5, vmax=184.5,
    #              ax=ax_ar[0])
    gdf.plot('tilt', legend=True, ax=ax_ar[1], vmin=32.5, vmax=40.5, cmap=cmap)
    gdf.plot('tilt_calc', legend=True, ax=ax_ar[0], vmin=32.5, vmax=40.5,
             cmap=cmap)
    gdf.plot(
        'tilt_diff', legend=True, vmin=-5.5, vmax=5.5,
        cmap=cm_gyr, ax=ax_ar[2])
    plt.show()


def polar_plot():
    key = 1129089
    p = os.path.join(cfg.get('paths', 'analysis'), 'pv_yield_by_orientation')
    fn = os.path.join(p, '{0}_combined.csv'.format(key))

    df = pd.read_csv(fn, index_col=[0, 1], header=None)
    df.reset_index(inplace=True)

    # Data
    tilt = df[0]
    azimuth = df[1] / 180 * np.pi
    colors = df[2] / df[2].max()

    # Colormap
    cmap = plt.get_cmap('viridis', 8)

    # Plot
    fig = plt.figure(figsize=(8, 6))
    ax = fig.add_subplot(111, projection='polar')
    sc = ax.scatter(azimuth, tilt, c=colors, cmap=cmap, alpha=1, vmin=0.2)

    # Colorbar
    label = "Anteil vom maximalen Ertrag"
    cax = fig.add_axes([0.89, 0.05, 0.03, 0.92])
    fig.colorbar(sc, cax=cax, label=label, ticks=[0, 0.2, 0.4, 0.6, 0.8, 1])
    ax.set_theta_zero_location('S', offset=0)

    # Adjust radius
    ax.set_rmax(90)
    ax.set_rlabel_position(110)

    # Adjust margins
    plt.subplots_adjust(right=0.94, left=0, bottom=0.08, top=0.93)
    plt.savefig(os.path.join(p, 'polar_plot_{0}.png'.format(key)))


if __name__ == "__main__":
    logger.define_logging()
    cfg.init(paths=[os.path.dirname(deflex.__file__)])
    # combine_large_orientation_files()
    # optimal_pv_orientation()
    pv_yield_by_orientation()
    # collect_orientation_files()
    # collect_single_orientation_files()
    # plt.show()
    # scatter()
    # analyse_multi_files()
    # polar_plot()
