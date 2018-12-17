import os
import logging
from datetime import datetime

from deflex import Scenario

from oemof import graph
from oemof.tools import logger
from oemof import solph as solph
from oemof import outputlib

from my_reegis import analyzer

import pandas as pd
import reegis_tools.config as cfg
import reegis_tools.gui as gui

from deflex.scenario_tools import Label as Label


def stopwatch():
    if not hasattr(stopwatch, 'start'):
        stopwatch.start = datetime.now()
    return str(datetime.now() - stopwatch.start)[:-7]


def get_file_name_doctests():
    fn1 = os.path.join(cfg.get('paths', 'scenario'), 'deflex', '2014',
                       'results', 'deflex_2014_de21.esys')
    fn2 = os.path.join(cfg.get('paths', 'scenario'), 'deflex', '2013',
                       'results', 'deflex_2013_de21.esys')
    return fn1, fn2


def compare_transmission(es1, es2, name1='es1', name2='es2', noreg='DE22'):
    """
    Compare the transmission between two scenarios in a DataFrame.

    Parameters
    ----------
    es1 : oemof.solph.EnergySystem
        Solph energy system with results.
    es2 : oemof.solph.EnergySystem
    name1 : str (optional)
        Short name to identify the first energy system in the DataFrame
    name2 : str (optional)
        Short name to identify the second energy system in the DataFrame
    noreg : str
        Name of a region that should be ignored. At the moment you can only
        choose one region.

    Returns
    -------
    pd.DataFrame

    Examples
    --------
    >>> fn1, fn2 = get_file_name_doctests()
    >>> my_es1 = load_es(fn1)
    >>> my_es2 = load_es(fn2)
    >>> my_df = compare_transmission(my_es1, my_es2, noreg='DE22')
    >>> isinstance(my_df, pd.DataFrame)
    True
    """
    results1 = es1.results['Main']
    results2 = es2.results['Main']
    parameter = es1.results['Param']

    out_flow_lines = [x for x in results1.keys() if
                      ('line' in x[0].label.cat) &
                      (noreg not in x[0].label.subtag) &
                      (noreg not in x[0].label.region)]

    # Calculate results
    transmission = pd.DataFrame()
    for out_flow in out_flow_lines:

        # es1
        line_a_1 = out_flow[0]
        bus_reg1_1 = [x for x in line_a_1.inputs][0]
        bus_reg2_1 = out_flow[1]
        line_b_1 = es1.groups['_'.join(['line', 'electricity',
                                        bus_reg2_1.label.region,
                                        bus_reg1_1.label.region])]

        # es2
        bus_reg1_2 = es2.groups[str(bus_reg1_1.label)]
        bus_reg2_2 = es2.groups[str(bus_reg2_1.label)]
        line_a_2 = es2.groups[str(line_a_1.label)]
        line_b_2 = es2.groups[str(line_b_1.label)]

        from1to2_es1 = results1[(line_a_1, bus_reg2_1)]['sequences']
        from2to1_es1 = results1[(line_b_1, bus_reg1_1)]['sequences']
        from1to2_es2 = results2[(line_a_2, bus_reg2_2)]['sequences']
        from2to1_es2 = results2[(line_b_2, bus_reg1_2)]['sequences']

        line_capacity = (parameter[(line_a_1, bus_reg2_1)]['scalars']
                         .nominal_value)

        line_name = '-'.join([line_a_1.label.subtag, line_a_1.label.region])

        transmission.loc[line_name, 'capacity'] = line_capacity

        # Annual balance for each line and each energy system
        transmission.loc[line_name, name1] = float(from1to2_es1.sum() -
                                                   from2to1_es1.sum()) / 1000
        transmission.loc[line_name, name2] = float(from1to2_es2.sum() -
                                                   from2to1_es2.sum()) / 1000

        relative_usage1 = (from1to2_es1 + from2to1_es1).div(
            line_capacity).flow.fillna(0)
        relative_usage2 = (from1to2_es2 + from2to1_es2).div(
            line_capacity).flow.fillna(0)

        # How many days of min 90% usage
        transmission.loc[line_name, name1 + '_90+_usage'] = (
            relative_usage1.multiply(10).astype(int).value_counts(
                ).sort_index().iloc[9:].sum())
        transmission.loc[line_name, name2 + '_90+_usage'] = (
            relative_usage1.multiply(10).astype(int).value_counts(
                ).sort_index().iloc[9:].sum())
        transmission.loc[line_name, 'diff_2-1_90+_usage'] = (
            transmission.loc[line_name, name2 + '_90+_usage'] -
            transmission.loc[line_name, name1 + '_90+_usage'])

        # How many days of min MAX usage
        transmission.loc[line_name, name1 + '_max_usage'] = (
            relative_usage1.multiply(10).astype(int).value_counts(
                ).sort_index().iloc[10:].sum())
        transmission.loc[line_name, name2 + '_max_usage'] = (
            relative_usage1.multiply(10).astype(int).value_counts(
                ).sort_index().iloc[10:].sum())
        transmission.loc[line_name, 'diff_2-1_max_usage'] = (
            transmission.loc[line_name, name2 + '_max_usage'] -
            transmission.loc[line_name, name1 + '_max_usage'])

        # Average relative usage
        transmission.loc[line_name, name1 + '_avg_usage'] = (
            relative_usage1.mean() * 100)
        transmission.loc[line_name, name2 + '_avg_usage'] = (
            relative_usage2.mean() * 100)
        transmission.loc[line_name, 'diff_2-1_avg_usage'] = (
            transmission.loc[line_name, name2 + '_avg_usage'] -
            transmission.loc[line_name, name1 + '_avg_usage'])

        # Absolute annual flow for each line
        transmission.loc[line_name, name1 + '_abs'] = float(
            from1to2_es1.sum() + from2to1_es1.sum() / 1000)
        transmission.loc[line_name, name2 + '_abs'] = float(
            from1to2_es2.sum() + from2to1_es2.sum() / 1000)

        # Maximum peak value for each line and each energy system
        transmission.loc[line_name, name1 + '_max'] = float(
            from1to2_es1.abs().max() - from2to1_es1.abs().max()) / 1000
        transmission.loc[line_name, name2 + '_max'] = float(
            from1to2_es2.abs().max() - from2to1_es2.abs().max()) / 1000

    transmission['diff_2-1'] = transmission[name2] - transmission[name1]
    transmission['diff_2-1_max'] = (transmission[name2 + '_max'] -
                                    transmission[name1 + '_max'])
    transmission['diff_2-1_abs'] = (transmission[name2 + '_abs'] -
                                    transmission[name1 + '_abs'])
    transmission['fraction'] = (transmission['diff_2-1'] /
                                abs(transmission[name1]) * 100)
    transmission['fraction'].fillna(0, inplace=True)

    return transmission


def reshape_bus_view(es, bus, data=None, aggregate_lines=True):
    """
    Create a MultiIndex DataFrame with all Flows around the given Bus object.

    Parameters
    ----------
    es : oemof.solph.EnergySystem
        Solph energy system with results.
    bus : solph.Bus or list
        Bus
    data : pandas.DataFrame
        MultiIndex DataFrame to add the results to.
    aggregate_lines : bool
        If True all incoming lines will be aggregated to import and outgoing
        lines to export.

    Returns
    -------
    pandas.DataFrame

    Examples
    --------
    >>> fn1, fn2 = get_file_name_doctests()
    >>> my_es = load_es(fn1)
    >>> my_bus = get_nodes_by_label(
    ...    my_es, ('bus', 'electricity', None, 'DE10'))
    >>> my_df = reshape_bus_view(my_es, my_bus).sum()
    """
    if data is None:
        m_cols = pd.MultiIndex(levels=[[], [], [], [], []],
                               labels=[[], [], [], [], []])
        data = pd.DataFrame(columns=m_cols)

    if not isinstance(bus, list):
        buses = [bus]
    else:
        buses = bus

    for bus in buses:
        # filter all nodes and sub-list import/exports
        node_flows = [x for x in es.results['Main'].keys()
                      if (x[1] == bus or x[0] == bus) and x[1] is not None]

        if len([x for x in node_flows if (x[1].label.cat == 'line') or
                                         (x[0].label.cat == 'line')]) == 0:
            aggregate_lines = False

        # If True all power lines will be aggregated to import/export
        if aggregate_lines is True:
            export_flows = [x for x in node_flows if x[1].label.cat == 'line']
            import_flows = [x for x in node_flows if x[0].label.cat == 'line']

            # only export lines
            export_label = (bus.label.region, 'out', 'export', 'electricity',
                            'all')

            data[export_label] = (
                    es.results['Main'][export_flows[0]]['sequences']['flow']
                    * 0)
            for export_flow in export_flows:
                data[export_label] += (
                    es.results['Main'][export_flow]['sequences']['flow'])
                node_flows.remove(export_flow)

            # only import lines
            import_label = (bus.label.region, 'in', 'import', 'electricity',
                            'all')
            data[import_label] = (
                    es.results['Main'][import_flows[0]]['sequences']['flow']
                    * 0)
            for import_flow in import_flows:
                data[import_label] += (
                    es.results['Main'][import_flow]['sequences']['flow'])
                node_flows.remove(import_flow)

        # all flows without lines (import/export)
        for flow in node_flows:
            if flow[0] == bus:
                flow_label = (bus.label.region, 'out', flow[1].label.cat,
                              flow[1].label.tag, flow[1].label.subtag)
            elif flow[1] == bus:
                flow_label = (bus.label.region, 'in', flow[0].label.cat,
                              flow[0].label.tag, flow[0].label.subtag)
            else:
                flow_label = None

            if flow_label in data:
                data[flow_label] += (
                    es.results['Main'][flow]['sequences']['flow'])
            else:
                data[flow_label] = (
                    es.results['Main'][flow]['sequences']['flow'])

    return data.sort_index(axis=1)


def get_multiregion_bus_balance(es, bus_substring=None):
    """

    Parameters
    ----------
    es : solph.EnergySystem
        An EnergySystem with results.
    bus_substring : str or tuple
        A sub-string or sub-tuple to find a list of buses.

    Returns
    -------
    pd.DataFrame : Multi-regional results.

    Examples
    --------
    >>> fn1, fn2 = get_file_name_doctests()
    >>> my_es = load_es(fn1)
    >>> my_df = get_multiregion_bus_balance(
    ...    my_es, bus_substring='bus_electricity')
    >>> isinstance(my_df, pd.DataFrame)
    True

    """
    # regions = [x for x in es.results['tags']['region']
    #            if re.match(r"DE[0-9][0-9]", x)]

    if bus_substring is None:
        bus_substring = 'bus_electricity_all'

    buses = set([x[0] for x in es.results['Main'].keys()
                 if str(bus_substring) in str(x[0].label)])

    data = None
    for bus in sorted(buses):
        data = reshape_bus_view(es, bus, data)

    return data


def get_nominal_values(es, cat='bus', tag='electricity', subtag=None):
    """
    Get a DataFrame with all nodes and the nominal value of their Flows.

    Parameters
    ----------
    es : solph.EnergySystem
        An EnergySystem with results.
    cat : str or None
    tag : str or None
    subtag : str or None

    Returns
    -------
    pd. DataFrame

    Examples
    --------
    >>> fn1, fn2 = get_file_name_doctests()
    >>> my_es = load_es(fn1)
    >>> my_df = get_nominal_values(my_es)
    >>> isinstance(my_df, pd.DataFrame)
    True
    """
    de_results = es.results['Param']

    regions = [x[0].label.region for x in es.results['Param'].keys()
               if ('shortage' in x[0].label.cat) &
               ('electricity' in x[0].label.tag)]

    midx = pd.MultiIndex(levels=[[], [], [], []], labels=[[], [], [], []])
    dt = pd.DataFrame(index=midx, columns=['nominal_value'])
    for region in sorted(set(regions)):
        node = get_nodes_by_label(es, (cat, tag, subtag, region))
        in_c = [x for x in de_results.keys() if x[1] == node]
        out_c = [x for x in de_results.keys()
                 if x[0] == node and x[1] is not None]
        for k in in_c:
            # print(repr(k.label))
            # idx = region, 'in', k[0].replace('_{0}'.format(region), '')
            dt.loc[k[0].label] = de_results[k]['scalars'].get('nominal_value')

        for k in out_c:
            dt.loc[k[1].label] = de_results[k]['scalars'].get('nominal_value')

    return dt


def get_nodes_by_label(es, label_args):
    """
    Get a node by specifying the label. If the label contains a None attribute
    the argument is skipped. If more than one node is found a list is
    returned otherwise the single node is returned.

    Parameters
    ----------
    es : solph.EnergySystem
        An EnergySystem with results.
    label_args : tuple
        A list of label arguments. Use None as a wildcard.
        The position of the argument is considered.

    Returns
    -------
    solph.node or list

    Examples
    --------
    >>> fn1, fn2 = get_file_name_doctests()
    >>> my_es = load_es(fn1)
    >>> my_bus = get_nodes_by_label(my_es, ('bus', 'electricity', None, None))
    >>> len(my_bus)
    21
    >>> my_bus = get_nodes_by_label(
    ...     my_es, ('bus', 'electricity', None, 'DE21'))
    >>> type(my_bus)
    <class 'oemof.solph.network.Bus'>

    """
    label = Label(*label_args)
    res = es.results['Main']
    for n in range(len(label_args)):
        if label[n] is not None:
            res = {k: v for k, v in res.items() if k[0].label[n] == label[n]}

    nodes = []
    for r in res:
        nodes.append(r[0])

    nodes = list(set(nodes))

    if len(nodes) == 1:
        nodes = nodes[0]

    return nodes


def check_excess_shortage(es):
    """Check if shortage or excess is used in the given EnergySystem."""

    result = es.results['Main']
    flows = [x for x in result.keys() if x[1] is not None]
    ex_nodes = [x for x in flows if (x[1] is not None) &
                ('excess' in x[1].label)]
    sh_nodes = [x for x in flows if 'shortage' in x[0].label]
    ex = 0
    sh = 0
    for node in ex_nodes:
        f = outputlib.views.node(result, node[1])
        s = int(round(f['sequences'].sum()))
        if s > 0:
            print(node[1], ':', s)
            ex += 1

    for node in sh_nodes:
        f = outputlib.views.node(result, node[0])
        s = int(round(f['sequences'].sum()))
        if s > 0:
            print(node[0], ':', s)
            sh += 1
    if sh == 0:
        print("No shortage usage found.")
    if ex == 0:
        print("No excess usage found.")


def find_input_flow(out_flow, nodes):
    return [x for x in list(nodes.keys()) if x[1] == out_flow[0][0]]


def ee_analyser(es, ee_type):
    """Get aggregated time series of one feed-in source type.

    Parameters
    ----------
    es : solph.EnergySystem
        An EnergySystem with results.
    ee_type : str
        An ee type such as wind or solar.

    Returns
    -------
    pd.Series

    Examples
    --------
    >>> fn1, fn2 = get_file_name_doctests()
    >>> s = ee_analyser(load_es(fn1), 'solar')
    >>> isinstance(s, pd.Series)
    True
    """
    results = es.results
    analysis = analyzer.Analysis(
        results['Main'], results['Param'],
        iterator=analyzer.FlowNodeIterator)
    ee = analyzer.FlowFilterSubstring(ee_type, position=0)
    analysis.add_analyzer(ee)
    analysis.analyze()

    df = pd.concat(ee.result, axis=1)
    df.columns = df.columns.droplevel(-1)
    return df.sum(axis=1)


def emissions(es):
    """Get emissions of all commodity sources."""
    r = es.results['Main']
    p = es.results['Param']

    emission_df = pd.DataFrame()

    for i in r.keys():
        if (i[0].label.cat == 'source') & (i[0].label.tag == 'commodity'):
            emission_df.loc[i[0].label.subtag, 'specific_emission'] = (
                p[i]['scalars']['emission'])
            emission_df.loc[i[0].label.subtag, 'summed_flow'] = (
                r[i]['sequences']['flow'].sum())

    emission_df['total_emission'] = (emission_df['specific_emission'] *
                                     emission_df['summed_flow'])

    emission_df.sort_index(inplace=True)

    return emission_df


def fullloadhours(es, grouplevel=None, dropnan=False):
    """
    Calculate the full load hours of all nodes.

    The last column of the index indicates the method how the nominal_value
    was collected:

    nvo : nominal_value found in output flow
    nvi : nominal_value found in input flow
    max : not nominal_value found the maximum of the flow was used

    Parameters
    ----------
    es : solph.EnergySystem
        An EnergySystem with results.
    grouplevel : list
        sdaf
    dropnan : bool
        If True all nodes with NaN values for full load hours will be dropped.

    Returns
    -------
    pd.DataFrame

    Examples
    --------
    >>> fn1, fn2 = get_file_name_doctests()
    >>> es = load_es(fn1)
    >>> df1 = fullloadhours(es, grouplevel = [0, 1, 2])
    >>> df_sub1 = df1.loc['trsf', 'pp', 'lignite']
    >>> df2 = fullloadhours(es)
    >>> df_sub2 = df2.loc['trsf', 'pp', 'lignite', 'DE04']

    """
    if grouplevel is None:
        grouplevel = [0, 1, 2, 3, 4]

    r = es.results['Main']
    p = es.results['Param']

    idx = pd.MultiIndex(levels=[[], [], [], [], []],
                        labels=[[], [], [], [], []])
    cols = ['nominal_value', 'summed_flow']
    sort_results = pd.DataFrame(index=idx, columns=cols)
    logging.info('Start')
    for i in r.keys():
        if isinstance(i[1], solph.Transformer):
            out_node = [o for o in i[1].outputs][0]
            cf_name = 'conversion_factors_' + str(out_node.label)
            try:
                nom_value = (
                    p[(i[1], out_node)]['scalars']['nominal_value'] /
                    p[(i[1], None)]['scalars'][cf_name])
                label = tuple(i[1].label) + ('nvo', )
            except KeyError:
                try:
                    nom_value = p[i]['scalars']['nominal_value']
                    label = tuple(i[1].label) + ('nvi', )
                except KeyError:
                    nom_value = r[i]['sequences']['flow'].max()
                    label = tuple(i[1].label) + ('max', )

            summed_flow = r[i]['sequences']['flow'].sum()

        elif isinstance(i[0], solph.Source):
            try:
                nom_value = p[i]['scalars']['nominal_value']
                label = tuple(i[0].label) + ('nvo', )
            except KeyError:
                nom_value = r[i]['sequences']['flow'].max()
                label = tuple(i[0].label) + ('max', )

            summed_flow = r[i]['sequences']['flow'].sum()

        else:
            label = None
            nom_value = None
            summed_flow = None

        if nom_value is not None:
            sort_results.loc[label, 'nominal_value'] = nom_value
            if not sort_results.index.is_lexsorted():
                sort_results.sort_index(inplace=True)
            sort_results.loc[label, 'summed_flow'] = summed_flow

    logging.info('End')
    new = sort_results.groupby(level=grouplevel).sum()
    new['flh'] = new['summed_flow'] / new['nominal_value']

    if dropnan is True:
        new = new[new.flh.notnull()]
    return new


def get_electricity_duals(es):
    """Get the dual variables of all electricity buses as DataFrame"""
    e_buses = get_nodes_by_label(es, ('bus', 'electricity', None, None))
    df = pd.DataFrame()
    for bus in sorted(e_buses):
        region = bus.label.region
        df[region] = es.results['Main'][bus, None]['sequences']['duals']
    return df


def write_graph(es, fn, remove=None):
    """
    Write a graph to a given file. Add a list of substrings to remove nodes.
    """
    if remove is None:
        remove = ['commodity']
    graph.create_nx_graph(es, filename=fn, remove_nodes_with_substrings=remove)


def create_label_overview(es):
    """
    Creates a DataFrame with all existing label values in a MultiIndex.
    Just print the examples below to learn how to get subsets. You can also
    write an overview to an csv oder xlsx file using 'to_csv/to_excel'.

    Examples
    --------
    >>> fn1, fn2 = get_file_name_doctests()
    >>> fulldf = create_label_overview(load_es(fn1))
    >>> subdf = fulldf.swaplevel(0, 3).sort_index().loc['DE01']
    >>> isinstance(subdf, pd.DataFrame)
    True
    >>> subdf = fulldf.loc['bus', 'heat']
    >>> isinstance(subdf, pd.DataFrame)
    True
    """
    idx = pd.MultiIndex(levels=[[], [], [], []],
                        labels=[[], [], [], []])
    cols = ['solph_class']
    label_overview = pd.DataFrame(index=idx, columns=cols)
    for node in es.nodes:
        solph_class = str(type(node)).split('.')[-1][:-2]
        label_overview.loc[node.label, 'solph_class'] = solph_class
        label_overview.sort_index(inplace=True)
    return label_overview


def load_es(fn=None):
    """
    Load EnergySystem with the given filename (full path). If no file name
    is given a GUI window is popping up.
    """
    if fn is None:
        fn = gui.select_filename(work_dir=cfg.get('paths', 'scenario'),
                                 title='Select results file',
                                 extension='esys')

    sc = Scenario()
    logging.debug("Restoring file from {0}".format(fn))
    file_datetime = datetime.fromtimestamp(os.path.getmtime(fn)).strftime(
        '%d. %B %Y - %H:%M:%S')
    logging.info("Restored results created on: {0}".format(file_datetime))
    sc.restore_es(fn)
    return sc.es


def load_my_es(*args, var=None, fn=None, scpath=None):
    """

    Parameters
    ----------
    args : args
        Parts of the scenario path.
    var : str (optional)
        Variant of the scenario.
    fn : str (optional)
        Filename of EnergySystem (with full path)
    scpath : str (optional)
        Path of the scenarios.

    Returns
    -------
    solph.EnergySystem

    Examples
    --------
    >>> fn1, fn2 = get_file_name_doctests()
    >>> es1 = load_my_es('deflex', '2014', var='de21')
    >>> es2 = load_es(fn1)
    >>> l1 = list(es1.results['Main'].keys())[0][0].label
    >>> l2 = list(es2.results['Main'].keys())[0][0].label
    >>> l1 == l2
    True
    """
    if cfg.has_option('results', 'dir'):
        results_dir = cfg.get('results', 'dir')
    else:
        results_dir = 'results'

    if scpath is None:
        path = os.path.join(cfg.get('paths', 'scenario'), *args, results_dir)
    else:
        path = os.path.join(scpath, *args, results_dir)

    if var is None:
        var = []
    else:
        var = [var]

    if fn is None:
        name = '_'.join(list(args) + var)
        fn = os.path.join(path, name + '.esys')
    else:
        name = fn.split(os.sep)[-1].split('.')[0]

    es = load_es(fn)
    es.name = name
    es.var = var[0]
    return es


def fetch_cost_emission(es, with_chp=True):
    """
    Fetch the costs and emissions per electricity unit for all power plants
    and combined heat and power plants if with chp is True

    Returns
    -------
    pd.DataFrame
    """
    idx = pd.MultiIndex(levels=[[], [], []], labels=[[], [], []])
    parameter = pd.DataFrame(index=idx)
    p = es.results['Param']
    flows = [x for x in p if x[1] is not None]
    cs = [x for x in flows if (x[0].label.tag == 'commodity') and
          (x[0].label.cat == 'source')]

    # Loop over commodity sources
    for k in cs:
        fuel = k[0].label.subtag
        emission = p[k]['scalars'].emission
        var_costs = p[k]['scalars'].variable_costs

        # All power plants with the commodity source (cs)
        pps = [x[1] for x in flows if x[0] == k[1] and x[1].label.tag == 'pp']
        for pp in pps:
            region = pp.label.region
            key = 'conversion_factors_bus_electricity_all_{0}'.format(region)
            cf = p[pp, None]['scalars'][key]
            region = pp.label.region
            parameter.loc[(fuel, region, 'pp'), 'emission'] = emission / cf
            parameter.loc[(fuel, region, 'pp'), 'var_costs'] = var_costs / cf

        # All chp plants with the commodity source (cs)
        if with_chp is True:
            chps = [
                x[1] for x in flows if
                x[0] == k[1] and x[1].label.tag == 'chp']
            hps = [x[1] for x in flows if
                   x[0] == k[1] and x[1].label.tag == 'hp']
        else:
            chps = []
            hps = []

        for chp in chps:
            region = chp.label.region
            eta = {}
            hp = [x for x in hps if x.label.region == region]
            if len(hp) == 1:
                key = 'conversion_factors_bus_heat_district_{0}'.format(region)
                eta['heat_hp'] = p[hp[0], None]['scalars'][key]
                for o in chp.outputs:
                    key = 'conversion_factors_{0}'.format(o)
                    eta_key = o.label.tag
                    eta_val = p[chp, None]['scalars'][key]
                    eta[eta_key] = eta_val
                alternative_resource_usage = (
                        eta['heat'] / (eta['electricity'] * eta['heat_hp']))
                chp_resource_usage = 1 / eta['electricity']

                cf = 1 / (chp_resource_usage - alternative_resource_usage)
                parameter.loc[
                    (fuel, region, 'chp'), 'emission'] = emission / cf
                parameter.loc[
                    (fuel, region, 'chp'), 'var_costs'] = var_costs / cf

                # eta['heat_ref'] = 0.9
                # eta['elec_ref'] = 0.55
                #
                # pee = (1 / (eta['heat'] / eta['heat_ref']
                #             + eta['electricity'] / eta['elec_ref'])) *\
                #       (eta['electricity'] / eta['elec_ref'])
                # parameter.loc[
                #     (fuel, region, 'chp_fin'), 'emission'] = emission / pee
                # parameter.loc[
                #     (fuel, region, 'chp_fin'), 'var_costs'] = var_costs / pee
            elif len(hp) > 1:
                print('error')
            else:
                print('Missing hp: {0}'.format(str(chp)))
                parameter.loc[
                    (fuel, region, 'chp'), 'emission'] = float('nan')
                parameter.loc[
                    (fuel, region, 'chp'), 'var_costs'] = 0
    return parameter


def get_storage_efficiencies(es):
    """Get the overall efficiency for all storages.

    Returns
    -------
    pd.DataFrame
    """
    p = es.results['Param']
    storages = [x for x in p if x[0].label.cat == 'storage' and x[1] is None]
    storages_eff = pd.Series()
    for s in storages:
        sp = p[s]['scalars']
        cf_in = sp.inflow_conversion_factor
        cf_out = sp.outflow_conversion_factor
        storages_eff[s[0]] = cf_in * cf_out
    return storages_eff


def fetch_cost_emission_with_storages(es, with_chp=True):
    """
    Fetch the costs and emissions per electricity unit for all power plants
    and combined heat and power plants if with chp is True.

    Additionally all emissions and cost will be divided by the efficiency of
    all storage. The result is a Multiindex DataFrame with the name of the
    storage in the first level and 'emission' or 'cost' in the second level.
    For the emissions and cost without a storage the keyword 'no_storage is
    used.

    Returns
    -------
    pd.DataFrame
    """
    parameter = fetch_cost_emission(es, with_chp=with_chp)
    storage_efficiencies = get_storage_efficiencies(es)
    idx = pd.MultiIndex(levels=[[], []], labels=[[], []])
    parameter_w_storage = pd.DataFrame(index=parameter.index, columns=idx)
    for si, sv in storage_efficiencies.iteritems():
        for pi, pv in parameter.iterrows():
            parameter_w_storage.loc[
                pi, (str(si), 'var_costs')] = pv.var_costs / sv
            parameter_w_storage.loc[
                pi, (str(si), 'emission')] = pv.emission / sv
            parameter_w_storage.loc[pi, ('multip' + str(si), 'var_costs')] = (
                    pv.var_costs * sv)
            parameter_w_storage.loc[pi, ('multip' + str(si), 'emission')] = (
                    pv.emission * sv)
    for pi, pv in parameter.iterrows():
        ns = 'no_storage'
        parameter_w_storage.loc[pi, (ns, 'var_costs')] = pv.var_costs
        parameter_w_storage.loc[pi, (ns, 'emission')] = pv.emission
    return parameter_w_storage


def get_test_es():
    fn1, fn2 = get_file_name_doctests()
    return load_es(fn1)


if __name__ == "__main__":
    logger.define_logging()
