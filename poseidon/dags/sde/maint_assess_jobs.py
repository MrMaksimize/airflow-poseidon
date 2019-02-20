"""_jobs file for 'maint_assessment' layer sde extraction."""
from poseidon.util import general
from poseidon.util import geospatial
import pandas as pd
from collections import OrderedDict
import logging

conf = general.config
table = 'MAINT_ASSESSMENT'
prod_dir = conf['prod_data_dir']
layername = 'maintenance_assessment_districts_datasd'
layer = prod_dir + '/' + layername

dtypes = OrderedDict([
        ('objectid', 'int:9'),
        ('name', 'str:50'),
        ('management', 'str:60')
    ])

gtype = 'Polygon'


def sde_to_shp():
    """SDE table to Shapefile."""
    logging.info('Extracting {layername} layer from SDE.'.format(
        layername=layername))
    df = geospatial.extract_sde_data(table=table)

    logging.info('Processing {layername} df.'.format(layername=layername))
    df = df.rename(columns={'code': 'name',
                            'note_': 'management'})
    df = df.fillna('')

    logging.info('Converting {layername} df to shapefile.'.format(
        layername=layername))
    geospatial.df2shp(df=df,
                      folder=prod_dir,
                      layername=layername,
                      dtypes=dtypes,
                      gtype=gtype,
                      epsg=2230)
    return 'Successfully converted {layername} to shapefile.'.format(
           layername=layername)
