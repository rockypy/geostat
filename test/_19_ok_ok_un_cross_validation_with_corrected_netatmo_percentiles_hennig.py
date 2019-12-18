# -*- coding: utf-8 -*-
"""
Created on 01.12.2019

@author: Abbas EL Hachem

Goal: Quantile Kriging
"""
import os
os.environ[str('MKL_NUM_THREADS')] = str(1)
os.environ[str('NUMEXPR_NUM_THREADS')] = str(1)
os.environ[str('OMP_NUM_THREADS')] = str(1)

import pyximport

pyximport.install()


import timeit
import time

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from scipy import spatial
from scipy.stats import norm
from scipy.stats import rankdata

from pathlib import Path
from spinterps import (OrdinaryKriging,
                       OrdinaryKrigingWithUncertainty)
from spinterps import variograms


VG = variograms.vgs.Variogram

plt.rcParams.update({'font.size': 12})
plt.rcParams.update({'axes.labelsize': 12})


# =============================================================================
#main_dir = Path(r'/home/abbas/Documents/Python/Extremes')
# main_dir = Path(r'/home/IWS/hachem/Extremes')
main_dir = Path(r'X:\hiwi\ElHachem\Prof_Bardossy\Extremes')
os.chdir(main_dir)

path_to_data = main_dir / r'NetAtmo_BW'

path_to_vgs = main_dir / r'kriging_ppt_netatmo'

# COORDINATES
path_to_dwd_coords = (path_to_data /
                      r'station_coordinates_names_hourly_only_in_BW_utm32.csv')

path_to_netatmo_coords = path_to_data / r'netatmo_bw_1hour_coords_utm32.csv'

# path for data filter
in_filter_path = main_dir / r'oridinary_kriging_compare_DWD_Netatmo'

# distance mtx netatmo dwd
distance_matrix_netatmo_dwd_df_file = path_to_data / \
    r'distance_mtx_in_m_NetAtmo_DWD.csv'

# path_to_dwd_stns_comb
path_to_dwd_stns_comb = in_filter_path / r'dwd_combination_to_use.csv'
#==============================================================================
# # NETATMO FIRST FILTER
#==============================================================================

use_dwd_stns_for_kriging = True

qunatile_kriging = True

# run it to filter True
use_netatmo_gd_stns = False  # general filter, Indicator kriging
use_temporal_filter_after_kriging = False  # on day filter

use_first_neghbr_as_gd_stns = False  # False
use_first_and_second_nghbr_as_gd_stns = False  # True

_acc_ = ''

if use_first_neghbr_as_gd_stns:
    _acc_ = '1st'

if use_first_and_second_nghbr_as_gd_stns:
    _acc_ = 'comb'

if use_netatmo_gd_stns:
    path_to_netatmo_gd_stns = (
        main_dir / r'plots_NetAtmo_ppt_DWD_ppt_correlation_' /
        (r'keep_stns_all_neighbor_99_per_60min_s0_%s.csv'
         % _acc_))


#==============================================================================
#
#==============================================================================
resample_frequencies = ['1440min']
# '60min', '180min', '360min', '720min', '1440min'


title_ = r'Qt_ok_ok_un_3_test'


if not use_netatmo_gd_stns:
    title_ = title_ + '_netatmo_no_flt_'

if use_netatmo_gd_stns:
    title_ = title_ + '_first_flt_'

if use_temporal_filter_after_kriging:

    title_ = title_ + '_temp_flt_'

#==============================================================================
#
#==============================================================================


strt_date = '2015-01-01 00:00:00'
end_date = '2019-09-01 00:00:00'

# min_valid_stns = 20

drop_stns = []
mdr = 0.9
perm_r_list_ = [1, 2]
fit_vgs = ['Sph', 'Exp']  # 'Sph',
fil_nug_vg = 'Nug'  # 'Nug'
n_best = 4
ngp = 5

idx_time_fmt = '%Y-%m-%d %H:%M:%S'

radius = 10000
max_dist_neighbrs = 3e4
diff_thr = 0.1

#==============================================================================
# Needed functions
#==============================================================================


def build_edf_fr_vals(ppt_data):
    """ construct empirical distribution function given data values """
    data_sorted = np.sort(ppt_data, axis=0)[::-1]

    x0 = np.round(np.squeeze(data_sorted)[::-1], 2)
    y0 = np.round((np.arange(data_sorted.size) / len(data_sorted)), 5)

    return x0, y0

# =============================================================================


def find_nearest(array, value):
    '''given an array, find in the array 
        the nearest value to a given value'''
    array = np.asarray(array)
    idx = (np.abs(array - value)).argmin()
    return array[idx]

# =============================================================================


def test_if_vg_model_is_suitable(vg_model, df_vgs, event_date):
    '''check if vg model is suitable'''
    if not isinstance(vg_model, str):
        vg_model = df_vgs.loc[event_date, 2]

    if not isinstance(vg_model, str):
        vg_model = ''

    if ('Nug' in vg_model or len(
        vg_model) == 0) and (
        'Exp' not in vg_model and
            'Sph' not in vg_model):
        try:
            for i in range(2, len(df_vgs.loc[event_date, :])):
                vg_model = df_vgs.loc[event_date, i]
                if type(vg_model) == np.float:
                    continue
                if ('Nug' in vg_model
                        or len(vg_model) == 0) and (
                            'Exp' not in vg_model or
                        'Sph' not in vg_model):
                    continue
                else:
                    break

        except Exception as msg:
            print(msg)
            print('Only Nugget variogram for this day')
    return vg_model


#==============================================================================
#
#==============================================================================
# Netatmo Coords
netatmo_in_coords_df = pd.read_csv(path_to_netatmo_coords,
                                   index_col=0,
                                   sep=';',
                                   encoding='utf-8')

# DWD Coords

dwd_in_coords_df = pd.read_csv(path_to_dwd_coords,
                               index_col=0,
                               sep=';',
                               encoding='utf-8')
# added by Abbas, for DWD stations
stndwd_ix = ['0' * (5 - len(str(stn_id))) + str(stn_id)
             if len(str(stn_id)) < 5 else str(stn_id)
             for stn_id in dwd_in_coords_df.index]

dwd_in_coords_df.index = stndwd_ix
dwd_in_coords_df.index = list(map(str, dwd_in_coords_df.index))


# Netatmo first filter
if use_netatmo_gd_stns:
    df_gd_stns = pd.read_csv(path_to_netatmo_gd_stns,
                             index_col=0,
                             sep=';',
                             encoding='utf-8')

#==============================================================================
#
#==============================================================================
# read distance matrix dwd-netamot ppt
in_df_distance_netatmo_dwd = pd.read_csv(
    distance_matrix_netatmo_dwd_df_file, sep=';', index_col=0)

# read df combinations to use
df_dwd_stns_comb = pd.read_csv(
    path_to_dwd_stns_comb, index_col=0,
    sep=',', dtype=str)
#==============================================================================
#
#==============================================================================
for temp_agg in resample_frequencies:

    # out path directory
    dir_path = title_ + '_' + _acc_ + '_' + temp_agg

    out_plots_path = in_filter_path / dir_path

    if not os.path.exists(out_plots_path):
        os.mkdir(out_plots_path)
    print(out_plots_path)

    # path to data
    #=========================================================================
    out_save_csv = '_%s_ppt_edf_' % temp_agg

    path_to_dwd_edf = (path_to_data /
                       (r'edf_ppt_all_dwd_%s_.csv' % temp_agg))

    path_to_dwd_ppt = (path_to_data /
                       (r'ppt_all_dwd_%s_.csv' % temp_agg))

    path_to_dwd_edf_old = (path_to_data /
                           (r'edf_ppt_all_dwd_old_%s_.csv' % temp_agg))

    path_to_dwd_ppt_old = (path_to_data /
                           (r'ppt_all_dwd_old_%s_.csv' % temp_agg))

    path_to_netatmo_edf = (path_to_data /
                           (r'edf_ppt_all_netatmo_%s_.csv' % temp_agg))

    path_to_netatmo_ppt = (path_to_data /
                           (r'ppt_all_netatmo_%s_.csv' % temp_agg))
    path_to_dwd_vgs = path_to_vgs / \
        (r'vg_strs_dwd_%s_maximum_100_event.csv' % temp_agg)
    path_to_dwd_vgs_transf = path_to_vgs / \
        (r'dwd_edf_transf_vg_%s.csv' % temp_agg)
    path_dwd_extremes_df = path_to_data / \
        (r'dwd_%s_maximum_100_event.csv' % temp_agg)

    # Files to use
    #==========================================================================

    netatmo_data_to_use = path_to_netatmo_edf
    dwd_data_to_use = path_to_dwd_edf

    print(title_)
    # DWD DATA
    #=========================================================================
    dwd_in_vals_df = pd.read_csv(
        path_to_dwd_edf, sep=';', index_col=0, encoding='utf-8')

    dwd_in_vals_df.index = pd.to_datetime(
        dwd_in_vals_df.index, format='%Y-%m-%d')

    dwd_in_vals_df = dwd_in_vals_df.loc[strt_date:end_date, :]
    dwd_in_vals_df.dropna(how='all', axis=0, inplace=True)

    # DWD ppt
    dwd_in_ppt_vals_df = pd.read_csv(
        path_to_dwd_ppt, sep=';', index_col=0, encoding='utf-8')

    dwd_in_ppt_vals_df.index = pd.to_datetime(
        dwd_in_ppt_vals_df.index, format='%Y-%m-%d')

    dwd_in_ppt_vals_df = dwd_in_ppt_vals_df.loc[strt_date:end_date, :]
    dwd_in_ppt_vals_df.dropna(how='all', axis=0, inplace=True)

    # DWD old edf

    dwd_in_vals_edf_old = pd.read_csv(
        path_to_dwd_edf_old, sep=';', index_col=0, encoding='utf-8')

    dwd_in_vals_edf_old.index = pd.to_datetime(
        dwd_in_vals_edf_old.index, format='%Y-%m-%d')

    dwd_in_vals_edf_old.dropna(how='all', axis=0, inplace=True)
    # dwd ppt old
    dwd_in_ppt_vals_df_old = pd.read_csv(
        path_to_dwd_ppt_old, sep=';', index_col=0, encoding='utf-8')

    dwd_in_ppt_vals_df_old.index = pd.to_datetime(
        dwd_in_ppt_vals_df_old.index, format='%Y-%m-%d')

    # NETAMO DATA
    #=========================================================================
    netatmo_in_vals_df = pd.read_csv(
        path_to_netatmo_edf, sep=';',
        index_col=0,
        encoding='utf-8', engine='c')

    netatmo_in_vals_df.index = pd.to_datetime(
        netatmo_in_vals_df.index, format='%Y-%m-%d')

    netatmo_in_vals_df = netatmo_in_vals_df.loc[strt_date:end_date, :]
    netatmo_in_vals_df.dropna(how='all', axis=0, inplace=True)

    # ppt data
    netatmo_in_ppt_vals_df = pd.read_csv(
        path_to_netatmo_ppt, sep=';',
        index_col=0,
        encoding='utf-8', engine='c')

    netatmo_in_ppt_vals_df.index = pd.to_datetime(
        netatmo_in_ppt_vals_df.index, format='%Y-%m-%d')

    netatmo_in_ppt_vals_df = netatmo_in_ppt_vals_df.loc[strt_date:end_date, :]
    netatmo_in_ppt_vals_df.dropna(how='all', axis=0, inplace=True)

    # apply first filter
    if use_netatmo_gd_stns:
        print('\n**using Netatmo gd stns**')
        good_netatmo_stns = df_gd_stns.loc[:, 'Stations'].values.ravel()
        cmn_gd_stns = netatmo_in_vals_df.columns.intersection(
            good_netatmo_stns)
        netatmo_in_vals_df = netatmo_in_vals_df.loc[:, cmn_gd_stns]

    cmn_stns = netatmo_in_vals_df.columns.intersection(
        netatmo_in_coords_df.index)

    netatmo_in_coords_df = netatmo_in_coords_df.loc[
        netatmo_in_coords_df.index.intersection(cmn_stns), :]
    netatmo_in_vals_df = netatmo_in_vals_df.loc[
        :, netatmo_in_vals_df.columns.intersection(cmn_stns)]
    netatmo_in_ppt_vals_df = netatmo_in_ppt_vals_df.loc[:, cmn_stns]

    # DWD Extremes
    #=========================================================================
    dwd_in_extremes_df = pd.read_csv(path_dwd_extremes_df,
                                     index_col=0,
                                     sep=';',
                                     parse_dates=True,
                                     infer_datetime_format=True,
                                     encoding='utf-8',
                                     header=None)

    df_vgs_extremes = pd.read_csv(path_to_dwd_vgs,
                                  index_col=0,
                                  sep=';',
                                  parse_dates=True,
                                  infer_datetime_format=True,
                                  encoding='utf-8',
                                  skiprows=[0],
                                  header=None).dropna(how='all')

    # DWD tranformed data VG
    #==========================================================================

    df_vgs_transf = pd.read_csv(path_to_dwd_vgs_transf,
                                index_col=0,
                                sep=';',
                                parse_dates=True,
                                infer_datetime_format=True,
                                encoding='utf-8',
                                skiprows=[0],
                                header=None).dropna(how='all')

    dwd_in_extremes_df = dwd_in_extremes_df.loc[
        dwd_in_extremes_df.index.intersection(
            netatmo_in_vals_df.index).intersection(
                df_vgs_extremes.index).intersection(
                df_vgs_transf.index), :]

    cmn_netatmo_stns = in_df_distance_netatmo_dwd.index.intersection(
        netatmo_in_vals_df.columns)
    in_df_distance_netatmo_dwd = in_df_distance_netatmo_dwd.loc[
        cmn_netatmo_stns, :]

    #==============================================================
    # # DWD qunatiles for every event, fit a variogram
    #==============================================================
#     df_vgs_extremes_norm = pd.DataFrame(index=dwd_in_extremes_df.index)
#
#     for event_date in dwd_in_extremes_df.index:
#         #                 if event_date == '2016-08-18 20:00:00':
#         #                     print(event_date)
#         #                     raise Exception
#         _stn_id_event_ = str(dwd_in_extremes_df.loc[event_date, 2])
#         if len(_stn_id_event_) < 5:
#             _stn_id_event_ = (5 - len(_stn_id_event_)) * \
#                 '0' + _stn_id_event_
#
#         _ppt_event_ = dwd_in_extremes_df.loc[event_date, 1]
#         _edf_event_ = dwd_in_vals_df.loc[event_date, _stn_id_event_]
#         print('**Calculating for Date ',
#               event_date, '\n Rainfall: ',  _ppt_event_,
#               'Quantile: ', _edf_event_, ' **\n')
#         edf_dwd_vals = []
#         dwd_xcoords = []
#         dwd_ycoords = []
#         dwd_stn_ids = []
#         for stn_id in all_dwd_stns:
#             #print('station is', stn_id)
#
#             edf_stn_vals = dwd_in_vals_df.loc[
#                 event_date, stn_id]
#
#             if edf_stn_vals > 0:
#                 edf_dwd_vals.append(np.round(edf_stn_vals, 4))
#                 dwd_xcoords.append(dwd_in_coords_df.loc[stn_id, 'X'])
#                 dwd_ycoords.append(dwd_in_coords_df.loc[stn_id, 'Y'])
#                 dwd_stn_ids.append(stn_id)
#
#         dwd_xcoords = np.array(dwd_xcoords)
#         dwd_ycoords = np.array(dwd_ycoords)
#         edf_dwd_vals = np.array(edf_dwd_vals)
#
#         std_norm_edf_dwd_vals = norm.ppf(
#             rankdata(edf_dwd_vals) / (
#                 len(edf_dwd_vals) + 1))
# #         # fit a beta distribution to quantiles
# #         alpha1, beta1, xx, yy = beta.fit(edf_dwd_vals)  # , floc=0, fscale=1)
# #         # find for every Pi the Beta_Cdf(a, b, Pi)
# #         beta_edf_dwd_vals = beta.cdf(edf_dwd_vals, a=alpha1, b=beta1, loc=xx,
# #                                      scale=yy)
# #         # transform to normal using the inv standard normal
# #         std_norm_edf_dwd_vals = norm.ppf(beta_edf_dwd_vals)
#         # fit variogram
#         print('*Done getting data* \n *Fitting variogram*\n')
#         try:
#
#             vg_dwd = VG(
#                 x=dwd_xcoords,
#                 y=dwd_ycoords,
#                 z=std_norm_edf_dwd_vals,
#                 mdr=mdr,
#                 nk=5,
#                 typ='cnst',
#                 perm_r_list=perm_r_list_,
#                 fil_nug_vg=fil_nug_vg,
#                 ld=None,
#                 uh=None,
#                 h_itrs=100,
#                 opt_meth='L-BFGS-B',
#                 opt_iters=1000,
#                 fit_vgs=fit_vgs,
#                 n_best=n_best,
#                 evg_name='robust',
#                 use_wts=False,
#                 ngp=ngp,
#                 fit_thresh=0.01)
#
#             vg_dwd.fit()
#
#             fit_vg_list = vg_dwd.vg_str_list
#
#         except Exception as msg:
#             print(msg)
#             fit_vg_list = ['']
#             # continue
#
#         vgs_model_dwd = fit_vg_list[0]
#         if len(vgs_model_dwd) > 0:
#             df_vgs_extremes_norm.loc[event_date, 1] = vgs_model_dwd
#         else:
#             df_vgs_extremes_norm.loc[event_date, 1] = np.nan
#     df_vgs_extremes_norm.dropna(how='all', inplace=True)
#     df_vgs_extremes_norm.to_csv((path_to_vgs /
#                                  ('dwd_edf_transf_vg_%s.csv' % temp_agg)),
#                                 sep=';')

    #==========================================================================
    # CREATE DFS HOLD RESULT KRIGING PER NETATMO STATION
    #==========================================================================

    for idx_lst_comb in df_dwd_stns_comb.index:

        stn_comb = [stn.replace("'", "")
                    for stn in df_dwd_stns_comb.iloc[
                        idx_lst_comb, :].dropna().values]
        # create DFs for saving results
        df_interpolated_dwd_netatmos_comb = pd.DataFrame(
            index=dwd_in_extremes_df.index,
            columns=[stn_comb])

        df_interpolated_dwd_netatmos_comb_un = pd.DataFrame(
            index=dwd_in_extremes_df.index,
            columns=[stn_comb])

        df_interpolated_dwd_only = pd.DataFrame(
            index=dwd_in_extremes_df.index,
            columns=[stn_comb])

        df_interpolated_netatmo_only = pd.DataFrame(
            index=dwd_in_extremes_df.index,
            columns=[stn_comb])

        df_interpolated_netatmo_only_un = pd.DataFrame(
            index=dwd_in_extremes_df.index,
            columns=[stn_comb])

        #======================================================================
        # START KRIGING EVENTS
        #======================================================================
        for event_date in dwd_in_extremes_df.index[170:]:

            _stn_id_event_ = str(int(dwd_in_extremes_df.loc[event_date, 2]))
            if len(_stn_id_event_) < 5:
                _stn_id_event_ = (5 - len(_stn_id_event_)) * \
                    '0' + _stn_id_event_

            _ppt_event_ = dwd_in_extremes_df.loc[event_date, 1]
            _edf_event_ = dwd_in_vals_df.loc[event_date, _stn_id_event_]

            for i, stn_dwd_id in enumerate(stn_comb):

                x_dwd_interpolate = np.array(
                    [dwd_in_coords_df.loc[stn_dwd_id, 'X']])
                y_dwd_interpolate = np.array(
                    [dwd_in_coords_df.loc[stn_dwd_id, 'Y']])

                # dwd ppt data for cdf
                ppt_stn_dwd = dwd_in_ppt_vals_df.loc[
                    :, stn_dwd_id].dropna(how='all').values

                if ppt_stn_dwd.size > 10:

                    _ppt_event_stn = dwd_in_ppt_vals_df.loc[
                        event_date, stn_dwd_id]
                    _edf_event_stn = dwd_in_vals_df.loc[
                        event_date, stn_dwd_id]

                    print('\n** Obersved Rainfall at DWD Stn: ',
                          _ppt_event_stn)
                    print('\n** Obersved Quantile at DWD Stn: ',
                          _edf_event_stn)

                    # build edf
                    try:
                        xppt, yppt = build_edf_fr_vals(ppt_stn_dwd)
                    except Exception as msg:
                        print('Error getting cdf', msg)
                        continue
                    # drop stn from group
                    all_dwd_stns_except_interp_loc = [
                        stn for stn in dwd_in_vals_df.columns
                        if stn not in stn_comb]

                    # get only nearby DWD stations
                    # coords of neighbors
                    neighbors_dwd_coords = np.array(
                        [(x, y) for x, y in zip(
                            dwd_in_coords_df.loc[
                                all_dwd_stns_except_interp_loc,
                                'X'].values.ravel(),
                            dwd_in_coords_df.loc[
                                all_dwd_stns_except_interp_loc,
                                'Y'].values.ravel())])

                    # create a tree from coordinates
                    points_tree_dwd = spatial.cKDTree(
                        neighbors_dwd_coords)

                    # This finds the index of all points within
                    # distance 1 of [1.5,2.5].
                    idxs_neighbours = points_tree_dwd.query_ball_point(
                        np.column_stack(
                            [x_dwd_interpolate, y_dwd_interpolate]),
                        max_dist_neighbrs)

                    # keep only dwd neighbors
                    dwd_neighbrs = [all_dwd_stns_except_interp_loc[i]
                                    for i in idxs_neighbours[0]]

                    # find distance to all dwd stations, sort them, select
                    # minimum
                    distances_dwd_to_stns = in_df_distance_netatmo_dwd.loc[
                        :, stn_dwd_id]

                    sorted_distances_ppt_dwd = distances_dwd_to_stns.sort_values(
                        ascending=True)

                    # select only neyrby netatmo stations below 30km
                    sorted_distances_ppt_dwd = sorted_distances_ppt_dwd[
                        sorted_distances_ppt_dwd.values <= max_dist_neighbrs]

                    #==========================================================
                    # # DWD qunatiles
                    #==========================================================
                    edf_dwd_vals = []
                    dwd_xcoords = []
                    dwd_ycoords = []
                    dwd_stn_ids = []

                    for stn_id in dwd_neighbrs:
                        #print('station is', stn_id)

                        edf_stn_vals = dwd_in_vals_df.loc[
                            event_date, stn_id]

                        if edf_stn_vals > 0:
                            edf_dwd_vals.append(np.round(edf_stn_vals, 10))
                            dwd_xcoords.append(
                                dwd_in_coords_df.loc[stn_id, 'X'])
                            dwd_ycoords.append(
                                dwd_in_coords_df.loc[stn_id, 'Y'])
                            dwd_stn_ids.append(stn_id)
                    # coords and data of DWD stns
                    dwd_xcoords = np.array(dwd_xcoords)
                    dwd_ycoords = np.array(dwd_ycoords)
                    edf_dwd_vals = np.array(edf_dwd_vals)

                    # get vg model for this day
                    vgs_model_dwd = df_vgs_extremes.loc[event_date, 1]

                    # test if vg model is acceptable
                    vgs_model_dwd = test_if_vg_model_is_suitable(
                        vgs_model_dwd, df_vgs_extremes, event_date)

                    if ('Nug' in vgs_model_dwd
                            or len(vgs_model_dwd) > 0) and (
                            'Exp' in vgs_model_dwd or
                            'Sph' in vgs_model_dwd):

                        # Netatmo data and coords
                        netatmo_df = netatmo_in_vals_df.loc[
                            event_date,
                            sorted_distances_ppt_dwd.index].dropna(
                            how='all')

                        if netatmo_df.size > 0:
                            print('-->Correcting Netatmo Quantiles<--')
                            # =================================================
                            # # CORRECT NETATMO QUANTILES
                            # =================================================

                            edf_netatmo_vals = []
                            netatmo_xcoords = []
                            netatmo_ycoords = []
                            netatmo_stn_ids = []

                            for i, netatmo_stn_id in enumerate(netatmo_df.index):

                                netatmo_edf_event_ = netatmo_in_vals_df.loc[
                                    event_date, netatmo_stn_id]
                                if netatmo_edf_event_ >= 0.7:
                                    # print('Correcting Netatmo station',
                                    # netatmo_stn_id)
                                    try:

                                        #======================================
                                        # # Correct Netatmo Quantiles
                                        #======================================

                                        x_netatmo_interpolate = np.array(
                                            [netatmo_in_coords_df.loc[
                                                netatmo_stn_id, 'X']])
                                        y_netatmo_interpolate = np.array(
                                            [netatmo_in_coords_df.loc[
                                                netatmo_stn_id, 'Y']])

                                        netatmo_stn_edf_df = netatmo_in_vals_df.loc[
                                            :, netatmo_stn_id].dropna(
                                                how='all')

                                        netatmo_start_date = netatmo_stn_edf_df.index[0]
                                        netatmo_end_date = netatmo_stn_edf_df.index[-1]

                                        netatmo_ppt_event_ = netatmo_in_ppt_vals_df.loc[
                                            event_date,
                                            netatmo_stn_id]

                                        # select dwd stations with only same period as
                                        # netatmo stn
                                        ppt_dwd_stn_vals = dwd_in_ppt_vals_df.loc[
                                            netatmo_start_date:netatmo_end_date,
                                            :].dropna(how='all')

                                        dwd_xcoords_new = []
                                        dwd_ycoords_new = []
                                        ppt_vals_dwd_new_for_obsv_ppt = []
                                        # get dwd quantiles for netatmo val
                                        for dwd_stn_id_new in ppt_dwd_stn_vals.columns:

                                            ppt_vals_stn_new = ppt_dwd_stn_vals.loc[
                                                :, dwd_stn_id_new].dropna()

                                            if ppt_vals_stn_new.size > 10:

                                                try:
                                                    ppt_stn_new, edf_stn_new = build_edf_fr_vals(
                                                        ppt_vals_stn_new)
                                                except Exception as msg:
                                                    print(msg)
                                                    continue

                                                if netatmo_edf_event_ == 1:
                                                    # correct edf event, 1 is due to
                                                    # rounding error
                                                    ppt_ix_edf = find_nearest(
                                                        ppt_stn_new,
                                                        _ppt_event_)
                                                    netatmo_edf_event_ = edf_stn_new[
                                                        np.where(
                                                            ppt_stn_new == ppt_ix_edf)][0]

                                                # get nearest percentile in dwd
                                                nearst_edf_new = find_nearest(
                                                    edf_stn_new,
                                                    netatmo_edf_event_)

                                                ppt_idx = np.where(
                                                    edf_stn_new == nearst_edf_new)

                                                try:
                                                    if ppt_idx[0].size > 1:
                                                        ppt_for_edf = np.mean(
                                                            ppt_stn_new[ppt_idx])
                                                    else:
                                                        ppt_for_edf = ppt_stn_new[
                                                            ppt_idx]
                                                except Exception as msg:
                                                    print(msg)

                                                try:
                                                    if ppt_for_edf >= 0:
                                                        ppt_vals_dwd_new_for_obsv_ppt.append(
                                                            ppt_for_edf)
                                                        stn_xcoords_new = dwd_in_coords_df.loc[
                                                            dwd_stn_id_new, 'X']
                                                        stn_ycoords_new = dwd_in_coords_df.loc[
                                                            dwd_stn_id_new, 'Y']

                                                        dwd_xcoords_new.append(
                                                            stn_xcoords_new)
                                                        dwd_ycoords_new.append(
                                                            stn_xcoords_new)
                                                except Exception as msg:
                                                    print(
                                                        msg, 'ERROR EDF CORRE')
                                                    continue
                                        # make DWD PPT recent data as array
                                        ppt_vals_dwd_new_for_obsv_ppt = np.array(
                                            ppt_vals_dwd_new_for_obsv_ppt).ravel()
                                        dwd_xcoords_new = np.array(
                                            dwd_xcoords_new)
                                        dwd_ycoords_new = np.array(
                                            dwd_ycoords_new)

                                        # interpolate PPT at Netatmo stn
                                        ordinary_kriging_dwd_netatmo_crt = OrdinaryKriging(
                                            xi=dwd_xcoords_new,
                                            yi=dwd_ycoords_new,
                                            zi=ppt_vals_dwd_new_for_obsv_ppt,
                                            xk=x_netatmo_interpolate,
                                            yk=y_netatmo_interpolate,
                                            model=vgs_model_dwd)

                                        try:
                                            ordinary_kriging_dwd_netatmo_crt.krige()
                                        except Exception as msg:
                                            print('Error while Kriging 1', msg)
                                            continue
                                        # interpolated PPT at Netatmo stn
                                        # using DWD recent
                                        interpolated_netatmo_ppt = ordinary_kriging_dwd_netatmo_crt.zk.copy()

                                        if interpolated_netatmo_ppt >= 0.:

                                            # get for each dwd stn the percentile corresponding
                                            # to interpolated ppt and reinterpolate percentiles
                                            # at Netatmo location

                                            dwd_xcoords_old = []
                                            dwd_ycoords_old = []
                                            edf_vals_dwd_old_for_interp_ppt = []

                                            for dwd_stn_id_old in dwd_in_ppt_vals_df_old.columns:
                                                ppt_vals_stn_old = dwd_in_ppt_vals_df_old.loc[
                                                    :, dwd_stn_id_old].dropna()

                                                ppt_stn_old, edf_stn_old = build_edf_fr_vals(
                                                    ppt_vals_stn_old)
                                                # nearest ppt in DWD stn old
                                                nearst_ppt_old = find_nearest(
                                                    ppt_stn_old,
                                                    interpolated_netatmo_ppt[0])
                                                # corresponding QT
                                                edf_idx = np.where(
                                                    ppt_stn_old == nearst_ppt_old)

                                                try:
                                                    if edf_idx[0].size > 1:
                                                        edf_for_ppt = np.mean(
                                                            edf_stn_old[edf_idx])
                                                    else:
                                                        edf_for_ppt = edf_stn_old[edf_idx]
                                                except Exception as msg:
                                                    print(msg)
                                                    continue
                                                try:
                                                    edf_for_ppt = edf_for_ppt[0]

                                                except Exception as msg:
                                                    edf_for_ppt = edf_for_ppt
                                                    # print('ERROR CDF 1')

                                                if edf_for_ppt >= 0:
                                                    edf_vals_dwd_old_for_interp_ppt.append(
                                                        edf_for_ppt)
                                                    stn_xcoords_old = dwd_in_coords_df.loc[
                                                        dwd_stn_id_old, 'X']
                                                    stn_ycoords_old = dwd_in_coords_df.loc[
                                                        dwd_stn_id_old, 'Y']

                                                    dwd_xcoords_old.append(
                                                        stn_xcoords_old)
                                                    dwd_ycoords_old.append(
                                                        stn_xcoords_old)

                                            # QT data from DWD stns Old
                                            edf_vals_dwd_old_for_interp_ppt = np.array(
                                                edf_vals_dwd_old_for_interp_ppt)
                                            dwd_xcoords_old = np.array(
                                                dwd_xcoords_old)
                                            dwd_ycoords_old = np.array(
                                                dwd_ycoords_old)

                                            # use same VG model
                                            vgs_model_dwd_old = vgs_model_dwd

                                            # Kriging QT at Netatmo
                                            ordinary_kriging_dwd_only_old = OrdinaryKriging(
                                                xi=dwd_xcoords_old,
                                                yi=dwd_ycoords_old,
                                                zi=edf_vals_dwd_old_for_interp_ppt,
                                                xk=x_netatmo_interpolate,
                                                yk=y_netatmo_interpolate,
                                                model=vgs_model_dwd_old)

                                            try:
                                                ordinary_kriging_dwd_only_old.krige()

                                            except Exception as msg:
                                                print(
                                                    'Error while Kriging 2', msg)
                                                continue
                                            # get corrected percentile
                                            interpolated_vals_dwd_old = ordinary_kriging_dwd_only_old.zk.copy()

                                            if interpolated_vals_dwd_old < 0:
                                                interpolated_vals_dwd_old = np.nan

                                        else:
                                            # no gd VG found
                                            interpolated_vals_dwd_old = np.nan

                                        # append to netatmo vals
                                        if interpolated_vals_dwd_old >= 0:
                                            edf_netatmo_vals.append(
                                                np.round(interpolated_vals_dwd_old[0],
                                                         10))
                                            netatmo_xcoords.append(
                                                netatmo_in_coords_df.loc[
                                                    netatmo_stn_id, 'X'])
                                            netatmo_ycoords.append(
                                                netatmo_in_coords_df.loc[
                                                    netatmo_stn_id, 'Y'])
                                            netatmo_stn_ids.append(
                                                netatmo_stn_id)

                                    except KeyError:
                                        continue
                                else:
                                    # no need to correct QT, too small
                                    edf_netatmo_vals.append(
                                        np.round(netatmo_edf_event_, 10))
                                    netatmo_xcoords.append(
                                        netatmo_in_coords_df.loc[netatmo_stn_id, 'X'])
                                    netatmo_ycoords.append(
                                        netatmo_in_coords_df.loc[netatmo_stn_id, 'Y'])
                                    netatmo_stn_ids.append(netatmo_stn_id)

                            netatmo_xcoords = np.array(netatmo_xcoords).ravel()
                            netatmo_ycoords = np.array(netatmo_ycoords).ravel()

                            edf_netatmo_vals = np.array(
                                edf_netatmo_vals).ravel()
                            print('\n<--Done Correcting Netatmo Quantiles-->')

                            if use_temporal_filter_after_kriging:
                                print('\nApplying On Event Filter')
                                # krige Netatmo stations using DWD stns
                                ordinary_kriging_filter_netamto = OrdinaryKriging(
                                    xi=dwd_xcoords,
                                    yi=dwd_ycoords,
                                    zi=edf_dwd_vals,
                                    xk=netatmo_xcoords,
                                    yk=netatmo_ycoords,
                                    model=vgs_model_dwd)

                                try:
                                    ordinary_kriging_filter_netamto.krige()
                                except Exception as msg:
                                    print('Error while Error Kriging 3', msg)
                                    continue

                                # interpolated vals
                                interpolated_vals = ordinary_kriging_filter_netamto.zk

                                # calcualte standard deviation of estimated
                                # values
                                std_est_vals = np.sqrt(
                                    ordinary_kriging_filter_netamto.est_vars)
                                # calculate difference observed and estimated
                                # values
                                diff_obsv_interp = np.abs(
                                    edf_netatmo_vals - interpolated_vals)

                                #==============================================
                                # # use additional temporal filter
                                #==============================================
                                idx_good_stns = np.where(
                                    diff_obsv_interp <= 3 * std_est_vals)
                                idx_bad_stns = np.where(
                                    diff_obsv_interp > 3 * std_est_vals)

                                if (len(idx_bad_stns[0]) or
                                        len(idx_good_stns[0]) > 0):
                                    # ID of gd and bad netatmo stns
                                    try:
                                        ids_netatmo_stns_gd = np.take(
                                            netatmo_df.index,
                                            idx_good_stns).ravel()
                                        ids_netatmo_stns_bad = np.take(
                                            netatmo_df.index,
                                            idx_bad_stns).ravel()

                                    except Exception as msg:
                                        print(msg)

                                try:
                                    # QT values for good netatmo stns
                                    edf_gd_vals_df = netatmo_df.loc[ids_netatmo_stns_gd]
                                except Exception as msg:
                                    print(msg, 'error while second filter')
                                    continue
                                netatmo_dry_gd = edf_gd_vals_df[
                                    edf_gd_vals_df.values < 0.5].dropna()
                                # gd

                                cmn_wet_dry_stns = netatmo_in_coords_df.index.intersection(
                                    netatmo_dry_gd.index)
                                x_coords_gd_netatmo_dry = netatmo_in_coords_df.loc[
                                    cmn_wet_dry_stns, 'X'].values.ravel()
                                y_coords_gd_netatmo_dry = netatmo_in_coords_df.loc[
                                    cmn_wet_dry_stns, 'Y'].values.ravel()

                                netatmo_wet_gd = edf_gd_vals_df[
                                    edf_gd_vals_df.values >= 0.5].dropna(how='all')
                                cmn_wet_gd_stns = netatmo_in_coords_df.index.intersection(
                                    netatmo_wet_gd.index)
                                x_coords_gd_netatmo_wet = netatmo_in_coords_df.loc[
                                    cmn_wet_gd_stns, 'X'].values.ravel()
                                y_coords_gd_netatmo_wet = netatmo_in_coords_df.loc[
                                    cmn_wet_gd_stns, 'Y'].values.ravel()

                                # netatmo bad
                                edf_bad_vals_df = netatmo_df.loc[ids_netatmo_stns_bad]

                                netatmo_dry_bad = edf_bad_vals_df[
                                    edf_bad_vals_df.values < 0.5].dropna()
                                cmn_dry_bad_stns = netatmo_in_coords_df.index.intersection(
                                    netatmo_dry_bad.index)
                                # netatmo bad
                                netatmo_wet_bad = edf_bad_vals_df[
                                    edf_bad_vals_df.values >= 0.5].dropna()
                                cmn_wet_bad_stns = netatmo_in_coords_df.index.intersection(
                                    netatmo_wet_bad.index)
                                # dry bad
                                x_coords_bad_netatmo_dry = netatmo_in_coords_df.loc[
                                    cmn_dry_bad_stns, 'X'].values.ravel()
                                y_coords_bad_netatmo_dry = netatmo_in_coords_df.loc[
                                    cmn_dry_bad_stns, 'Y'].values.ravel()
                                # wet bad
                                x_coords_bad_netatmo_wet = netatmo_in_coords_df.loc[
                                    cmn_wet_bad_stns, 'X'].values.ravel()
                                y_coords_bad_netatmo_wet = netatmo_in_coords_df.loc[
                                    cmn_wet_bad_stns, 'Y'].values.ravel()
                                # find if wet bad is really wet bad
                                # find neighboring netatmo stations wet good

                                # make copy of arrays
                                netatmo_wet_gd_cp = netatmo_wet_gd.copy()
                                x_coords_gd_netatmo_wet_cp = x_coords_gd_netatmo_wet.copy()
                                y_coords_gd_netatmo_wet_cp = y_coords_gd_netatmo_wet.copy()
                                ids_netatmo_stns_gd_cp = ids_netatmo_stns_gd.copy()

                                if netatmo_wet_gd_cp.size > 0:

                                    for stn_, edf_stn, netatmo_x_stn, netatmo_y_stn in zip(
                                        netatmo_wet_bad.index,
                                        netatmo_wet_bad.values,
                                            x_coords_bad_netatmo_wet,
                                            y_coords_bad_netatmo_wet):

                                        # coords of stns self
                                        stn_coords = np.array([(netatmo_x_stn,
                                                                netatmo_y_stn)])

                                        ix_stn = np.where(np.logical_and(
                                            netatmo_xcoords == netatmo_x_stn,
                                            netatmo_ycoords == netatmo_y_stn))

                                        # coords of neighborsä
                                        neighbors_coords = np.array(
                                            [(x, y) for x, y
                                             in zip(x_coords_gd_netatmo_wet,
                                                    y_coords_gd_netatmo_wet)])

                                        # create a tree from coordinates
                                        points_tree = spatial.cKDTree(
                                            neighbors_coords)

                                        # This finds the index of all points within
                                        # distance 1 of [1.5,2.5].
                                        idxs_neighbours = points_tree.query_ball_point(
                                            np.array((netatmo_x_stn,
                                                      netatmo_y_stn)),
                                            radius)

                                        x_coords_gd_netatmo_wet_neighbors = x_coords_gd_netatmo_wet[
                                            idxs_neighbours]

                                        y_coords_gd_netatmo_wet_neighbors = y_coords_gd_netatmo_wet[
                                            idxs_neighbours]

                                        if len(idxs_neighbours) > 0:

                                            for i, ix_nbr in enumerate(idxs_neighbours):
                                                # compare bad stn to it's
                                                # neighbors
                                                try:
                                                    edf_neighbor = netatmo_wet_gd_cp.iloc[ix_nbr]
                                                except Exception as msg:
                                                    print(msg, 'ERROR 2nD F')
                                                    edf_neighbor = 1.1

                                                if np.abs(edf_stn - edf_neighbor) <= diff_thr:
                                                    # add to gd stations
                                                    netatmo_wet_gd_cp[stn_] = edf_stn
                                                    ids_netatmo_stns_gd_cp = np.append(
                                                        ids_netatmo_stns_gd_cp,
                                                        stn_)
                                                    x_coords_gd_netatmo_wet_cp = np.append(
                                                        x_coords_gd_netatmo_wet_cp,
                                                        netatmo_x_stn)
                                                    y_coords_gd_netatmo_wet_cp = np.append(
                                                        y_coords_gd_netatmo_wet_cp,
                                                        netatmo_y_stn)

                                                    idx_good_stns = np.unique(np.append(
                                                        idx_good_stns, ix_stn))

                                                    # remove from original bad
                                                    # wet
                                                    x_coords_bad_netatmo_wet = np.array(list(
                                                        filter(lambda x: x != netatmo_x_stn,
                                                               x_coords_bad_netatmo_wet)))

                                                    y_coords_bad_netatmo_wet = np.array(list(
                                                        filter(lambda x: x != netatmo_y_stn,
                                                               y_coords_bad_netatmo_wet)))

                                                    netatmo_wet_bad.loc[stn_] = np.nan

                                                    ids_netatmo_stns_bad = list(
                                                        filter(lambda x: x != stn_,
                                                               ids_netatmo_stns_bad))

                                                else:
                                                    pass
#                                                   print('bad wet is bad wet')
                                        else:
                                            pass
#                                           print('\nStn has no near neighbors')

                                # get good stations for this event
                                idx_good_stns_int = [
                                    i for i in idx_good_stns]
                                # if it is a list, extract array
                                if isinstance(idx_good_stns_int, list):
                                    idx_good_stns_int = idx_good_stns_int[0]

                                edf_netatmo_vals_gd = edf_netatmo_vals[
                                    idx_good_stns_int]
                                netatmo_xcoords_gd = netatmo_xcoords[
                                    idx_good_stns_int]
                                netatmo_ycoords_gd = netatmo_ycoords[
                                    idx_good_stns_int]
                                print('\nDone with second filter')
                            else:
                                print('Netatmo second filter not used')
                                #==============================================
                                edf_netatmo_vals_gd = edf_netatmo_vals
                                netatmo_xcoords_gd = netatmo_xcoords
                                netatmo_ycoords_gd = netatmo_ycoords

                            #==================================================
                            # Interpolate DWD QUANTILES
                            #==============================================
                            if len(edf_netatmo_vals_gd) > 0:

                                # combine coordinates of DWD and Netatmo
                                dwd_netatmo_xcoords = np.concatenate(
                                    [dwd_xcoords, netatmo_xcoords_gd])
                                dwd_netatmo_ycoords = np.concatenate(
                                    [dwd_ycoords, netatmo_ycoords_gd])

                                # combine dwd and netatmo values
                                dwd_netatmo_edf = np.concatenate(
                                    [edf_dwd_vals,  edf_netatmo_vals_gd])

                                # plot configuration
#                                 plt.ioff()
#                                 plt.scatter(x_dwd_interpolate,
#                                             y_dwd_interpolate,
#                                             marker='X',
#                                             c='k', label='Interp Stn')
#
#                                 plt.scatter(dwd_xcoords,
#                                             dwd_ycoords,
#                                             marker='o',
#                                             c='b', label='DWD')
#                                 plt.scatter(netatmo_xcoords_gd,
#                                             netatmo_ycoords_gd,
#                                             marker='d',
#                                             c='r', label='Netatmo')
#                                 plt.legend(loc=0)
#                                 plt.show()
#                                 plt.close()

                                #==============================================
                                # Transform quantiles to normal space
                                #==============================================
                                std_norm_edf_dwd_vals = norm.ppf(
                                    rankdata(edf_dwd_vals) / (
                                        len(edf_dwd_vals) + 1),
                                    loc=0, scale=1)

                                std_norm_edf_dwd_netatmo_vals = norm.ppf(
                                    rankdata(dwd_netatmo_edf) / (
                                        len(dwd_netatmo_edf) + 1),
                                    loc=0, scale=1)

                                # plot histogram of transformed vals
#                                 plt.ioff()
#                                 std_norm_edf_dwd_vals_sr = pd.Series(
#                                     std_norm_edf_dwd_vals)
#                                 std_norm_edf_dwd_vals_sr.plot.hist(
#                                     grid=True, bins=5, rwidth=0.9,
#                                     alpha=0.5, color='b', label='dwd')
#                                 std_norm_edf_dwd_netatmo_vals_sr = pd.Series(
#                                     std_norm_edf_dwd_netatmo_vals)
#                                 std_norm_edf_dwd_netatmo_vals_sr.plot.hist(
#                                     grid=True, bins=5, rwidth=0.9,
#                                     alpha=0.5, color='r', label='dwd-netatmo')
#                                 plt.show()
#                                 plt.close()

                                # Test for normality
#                                 from scipy import stats
#                                 plt.ioff()
#                                 ax4 = plt.subplot(111)
#                                 res = stats.probplot(std_norm_edf_dwd_netatmo_vals,
#                                         plot=plt)
#                                 plt.show()

                                # add uncertainty on quantiles
                                edf_netatmo_vals_uncert = np.array(
                                    [(1 - per) * 0.1 for per
                                     in edf_netatmo_vals_gd])

                                # uncertainty for dwd is 0
                                uncert_dwd = np.zeros(shape=edf_dwd_vals.shape)

                                # combine both uncertainty terms
                                edf_dwd_netatmo_vals_uncert = np.concatenate([
                                    uncert_dwd,
                                    edf_netatmo_vals_uncert])

                                # get VG model from transformed DWD values
                                vgs_model_dwd_transf = df_vgs_transf.loc[event_date, 1]
                                #==============================================
                                # KRIGING
                                #==============================================
    #                             print('\n+++ KRIGING +++\n')
                                ordinary_kriging_dwd_netatmo_comb = OrdinaryKriging(
                                    xi=dwd_netatmo_xcoords,
                                    yi=dwd_netatmo_ycoords,
                                    zi=std_norm_edf_dwd_netatmo_vals,
                                    xk=x_dwd_interpolate,
                                    yk=y_dwd_interpolate,
                                    model=vgs_model_dwd_transf)

                                ordinary_kriging_un_dwd_netatmo_comb = OrdinaryKrigingWithUncertainty(
                                    xi=dwd_netatmo_xcoords,
                                    yi=dwd_netatmo_ycoords,
                                    zi=std_norm_edf_dwd_netatmo_vals,
                                    uncert=edf_dwd_netatmo_vals_uncert,
                                    xk=x_dwd_interpolate,
                                    yk=y_dwd_interpolate,
                                    model=vgs_model_dwd_transf)

                                ordinary_kriging_dwd_only = OrdinaryKriging(
                                    xi=dwd_xcoords,
                                    yi=dwd_ycoords,
                                    zi=std_norm_edf_dwd_vals,
                                    xk=x_dwd_interpolate,
                                    yk=y_dwd_interpolate,
                                    model=vgs_model_dwd_transf)

                                try:
                                    ordinary_kriging_dwd_netatmo_comb.krige()
                                    ordinary_kriging_un_dwd_netatmo_comb.krige()
                                    ordinary_kriging_dwd_only.krige()

                                except Exception as msg:
                                    print('Error while Kriging 4', msg)
                                    continue
                                # get interpolated values
                                interpolated_vals_dwd_netatmo = ordinary_kriging_dwd_netatmo_comb.zk.copy()
                                interpolated_vals_dwd_netatmo_un = ordinary_kriging_un_dwd_netatmo_comb.zk.copy()
                                interpolated_vals_dwd_only = ordinary_kriging_dwd_only.zk.copy()

                                # calcualte standard deviation of estimated
                                # values
                                std_est_vals_dwd_netatmo = np.sqrt(
                                    ordinary_kriging_dwd_netatmo_comb.est_vars)

                                std_est_vals_dwd_netatmo_un = np.sqrt(
                                    ordinary_kriging_un_dwd_netatmo_comb.est_vars)

                                std_est_vals_dwd_only = np.sqrt(
                                    ordinary_kriging_dwd_only.est_vars)

                                if (- np.inf < interpolated_vals_dwd_netatmo < np.inf) and (
                                        - np.inf < interpolated_vals_dwd_netatmo_un < np.inf) and (
                                        - np.inf < interpolated_vals_dwd_only < np.inf):

                                    #==========================================
                                    # # backtransform everything to ppt
                                    #==========================================
                                    # DWD-Netatmo +- std
                                    interpolated_vals_dwd_netatmo_min_std = (
                                        interpolated_vals_dwd_netatmo -
                                        std_est_vals_dwd_netatmo)
                                    interpolated_vals_dwd_netatmo_plus_std = (
                                        interpolated_vals_dwd_netatmo +
                                        std_est_vals_dwd_netatmo)

                                    # DWD +- std
                                    interpolated_vals_dwd_min_std = (
                                        interpolated_vals_dwd_only -
                                        std_est_vals_dwd_only)
                                    interpolated_vals_dwd_plus_std = (
                                        interpolated_vals_dwd_only +
                                        std_est_vals_dwd_only)

                                    # DWD-Netatmo with Unc +- std
                                    interpolated_vals_dwd_netatmo_un_min_std = (
                                        interpolated_vals_dwd_netatmo_un -
                                        std_est_vals_dwd_netatmo_un)
                                    interpolated_vals_dwd_netatmo_un_plus_std = (
                                        interpolated_vals_dwd_netatmo_un +
                                        std_est_vals_dwd_netatmo_un)

                                    #==========================================
                                    # # transorm using the standard normal
                                    #==========================================
                                    # DWD-Netatmo +- std
                                    interpolated_vals_dwd_netatmo_min_std_tranf = norm.cdf(
                                        interpolated_vals_dwd_netatmo_min_std,
                                        loc=0, scale=1)
                                    interpolated_vals_dwd_netatmo_plus_std_tranf = norm.cdf(
                                        interpolated_vals_dwd_netatmo_plus_std,
                                        loc=0, scale=1)

                                    # DWD +- std
                                    interpolated_vals_dwd_min_std_tranf = norm.cdf(
                                        interpolated_vals_dwd_min_std,
                                        loc=0, scale=1)
                                    interpolated_vals_dwd_plus_std_tranf = norm.cdf(
                                        interpolated_vals_dwd_plus_std,
                                        loc=0, scale=1)

                                    # DWD-Netatmo with Unc +- std
                                    interpolated_vals_dwd_netatmo_un_min_std_tranf = norm.cdf(
                                        interpolated_vals_dwd_netatmo_un_min_std,
                                        loc=0, scale=1)
                                    interpolated_vals_dwd_netatmo_un_plus_std_tranf = norm.cdf(
                                        interpolated_vals_dwd_netatmo_un_plus_std,
                                        loc=0, scale=1)

                                    #==========================================
                                    # get inv of quantiles using CDF of station
                                    #==========================================

                                    # DWD-Netatmo +- std

                                    ppt_vals_dwd_netatmo_min_std = np.mean(
                                        xppt[np.where(
                                            yppt == find_nearest(
                                                yppt,
                                             interpolated_vals_dwd_netatmo_min_std_tranf
                                             ))])

                                    ppt_vals_dwd_netatmo_plus_std = np.mean(
                                        xppt[np.where(yppt == find_nearest(
                                            yppt,
                                             interpolated_vals_dwd_netatmo_plus_std_tranf
                                             ))])

                                    # DWD +- std
                                    ppt_vals_dwd_min_std = np.mean(
                                        xppt[np.where(yppt == find_nearest(
                                            yppt,
                                            interpolated_vals_dwd_min_std_tranf
                                        ))])
                                    ppt_vals_dwd_plus_std = np.mean(
                                        xppt[np.where(yppt == find_nearest(
                                            yppt,
                                            interpolated_vals_dwd_plus_std_tranf
                                        ))])

                                    # DWD-Netatmo with Unc +- std
                                    ppt_vals_dwd_netatmo_un_min_std = np.mean(
                                        xppt[np.where(yppt == find_nearest(
                                            yppt,
                                             interpolated_vals_dwd_netatmo_un_min_std_tranf
                                             ))])
                                    ppt_vals_dwd_netatmo_un_plus_std = np.mean(
                                        xppt[np.where(yppt == find_nearest(
                                            yppt,
                                             interpolated_vals_dwd_netatmo_un_plus_std_tranf
                                             ))])

                                    # get mean of 2
                                    ppt_interpolated_vals_dwd_netatmo = (
                                        ppt_vals_dwd_netatmo_min_std +
                                        ppt_vals_dwd_netatmo_plus_std) / 2

                                    ppt_interpolated_vals_dwd_netatmo_un = (
                                        ppt_vals_dwd_netatmo_un_min_std +
                                        ppt_vals_dwd_netatmo_un_plus_std) / 2

                                    ppt_interpolated_vals_dwd_only = (
                                        ppt_vals_dwd_min_std +
                                        ppt_vals_dwd_plus_std) / 2

                                    print('**Interpolated DWD: ',
                                          ppt_interpolated_vals_dwd_only,
                                          '\n**Interpolated DWD-Netatmo: ',
                                          ppt_interpolated_vals_dwd_netatmo,
                                          '\n**Interpolated DWD-Netatmo Un: ',
                                          ppt_interpolated_vals_dwd_netatmo_un)

                                    # Saving result to DF
                                    df_interpolated_dwd_netatmos_comb.loc[
                                        event_date,
                                        stn_dwd_id] = ppt_interpolated_vals_dwd_netatmo

                                    df_interpolated_dwd_netatmos_comb_un.loc[
                                        event_date,
                                        stn_dwd_id] = ppt_interpolated_vals_dwd_netatmo_un

                                    df_interpolated_dwd_only.loc[
                                        event_date,
                                        stn_dwd_id] = ppt_interpolated_vals_dwd_only
                break

        # drop nans from df and save results
        df_interpolated_dwd_netatmos_comb.dropna(how='all', inplace=True)
        df_interpolated_dwd_netatmos_comb_un.dropna(how='all', inplace=True)
        df_interpolated_dwd_only.dropna(how='all', inplace=True)

        df_interpolated_dwd_netatmos_comb.to_csv(out_plots_path / (
            'interpolated_quantiles_dwd_%s_data_%s_using_dwd_netamo_grp_%d_%s.csv'
            % (temp_agg, title_, idx_lst_comb, _acc_)),
            sep=';', float_format='%0.2f')

        df_interpolated_dwd_netatmos_comb_un.to_csv(out_plots_path / (
            'interpolated_quantiles_un_dwd_%s_data_%s_using_dwd_netamo_grp_%d_%s.csv'
            % (temp_agg, title_, idx_lst_comb, _acc_)),
            sep=';', float_format='%0.2f')

        df_interpolated_dwd_only.to_csv(out_plots_path / (
            'interpolated_quantiles_dwd_%s_data_%s_using_dwd_only_grp_%d_%s.csv'
            % (temp_agg, title_, idx_lst_comb, _acc_)),
            sep=';', float_format='%0.2f')


stop = timeit.default_timer()  # Ending time
print('\n\a\a\a Done with everything on %s \a\a\a' %
      (time.asctime()))
