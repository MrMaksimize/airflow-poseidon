"""PD collisions _dags file."""
from airflow.operators.python_operator import PythonOperator
from trident.operators.s3_file_transfer_operator import S3FileTransferOperator
from airflow.operators.latest_only_operator import LatestOnlyOperator
from airflow.models import DAG
from datetime import datetime, timedelta
from dags.pd.pd_col_jobs import *
from trident.util import general
from trident.util.notifications import afsys_send_email

from trident.util.seaboard_updates import *

args = general.args
conf = general.config
schedule = general.schedule
start_date = general.start_date['pd_col']

dag = DAG(
    dag_id='pd_col',
    default_args=args,
    start_date=start_date,
    schedule_interval=schedule['pd_col'],
    catchup=False
    )

#: Get collisions data from FTP and save to temp folder
get_collisions_data = PythonOperator(
    task_id='get_collisions_data',
    python_callable=get_collisions_data,
    on_failure_callback=afsys_send_email,
    dag=dag)

#: Process collisions data and save result to prod folder
process_collisions_data = PythonOperator(
    task_id='process_collisions_data',
    python_callable=process_collisions_data,
    on_failure_callback=afsys_send_email,
    dag=dag)

#: Upload prod file to S3
collisions_to_S3 = S3FileTransferOperator(
    task_id='collisions_to_S3',
    source_base_path=conf['prod_data_dir'],
    source_key='pd_collisions_datasd_v1.csv',
    dest_s3_bucket=conf['dest_s3_bucket'],
    dest_s3_conn_id=conf['default_s3_conn_id'],
    dest_s3_key='pd/pd_collisions_datasd_v1.csv',
    on_failure_callback=afsys_send_email,
    dag=dag)

#: Update data inventory json
update_json_date = PythonOperator(
    task_id='update_json_date',
    python_callable=update_json_date,
    provide_context=True,
    op_kwargs={'ds_fname': 'traffic_collisions'},
    on_failure_callback=afsys_send_email,
    dag=dag)

#: Update portal modified date
update_pd_cls_md = get_seaboard_update_dag('police-collisions.md', dag)

#: Execution rules:
get_collisions_data >> process_collisions_data >> collisions_to_S3 >> [update_pd_cls_md,update_json_date]
