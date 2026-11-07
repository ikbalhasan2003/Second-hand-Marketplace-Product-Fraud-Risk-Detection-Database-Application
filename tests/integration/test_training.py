"""Real PostgreSQL queue + real fitted candidate and authorized CSV checks."""
from contextlib import contextmanager
import io
import csv

import pytest
from django.contrib.auth.models import Group
from django.db import connection, transaction, DatabaseError
from psycopg.rows import dict_row

from accounts.models import User
from marketplace.db import actor_transaction, one, rows
from ml.training.register import register
from ml.training.jobs import process_one, evaluate_candidate, TrainingFailure
from ml.datasets.csv_export import safe_cell, dataset_csv


@pytest.fixture(scope="session")
def training_artifact(tmp_path_factory):
    from ml.datasets.generate import generate_records
    from ml.datasets.io import write_dataset
    from ml.training.train import train
    root = tmp_path_factory.mktemp("training-jobs")
    records = generate_records(500, 42)
    # Deliberately separable synthetic labels exercise the passing registration path.
    # Gate rejection uses a separate test; this is not a performance claim.
    for record in records:
        record["features"]["keyword_count"] = 8 if record["label"] == "fraud" else 0
    write_dataset(root / "dataset", records, {
        "split_strategy": "connected groups", "dataset_version": "training-job-fixture", "generator_version": "test-separable-v1", "seed": 42,
        "export_cutoff": "2026-12-31T00:00:00+00:00", "limitations": ["Artificially separable test fixture only"],
        "sources": [{"source_type": "synthetic", "attribution": "Synthetic test fixture", "license_access_notes": "Test only"}],
    })
    train(root / "dataset", root / "model", "training-job-fixture-rf")
    return root


@pytest.fixture
def training_case(db, training_artifact, tmp_path, monkeypatch, settings):
    import shutil
    scan_artifact = tmp_path / "artifacts"
    shutil.copytree(training_artifact, scan_artifact)
    admin = User.objects.create_user('trainer-tests@example.invalid', full_name='Trainer')
    admin.groups.add(Group.objects.get_or_create(name='administrator')[0])
    ids = register(connection.connection, scan_artifact / 'dataset', scan_artifact / 'model',
                   scan_artifact, admin.pk, 'Register approved training test data')
    settings.ARTIFACT_ROOT = scan_artifact
    @contextmanager
    def connect(*args, **kwargs):
        underlying = connection.connection
        original = underlying.row_factory
        underlying.row_factory = dict_row
        try:
            yield underlying
        finally:
            underlying.execute('SELECT pg_advisory_unlock(719241,9)')
            underlying.row_factory = original
    monkeypatch.setattr('ml.training.jobs.psycopg.connect', connect)
    return admin, ids, scan_artifact


def test_csv_cells_and_privacy_projection():
    for value in ('=cmd()', ' +1', '-1', '@SUM(A1)', '\tformula', '\rformula', '\ufeff=1'):
        assert safe_cell(value).startswith("'")
    payload = dataset_csv([{'features': {}, 'category': '=malicious', 'private_contact': 'PRIVATE'}],
                          {'dataset_version': 'v1', 'dataset_sha256': 'abc'})
    assert b'PRIVATE' not in payload
    result = list(csv.DictReader(io.StringIO(payload.decode('utf-8-sig'))))
    assert result[0]['category'] == "'=malicious"


def test_evaluation_gate_rejects_bad_or_small_candidates():
    config = {'minimum_partition_samples': 10, 'minimum_precision': .5, 'minimum_recall': .5}
    values = {'sample_count': 20, 'fraud_count': 10, 'precision': .2, 'recall': .9}
    report = {'models': {'random_forest': {'validation': {'all': values}, 'test': {'all': values}}}}
    with pytest.raises(TrainingFailure, match='precision/recall'):
        evaluate_candidate(report, config)
    values.update(precision=.9, fraud_count=20)
    with pytest.raises(TrainingFailure, match='both labels'):
        evaluate_candidate(report, config)


def test_training_runs_with_explicit_process_grants(training_case):
    from pathlib import Path
    admin, ids, root = training_case
    base = Path(__file__).resolve().parents[2]
    with connection.cursor() as cursor:
        for name in ('008_privileges.sql', '009_app_privileges.sql'):
            script = (base / 'database' / name).read_text(encoding='utf-8')
            cursor.execute(script.replace('BEGIN;', '').replace('COMMIT;', ''))
        cursor.execute('SET LOCAL ROLE secondhand_training')
    try:
        result = process_one('test', root)
    finally:
        with connection.cursor() as cursor:
            cursor.execute('RESET ROLE')
    assert result['status'] == 'succeeded', one(
        'SELECT error_code,error_message FROM ai_training_jobs WHERE dataset_id=%s', [ids['dataset_id']])


def test_training_request_provenance_is_immutable(training_case):
    admin, ids, root = training_case
    for statement in (
        "UPDATE ai_training_jobs SET configuration='{}'::jsonb WHERE dataset_id=%s",
        'DELETE FROM ai_training_jobs WHERE dataset_id=%s',
    ):
        with pytest.raises(DatabaseError), transaction.atomic():
            rows(statement, [ids['dataset_id']])


def test_freeze_trigger_dedup_real_training_and_manual_activation(training_case):
    admin, ids, root = training_case
    job = one('SELECT * FROM ai_training_jobs WHERE dataset_id=%s', [ids['dataset_id']])
    assert job['status'] == 'queued'
    with actor_transaction(admin, 'Select existing dataset for fitting'):
        assert one('SELECT app_enqueue_training(%s) AS id', [ids['dataset_id']])['id'] == job['job_id']
    active_before = one("SELECT model_id FROM risk_models WHERE state='active'")
    result = process_one('test', root)
    assert result == {'job_id': job['job_id'], 'status': 'succeeded'}, one('SELECT error_message FROM ai_training_jobs WHERE job_id=%s', [job['job_id']])
    completed = one('SELECT * FROM ai_training_jobs WHERE job_id=%s', [job['job_id']])
    model = one('SELECT * FROM risk_models WHERE model_id=%s', [completed['model_id']])
    assert model['state'] == 'registered'
    assert model['dataset_id'] == ids['dataset_id']
    assert one("SELECT model_id FROM risk_models WHERE state='active'") == active_before
    assert (root / 'training' / str(job['job_id']) / '1' / 'snapshot.json').exists()
    assert one('SELECT count(*) AS n FROM model_evaluations WHERE model_id=%s', [model['model_id']])['n'] > 0
    assert process_one('test', root) is None
    from marketplace.services.moderation import activate_configuration
    rules = one("SELECT ruleset_id FROM risk_rulesets WHERE state='active'")
    activate_configuration(admin, model['model_id'], ids['ruleset_id'], 'Activate evaluated candidate explicitly',
        active_before['model_id'] if active_before else None, rules['ruleset_id'] if rules else None)
    assert one("SELECT model_id FROM risk_models WHERE state='active'")['model_id'] == model['model_id']
    assert one("SELECT count(*) AS n FROM risk_rescan_campaigns WHERE event_type='model_activation'")['n'] > 0


def test_failures_retry_stop_and_sanitize(training_case, monkeypatch):
    admin, ids, root = training_case
    def broken(*args):
        raise RuntimeError('secret password /private/path')
    monkeypatch.setattr('ml.training.train.train', broken)
    for attempt in range(1, 4):
        assert process_one('test', root)['status'] == 'failed'
        job = one('SELECT * FROM ai_training_jobs WHERE dataset_id=%s', [ids['dataset_id']])
        assert job['attempts'] == attempt
        assert 'secret' not in job['error_message']
        assert process_one('test', root) is None
        rows('UPDATE ai_training_jobs SET retry_at=clock_timestamp() WHERE job_id=%s', [job['job_id']])
    assert process_one('test', root) is None
    assert one('SELECT model_id FROM ai_training_jobs WHERE dataset_id=%s', [ids['dataset_id']])['model_id'] is None


def test_gate_failure_keeps_working_model_and_recovers_interruption(training_case, monkeypatch):
    admin, ids, root = training_case
    active = one("SELECT model_id FROM risk_models WHERE state='active'")
    rows("UPDATE ai_training_jobs SET status='running',attempts=1 WHERE dataset_id=%s", [ids['dataset_id']])
    def reject(*args):
        raise TrainingFailure('Candidate failed evaluation; collect more labels.')
    monkeypatch.setattr('ml.training.jobs.evaluate_candidate', reject)
    assert process_one('test', root)['status'] == 'failed'
    job = one('SELECT * FROM ai_training_jobs WHERE dataset_id=%s', [ids['dataset_id']])
    assert job['attempts'] == 2 and job['model_id'] is None
    assert one("SELECT model_id FROM risk_models WHERE state='active'") == active


def test_csv_authorization_checksums_and_audit(training_case, client):
    admin, ids, root = training_case
    url = f"/admin-app/exports/{ids['dataset_id']}/download/"
    assert client.post(url, {'format': 'csv', 'reason': 'Review training CSV'}).status_code == 302
    buyer = User.objects.create_user('csv-buyer@example.invalid', full_name='Buyer')
    buyer.groups.add(Group.objects.get_or_create(name='buyer')[0])
    client.force_login(buyer)
    assert client.post(url, {'format': 'csv', 'reason': 'Review training CSV'}).status_code == 403
    assert client.get('/admin-app/ai-settings/').status_code == 403
    client.force_login(admin)
    assert client.get('/admin-app/ai-settings/').status_code == 200
    response = client.post(url, {'format': 'csv', 'reason': 'Review training CSV'})
    assert response.status_code == 200
    assert response['Content-Type'].startswith('text/csv')
    assert response['Cache-Control'] == 'private, no-store'
    assert response['X-Audit-Receipt']
    content = b''.join(response.streaming_content)
    assert b'dataset_sha256' in content and b'private_contact' not in content
    rows("UPDATE ai_training_jobs SET status='failed' WHERE dataset_id=%s", [ids['dataset_id']])
    with actor_transaction(admin, 'Ensure non-admin database actor is rejected'):
        rows("SELECT set_config('app.actor_id',%s,true)", [str(buyer.pk)])
        with pytest.raises(DatabaseError), transaction.atomic():
            rows('SELECT app_enqueue_training(%s)', [ids['dataset_id']])


def test_worker_lock_prevents_concurrent_claim(training_case):
    from psycopg import Connection
    admin, ids, root = training_case
    params = connection.get_connection_params()
    params.pop('cursor_factory', None)
    with Connection.connect(**params, autocommit=True) as blocker:
        blocker.execute('SELECT pg_advisory_lock(719241,9)')
        try:
            assert process_one('test', root) is None
            assert one('SELECT status FROM ai_training_jobs WHERE dataset_id=%s', [ids['dataset_id']])['status'] == 'queued'
        finally:
            blocker.execute('SELECT pg_advisory_unlock(719241,9)')


@pytest.mark.parametrize('failure', ['data', 'dependency', 'checksum'])
def test_unavailable_data_dependencies_and_tampered_input_fail(training_case, monkeypatch, failure):
    admin, ids, root = training_case
    if failure == 'data':
        def insufficient(*args):
            raise TrainingFailure('Insufficient labeled data; freeze more independent groups.')
        monkeypatch.setattr('ml.training.jobs.verified_dataset', insufficient)
    elif failure == 'dependency':
        def missing(*args):
            raise ImportError('sensitive local details')
        monkeypatch.setattr('ml.training.train.train', missing)
    else:
        with (root / 'dataset' / 'records.jsonl').open('a') as output:
            output.write('{}\n')
    result = process_one('test', root)
    assert result['status'] == 'failed'
    job = one('SELECT * FROM ai_training_jobs WHERE dataset_id=%s', [ids['dataset_id']])
    assert job['model_id'] is None
    assert 'sensitive' not in job['error_message']
    assert job['error_code'] == ('dependencies' if failure == 'dependency' else 'data_or_evaluation' if failure == 'data' else 'data_or_evaluation')


def test_threshold_publication_rescans_without_training(training_case):
    from marketplace.services.moderation import create_ruleset, activate_configuration
    admin, ids, root = training_case
    count = one('SELECT count(*) AS n FROM ai_training_jobs')['n']
    schema = one('SELECT feature_schema_id FROM risk_models WHERE model_id=%s', [ids['model_id']])
    ruleset = create_ruleset(admin, 'threshold-change-only', schema['feature_schema_id'], 35, 80, 12,
                            'Adjust supported risk score bands')
    current_model = one("SELECT model_id FROM risk_models WHERE state='active'")
    current_rules = one("SELECT ruleset_id FROM risk_rulesets WHERE state='active'")
    activate_configuration(admin, ids['model_id'], ruleset, 'Publish threshold rules and rescan',
        current_model['model_id'] if current_model else None, current_rules['ruleset_id'] if current_rules else None)
    assert one('SELECT count(*) AS n FROM ai_training_jobs')['n'] == count
    assert one("SELECT count(*) AS n FROM risk_rescan_campaigns WHERE event_type='ruleset_publication'")['n'] > 0


def test_real_small_dataset_is_rejected(tmp_path):
    from ml.datasets.generate import generate_records
    from ml.datasets.io import write_dataset
    from ml.training.jobs import verified_dataset
    manifest = write_dataset(tmp_path / 'small', generate_records(60, 42)[:10], {
        'dataset_version': 'small-fixture', 'generator_version': 'test', 'seed': 42,
        'export_cutoff': '2026-12-31T00:00:00+00:00', 'limitations': ['Small test dataset'],
        'sources': [{'source_type': 'synthetic', 'attribution': 'Test only', 'license_access_notes': 'No private data'}],
    })
    with pytest.raises(TrainingFailure, match='Insufficient labeled data'):
        verified_dataset(tmp_path, {'manifest_key': 'small/manifest.json', 'version': 'small-fixture',
                                   'dataset_sha256': manifest['dataset_sha256']})


def test_web_role_can_enqueue_but_cannot_modify_jobs(training_case):
    import re
    from pathlib import Path
    admin, ids, root = training_case
    project = Path(__file__).resolve().parents[2]
    with connection.cursor() as cursor:
        for name in ('008_privileges.sql', '009_app_privileges.sql'):
            script = (project / 'database' / name).read_text(encoding='utf-8')
            cursor.execute(re.sub(r'^\s*(BEGIN|COMMIT);\s*$', '', script, flags=re.MULTILINE))
    with actor_transaction(admin, 'Verify restricted runtime job authorization'):
        rows('SET LOCAL ROLE secondhand_web')
        job = one('SELECT app_enqueue_training(%s) AS id', [ids['dataset_id']])
        assert one('SELECT job_id FROM ai_training_jobs WHERE job_id=%s', [job['id']])
        with pytest.raises(DatabaseError), transaction.atomic():
            rows("UPDATE ai_training_jobs SET status='succeeded' WHERE job_id=%s", [job['id']])
        rows('RESET ROLE')
