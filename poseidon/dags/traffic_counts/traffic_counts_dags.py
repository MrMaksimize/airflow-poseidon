"""Traffic counts _dags file."""
from airflow.operators.python_operator import PythonOperator
from airflow.models import DAG
from poseidon.operators.s3_file_transfer_operator import S3FileTransferOperator
from poseidon.operators.latest_only_operator import LatestOnlyOperator
from poseidon.dags.traffic_counts.traffic_counts_jobs import *
from poseidon.util import general
from poseidon.util.notifications import notify
from poseidon.util.seaboard_updates import update_seaboard_date, get_seaboard_update_dag


args = general.args
conf = general.config
schedule = general.schedule['traffic_counts']


dag = DAG(
    dag_id='traffic_counts',
    default_args=args,
    schedule_interval=schedule)


#: Latest Only Operator for traffic_counts
tc_latest_only = LatestOnlyOperator(
    task_id='traffic_counts_latest_only', dag=dag)


#: Downloads traffic counts xlsx from share
get_traffic_counts = PythonOperator(
    task_id='get_traffic_counts',
    python_callable=get_traffic_counts,
    on_failure_callback=notify,
    on_retry_callback=notify,
    on_success_callback=notify,
    dag=dag)

#: Cleans the downloaded XLSX file, converts it to CSV data.
clean_traffic_counts = PythonOperator(
    task_id='clean_traffic_counts',
    python_callable=clean_traffic_counts,
    on_failure_callback=notify,
    on_retry_callback=notify,
    on_success_callback=notify,
    dag=dag
)

#: Builds the prod file
build_traffic_counts = PythonOperator(
    task_id='build_traffic_counts',
    python_callable=build_traffic_counts,
    on_failure_callback=notify,
    on_retry_callback=notify,
    on_success_callback=notify,
    dag=dag
)

#: Uploads the generated production file
upload_traffic_counts = S3FileTransferOperator(
    task_id='upload_traffic_counts',
    source_base_path=conf['prod_data_dir'],
    source_key='traffic_counts_datasd.csv',
    dest_s3_bucket=conf['dest_s3_bucket'],
    dest_s3_conn_id=conf['default_s3_conn_id'],
    dest_s3_key='traffic_counts/traffic_counts_datasd.csv',
    replace=True,
    on_failure_callback=notify,
    on_retry_callback=notify,
    on_success_callback=notify,
    dag=dag)

#: Update portal modified date
update_traffic_md = get_seaboard_update_dag('traffic-volumes.md', dag)

#: Execution Rules

#: traffic_counts_latest_only must run before get_traffic_counts
get_traffic_counts.set_upstream(tc_latest_only)
#: Cleaning task triggered after data retrieval.
clean_traffic_counts.set_upstream(get_traffic_counts)
#: Production build task triggered after cleaning task.
build_traffic_counts.set_upstream(clean_traffic_counts)
#: Data upload to S3 triggered after production build task.
upload_traffic_counts.set_upstream(build_traffic_counts)
#: Update .md file after S3 upload
update_traffic_md.set_upstream(upload_traffic_counts)
