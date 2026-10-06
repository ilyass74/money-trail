"""Import du contrat reference-v1, avec instantané brut et reprise idempotente."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .reference import ROOT, HEADERS, EXTRA_HEADERS, check_reference


@dataclass(frozen=True)
class SourceFile:
    entity: str
    filename: str
    content: bytes
    sha256: str
    rows: tuple


@dataclass(frozen=True)
class Bundle:
    label: str
    fingerprint: str
    manifest_bytes: bytes
    manifest: dict
    files: tuple[SourceFile, ...]


def prepare_bundle(directory: Path) -> Bundle:
    # Lecture des octets une seule fois. La validation porte sur cette copie,
    # et non sur un fichier pouvant changer entre contrôle et chargement.
    manifest_bytes = (directory / 'manifest.json').read_bytes()
    source_manifest=json.loads(manifest_bytes)
    entities=set(HEADERS)
    if source_manifest.get('contract_version')=='finance-v1':
        entities.update(item['entity'] for item in source_manifest['files'] if item['entity'] in EXTRA_HEADERS)
    contents = {f'{entity}.csv': (directory / f'{entity}.csv').read_bytes() for entity in entities}
    with tempfile.TemporaryDirectory() as temporary:
        snapshot = Path(temporary)
        (snapshot / 'manifest.json').write_bytes(manifest_bytes)
        for filename, content in contents.items():
            (snapshot / filename).write_bytes(content)
        check_reference(snapshot)
    manifest = json.loads(manifest_bytes)
    files = []
    fingerprint = hashlib.sha256(manifest_bytes)
    for item in sorted(manifest['files'], key=lambda entry: entry['entity']):
        content = contents[item['file']]
        sha = hashlib.sha256(content).hexdigest()
        rows = tuple(csv.DictReader(io.StringIO(content.decode('utf-8'), newline='')))
        files.append(SourceFile(item['entity'], item['file'], content, sha, rows))
        fingerprint.update(item['entity'].encode('utf-8') + b'\0' + bytes.fromhex(sha))
    return Bundle(directory.name, fingerprint.hexdigest(), manifest_bytes, manifest, tuple(files))


def local_config(env_path: Path = ROOT / '.env') -> dict:
    values = {}
    for line in (env_path.read_text(encoding='utf-8-sig') if env_path.exists() else '').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if not separator:
            raise ValueError('Ligne .env invalide.')
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    for source,target in [('MT_DB_HOST','POSTGRES_HOST'),('MT_DB_PORT','POSTGRES_PORT'),('MT_DB_NAME','POSTGRES_DB'),('MT_DB_USER','POSTGRES_USER'),('MT_DB_PASSWORD','POSTGRES_PASSWORD')]:
        if source in os.environ:values[target]=os.environ[source]
    password = values.get('POSTGRES_PASSWORD', '')
    if not password or password == '__GENERATE_ME__':
        raise ValueError('Mot de passe .env absent. Relancer scripts/prepare.ps1.')
    port = int(values.get('POSTGRES_PORT', '55432'))
    if not 1 <= port <= 65535:
        raise ValueError('Port PostgreSQL invalide.')
    return dict(host=values.get('POSTGRES_HOST','127.0.0.1'), port=port, dbname=values.get('POSTGRES_DB', 'money_trail'),
                user=values.get('POSTGRES_USER', 'moneytrail'), password=password,
                connect_timeout=10, application_name='money_trail_import')


def setup_database(connection):
    # Un verrou transactionnel sérialise les installations concurrentes.
    with connection.transaction():
        connection.execute('SELECT pg_advisory_xact_lock(732084651::bigint)')
        connection.execute((ROOT / 'sql' / '001_schemas.sql').read_text(encoding='utf-8')
                           .replace('BEGIN;', '').replace('COMMIT;', ''))
        connection.execute('''CREATE TABLE IF NOT EXISTS meta.schema_migrations (
            version TEXT PRIMARY KEY, sha256 CHAR(64) NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        migration = (ROOT / 'sql' / '002_import.sql').read_bytes()
        checksum = hashlib.sha256(migration).hexdigest()
        previous = connection.execute(
            'SELECT sha256 FROM meta.schema_migrations WHERE version = %s', ('002_import',)).fetchone()
        if previous:
            if previous[0] != checksum:
                raise ValueError('Migration deja appliquee avec une autre empreinte. Ajouter une nouvelle migration.')
        else:
            connection.execute(migration.decode('utf-8'))
            connection.execute('INSERT INTO meta.schema_migrations (version, sha256) VALUES (%s,%s)',
                               ('002_import', checksum))


def import_directory(connection, directory: Path, fail_hook=None) -> dict:
    from psycopg.types.json import Jsonb
    if not connection.autocommit:
        raise ValueError('Utiliser une connexion autocommit pour journaliser les tentatives separement.')
    attempt_id = uuid4()
    connection.execute('''INSERT INTO meta.import_attempts
        (attempt_id,dataset_label,status) VALUES (%s,%s,'started')''', (attempt_id, directory.name))
    try:
        bundle = prepare_bundle(directory)
        with connection.transaction():
            lock = int.from_bytes(bytes.fromhex(bundle.fingerprint[:16]), 'big', signed=True)
            connection.execute('SELECT pg_advisory_xact_lock(%s::bigint)', (lock,))
            previous = connection.execute('SELECT batch_id FROM meta.import_batches WHERE fingerprint=%s',
                                          (bundle.fingerprint,)).fetchone()
            if previous:
                batch_id, inserted, status = previous[0], 0, 'skipped_duplicate'
            else:
                batch_id, inserted, status = uuid4(), 0, 'success'
                m = bundle.manifest
                connection.execute('''INSERT INTO meta.import_batches
                    (batch_id,fingerprint,dataset_label,contract_version,company_id,currency,
                     control_on,manifest,manifest_bytes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (batch_id,bundle.fingerprint,bundle.label,m['contract_version'],m['company_id'],
                     m['currency'],m['control_on'],Jsonb(m),bundle.manifest_bytes))
                for index, file in enumerate(bundle.files):
                    if fail_hook:
                        fail_hook(index)
                    file_id = connection.execute('''INSERT INTO meta.import_files
                        (batch_id,entity,source_filename,sha256,row_count,source_bytes)
                        VALUES (%s,%s,%s,%s,%s,%s) RETURNING file_id''',
                        (batch_id,file.entity,file.filename,file.sha256,len(file.rows),file.content)).fetchone()[0]
                    with connection.cursor() as cursor:
                        records = []
                        for line, row in enumerate(file.rows, 1):
                            digest = hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False,
                                                               separators=(',',':')).encode('utf-8')).hexdigest()
                            records.append((file_id,line,row['company_id'],row['source_system'],
                                            row['source_id'],Jsonb(row),digest))
                        cursor.executemany('''INSERT INTO raw.source_records
                            (file_id,row_number,company_id,source_system,source_id,payload,payload_sha256)
                            VALUES (%s,%s,%s,%s,%s,%s,%s)''', records)
                    inserted += len(file.rows)
            connection.execute('''UPDATE meta.import_attempts SET status=%s,batch_id=%s,
                inserted_records=%s,finished_at=CURRENT_TIMESTAMP WHERE attempt_id=%s''',
                (status,batch_id,inserted,attempt_id))
        return dict(status=status,attempt_id=str(attempt_id),batch_id=str(batch_id),
                    inserted_records=inserted,fingerprint=bundle.fingerprint)
    except Exception as error:
        # Ne pas journaliser une chaîne de connexion ou des données financières.
        connection.execute('''UPDATE meta.import_attempts SET status='failed',
            finished_at=CURRENT_TIMESTAMP,error_code=%s WHERE attempt_id=%s''',
            (type(error).__name__,attempt_id))
        raise


def inspect_database(connection) -> dict:
    totals = dict(connection.execute('''SELECT 'batches',count(*) FROM meta.import_batches
        UNION ALL SELECT 'files',count(*) FROM meta.import_files
        UNION ALL SELECT 'records',count(*) FROM raw.source_records''').fetchall())
    attempts = [dict(status=row[0], count=row[1]) for row in connection.execute(
        'SELECT status,count(*) FROM meta.import_attempts GROUP BY status ORDER BY status')]
    entities = [dict(entity=row[0],records=row[1]) for row in connection.execute('''
        SELECT f.entity,count(r.record_id) FROM meta.import_files f
        LEFT JOIN raw.source_records r ON r.file_id=f.file_id
        WHERE f.batch_id=(SELECT batch_id FROM meta.import_batches ORDER BY ingested_at DESC LIMIT 1)
        GROUP BY f.entity ORDER BY f.entity''')]
    return dict(totals=totals,attempts=attempts,latest_batch_entities=entities)
