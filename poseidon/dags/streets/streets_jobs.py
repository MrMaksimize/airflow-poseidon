import os
import pandas as pd
import requests
from datetime import datetime, timedelta
import logging
from airflow.hooks.mssql_hook import MsSqlHook
from poseidon.util import general

conf = general.config

prod_file = {
    'sdif': conf['prod_data_dir'] + '/sd_paving_datasd.csv',
    'imcat': conf['prod_data_dir'] + '/sd_paving_imcat_datasd.csv'
}


def get_streets_paving_data(mode='sdif', **kwargs):
    """Get streets paving data from DB."""
    pv_query = general.file_to_string('./sql/pavement_ex.sql', __file__)
    pv_conn = MsSqlHook(mssql_conn_id='streets_cg_sql')

    moratorium_string = "Post Construction"
    phone_UTLY = "858-627-3200"
    phone_OTHER = "619-527-7500"
    TSW_PM = "JLahmann@sandiego.gov"
    UTLY_PM = "Engineering@sandiego.gov"
    ACT_OVERLAY_CONCRETE_PM = "CHudson@sandiego.gov"
    ACT_SLURRY_SERIES_PM = "JJaro@sandiego.gov"

    # Different String for imcat mode.
    if mode == 'imcat':
        moratorium_string = "Post-Construction"

    df = pv_conn.get_pandas_df(pv_query)

    for i in [
            'seg_id', 'rd_seg_id', 'wo_id', 'wo_name', 'wo_status',
            'wo_proj_type', 'job_activity', 'seg_func_class'
    ]:

        df[i] = df[i].astype(str)

    df['job_completed_cbox'] = df['job_completed_cbox'].astype(bool)

    # Backfill - set all fields to mora
    df.loc[df.wo_status.str.contains(
        'post construction|moratorium|post-construction',
        regex=True,
        case=False), "wo_status"] = moratorium_string

    # Remove Records w/o A Completed Date ONLY in the UTLY and TSW work order
    # IMCAT ONLY
    if mode == 'imcat':
        df = df.query('not '\
                    + '((wo_id == "UTLY" & job_end_dt.isnull()) '\
                    + 'or (wo_id == "TSW" & job_end_dt.isnull()))')

        # Remove empty activities (IMCAT ONLY)
        df = df.query('not '\
                    + '(job_activity.isnull() '\
                    + '| job_activity == "" '\
                    + '| job_activity == "None")')

    # Remove Data Entry
    # Remove mill / pave
    # Remove Structure Widening
    # Remove Patching
    if mode == 'imcat':
        remove_search = 'data entry|mill|structure wid|patching'
    else:
        remove_search = 'data entry|structure wid|patching'

    df = df[~(df.job_activity.str.contains(
        remove_search, regex=True, case=False))]

    # Search Strings
    concrete_search = "panel rep|pcc - reconstruc"
    slurry_search = "surface treatment|scrub seal|cape seal|central mix"
    overlay_search = "resurfacing|overlay|ac overlay|mill|ac - overlay|ac - ac overlay|ac - reconstruct|ac inlay"

    # Set Proj Type to NA
    df['wo_proj_type'] = None
    # Concrete
    df.loc[df.job_activity.str.contains(
        concrete_search, regex=True, case=False), 'wo_proj_type'] = 'Concrete'
    # Slurry
    df.loc[df.job_activity.str.contains(
        slurry_search, regex=True, case=False), 'wo_proj_type'] = 'Slurry'
    # Overlay
    df.loc[df.job_activity.str.contains(
        overlay_search, regex=True, case=False), 'wo_proj_type'] = 'Overlay'

    # Remove All Records over 5 Years Old;
    #pv <- pv[(as.Date(pv$job_end_dt) > (today() - years(5))) | is.na(pv$job_end_dt),]

    # Create ref dates
    today = kwargs['execution_date']
    five_yrs_ago = today.replace(year=(today.year - 5))
    three_yrs_ago = today.replace(year=(today.year - 3))

    # Remove records
    df = df[(df.job_end_dt > five_yrs_ago) | (df.job_end_dt.isnull())]

    # Remove Slurry Records > 3 Years Old
    # IMCAT ONLY
    if mode == 'imcat':
        mask = ~((df.wo_proj_type == 'Slurry') &
                 (df.job_end_dt < three_yrs_ago))
        df = df[mask]

    # Create a feature for completed jobs
    df['final_job_completion_state'] = False
    #pv[(!is.na(pv$job_end_dt) & pv$job_completed_cbox == 1), "final_job_completion_state"] <- 1

    df.loc[df.job_end_dt.notnull(), "final_job_completion_state"] = True

    # Set all completed jobs to Moratorium status
    df.loc[df.final_job_completion_state == True,
           "wo_status"] = moratorium_string

    # Set Dates in The future for TSW work orders as Construction.
    mask = (df.wo_id == 'TSW') & \
           (df.job_end_dt.notnull()) & \
           (df.job_end_dt > today)

    df.loc[mask, "wo_status"] = "Construction"

    # Set Phone # For UTLY
    df.loc[df.wo_id == 'UTLY', 'wo_pm_phone'] = phone_UTLY

    # Set Phone # for Everything else
    df.loc[df.wo_id != 'UTLY', 'wo_pm_phone'] = phone_OTHER

    # Set PM for UTLY
    df.loc[df.wo_id == 'UTLY', 'wo_pm'] = UTLY_PM

    # Set PM for TSW
    df.loc[df.wo_id == 'TSW', 'wo_pm'] = TSW_PM

    # Set PM for Overlay / Concrete
    #mask = (df.wo_proj_type == 'Overlay') | (df.wo_proj_type == 'Concrete') & (df.wo_pm.isnull())
    mask = (df.wo_pm.isnull()) & ((df.wo_proj_type == 'Overlay') |
                                  (df.wo_proj_type == 'Concrete'))
    df.loc[mask, 'wo_pm'] = ACT_OVERLAY_CONCRETE_PM

    # Set PM for Slurry / Series
    mask = (df.wo_pm.isnull()) & ((df.wo_proj_type == 'Slurry') |
                                  (df.wo_proj_type == 'Series Circuit'))
    df.loc[mask, 'wo_pm'] = ACT_SLURRY_SERIES_PM

    # Spot Unknown
    mask = (df.job_activity.isnull()) | (df.job_activity == None) | (df.job_activity == 'None') | (df.job_activity == '')\
        |(df.wo_proj_type.isnull()) | (df.wo_proj_type == None) | (df.wo_proj_type == 'None') | (df.wo_proj_type == '')\
        |(df.wo_status.isnull()) | (df.wo_status == None) | (df.wo_status == 'None') | (df.wo_status == '')

    spot_unknown = df[mask]

    logging.info('Found {} records with no activity, type or status'.format(
        spot_unknown.shape[0]))

    # Remove unknown
    df = df[~mask]

    # Sort by job end date time
    df = df.sort_values(by='job_end_dt', na_position='last', ascending=False)

    # Remove duplicates, although it doesn't make sense
    # This is wrong.
    df = df.drop_duplicates('seg_id', keep='first')

    # Rename columns we're keeping
    df = df.rename(columns={
        'pve_id': 'PVE_ID',
        'seg_id': 'SEG_ID',
        'wo_id': 'PROJECTID',
        'wo_name': 'TITLE',
        'wo_pm': 'PM',
        'wo_pm_phone': 'PM_PHONE',
        'wo_design_start_dt': 'START',
        'wo_design_end_dt': 'END',
        'wo_resident_engineer': 'RESIDENT_ENGINEER',
        'job_end_dt': 'MORATORIUM',
        'wo_status': 'STATUS',
        'wo_proj_type': 'TYPE',
        'seg_length_ft': 'LENGTH',
        'seg_width_ft': 'WIDTH',
    })

    # Regex for the keeps:
    df = df.filter(regex="^[A-Z0-9]")

    # Remove START and END for projects in moratorium:
    df.loc[df.STATUS == moratorium_string, ['START', 'END']] = None

    # For IMCAT uppercase status
    if mode == 'imcat':
        df['STATUS'] = df['STATUS'].str.upper()

    # Write csv
    logging.info('Writing ' + str(df.shape[0]) + ' rows in mode ' + mode)
    general.pos_write_csv(
        df, prod_file[mode], date_format=conf['date_format_ymd_hms'])
    return "Successfully wrote prod file at " + prod_file[mode]


def build_sonar_miles_aggs(mode='sdif', pav_type='total', **kwargs):
    pav_csv = prod_file[mode]
    dbl_spec = 2

    range_start_dt = kwargs['range_start']
    print range_start_dt

    # Read CSV
    df = pd.read_csv(pav_csv)

    # Multiply Length by 2x when street is over 50 feet wide
    df.loc[df['WIDTH'] > 50, "LENGTH"] = (df.loc[df['WIDTH'] > 50, "LENGTH"] * 2)

    # Convert to miles
    df['LENGTH'] = df.LENGTH / 5280

    # Convert moratorium to date
    df["MORATORIUM"] = pd.to_datetime(df["MORATORIUM"])

    # Get post construction, within range
    mask = (df.STATUS == 'Post Construction') & \
           (df.MORATORIUM >= range_start_dt)
    df = df[mask]

    # Get sums
    sums = df[["LENGTH", "TYPE"]].groupby("TYPE").sum()
    sums.reset_index(inplace=True)

    # Get total paved
    total = round(sums["LENGTH"].sum(), dbl_spec)

    # Get total overlay
    overlay = sums.loc[sums["TYPE"] == 'Overlay', "LENGTH"].reset_index()

    if len(overlay) == 0:
        overlay = 0
    else:
        overlay = round(overlay["LENGTH"][0], dbl_spec)

    # Get total slurry
    slurry = sums.loc[sums["TYPE"] == 'Slurry', "LENGTH"].reset_index()
    if len(slurry) == 0:
        slurry = 0
    else:
        slurry = round(slurry["LENGTH"][0], dbl_spec)


    # Return dicts
    if pav_type == 'total':
        logging.info('{} miles paved {}'.format(pav_type, total))
        return {'value': total}
    elif pav_type == 'overlay':
        logging.info('{} miles paved {}'.format(pav_type, overlay))
        return {'value': overlay}
    elif pav_type == 'slurry':
        logging.info('{} miles paved {}'.format(pav_type, slurry))
        return {'value': slurry}
    else:
        raise ValueError("Unknown pav_type")
