import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter

from app.ingestion.extractors.text_pdf_extractor import parse_pdf
from app.ingestion.parser import parse_document
from app.ingestion.structured import extract_fields

PACKET = Path(__file__).resolve().parents[1] / 'data/demo_documents/robert_chen'


@pytest.mark.parametrize('filename,count', [
    ('01_clinic_follow_up', 8), ('02_medication_review', 9), ('03_laboratory_report', 8),
])
def test_real_pdf_and_text_exports_match_labeled_packet(filename, count):
    result = parse_document(str(PACKET / f'{filename}.pdf'))
    assert result.metadata == {'page_count': 1, 'format': 'pdf', 'parser': 'pypdf', 'ocr_used': False}
    assert 'SYNTHETIC TRAINING RECORD' in result.text
    pdf_fields = extract_fields(result.text)
    text_fields = extract_fields((PACKET / f'{filename}.txt').read_text())
    assert len(pdf_fields['fields']) == count
    assert pdf_fields['warnings'] == []
    def canonical(result):
        return sorted(json.dumps({'kind': f['kind'], 'data': f['data']}, sort_keys=True)
                      for f in result['fields'])
    assert canonical(pdf_fields) == canonical(text_fields)
    for field in pdf_fields['fields']:
        assert result.text[field['start']:field['end']] == field['quote']
    if filename == '01_clinic_follow_up':
        assert any(f['data'].get('name') == 'pneumonia' and f['data'].get('status') == 'negated' for f in pdf_fields['fields'])
    if filename == '02_medication_review':
        medication = next(f['data'] for f in pdf_fields['fields'] if f['data'].get('name') == 'Metformin')
        assert medication['dose'] == '500mg' and medication['status'] == 'held'
    if filename == '03_laboratory_report':
        creatinine = next(f['data'] for f in pdf_fields['fields'] if f['data'].get('test_name') == 'Creatinine')
        assert creatinine == {'test_name': 'Creatinine', 'value': '138', 'unit': 'µmol/L',
                              'reference_range': '60–110', 'flag': 'high', 'date': '2024-06-12'}


def test_full_pdf_packet_upload_review_and_saved_record(client):
    client.post('/api/review/session', json={'name': 'Packet Reviewer'})
    for filename in ('01_clinic_follow_up', '02_medication_review', '03_laboratory_report'):
        path = PACKET / f'{filename}.pdf'
        response = client.post('/api/rag/ingest/demo-case-b', files={'file': (path.name, path.read_bytes(), 'application/pdf')})
        assert response.status_code == 200, response.text
        assert response.json()['chunks_indexed'] > 0
        run = response.json()['review_run']
        assert client.post(f"/api/review/runs/{run['id']}/finalize", json={'version': run['version']}).status_code == 409
        for finding in list(run['findings']):
            body = {'version': run['version'], 'action': 'accepted', 'reason': 'Compared with the synthetic PDF source'}
            if finding['extracted']['data'].get('name') == 'Ramipril':
                body.update(action='edited', edited_data={**finding['extracted']['data'], 'frequency': 'once daily'})
            response = client.post(f"/api/review/runs/{run['id']}/findings/{finding['id']}/decision", json=body)
            assert response.status_code == 200, response.text
            run = response.json()
        assert client.post(f"/api/review/runs/{run['id']}/finalize", json={'version': run['version']}).status_code == 200
    record = client.get('/api/agent/cases/case_b').json()
    fields = record['summary']['reviewed_fields']
    assert len(fields) == 25
    assert any(f['data'].get('name') == 'Ramipril' and f['data'].get('frequency') == 'once daily' for f in fields)
    assert any(f['data'].get('name') == 'Metformin' and f['data'].get('status') == 'held' for f in fields)
    assert client.get('/api/review/patients/demo-case-a/fields').json()['fields'] == []


def test_pdf_upload_errors_are_actionable(client):
    response = client.post('/api/rag/ingest/p', files={'file': ('broken.pdf', b'not a PDF', 'application/pdf')})
    assert response.status_code == 422
    assert 'valid PDF' in response.json()['detail']
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.encrypt('synthetic-password')
    buffer = io.BytesIO()
    writer.write(buffer)
    response = client.post('/api/rag/ingest/p', files={'file': ('encrypted.pdf', buffer.getvalue(), 'application/pdf')})
    assert response.status_code == 422
    assert 'encrypted' in response.json()['detail']


def test_image_only_pdf_delegates_to_existing_optional_parser(tmp_path, monkeypatch):
    path = tmp_path / 'image-only.pdf'
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.write(path)
    sentinel = object()
    monkeypatch.setitem(sys.modules, 'app.ingestion.extractors.pdf_extractor',
                        SimpleNamespace(parse_pdf=lambda *args, **kwargs: sentinel))
    assert parse_pdf(str(path)) is sentinel


def test_unrecognized_layout_table_does_not_create_lab_fields():
    text = 'Item      Price      Owner      Ref Range      Flag\nChair     138        µmol/L     60–110         H'
    assert extract_fields(text)['fields'] == []


def test_layout_table_preserves_empty_unit_and_flag_columns():
    text = f"{'Test':<20}{'Result':<12}{'Units':<14}{'Ref Range':<20}Flag\n"
    text += f"{'INR':<20}{'2.8':<12}{'':<14}{'2.5–3.5':<20}\n"
    result = extract_fields(text)
    assert result['fields'][0]['data'] == {'test_name': 'INR', 'value': '2.8', 'unit': '',
                                          'reference_range': '2.5–3.5', 'flag': 'not_recorded', 'date': ''}
