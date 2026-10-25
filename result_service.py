"""Exact chart lookup for the team's demo; no model or network is required."""
from functools import lru_cache
import json
import math
from pathlib import Path


DATA = Path(__file__).resolve().parent / 'data'


@lru_cache(maxsize=2)
def read_data(filename):
    return json.loads((DATA / filename).read_text(encoding='utf-8'))


def build_result(context):
    chart_no = context.get('chart_no')
    legal_status = 'not_in_provided_pdf'
    try:
        entry = read_data('legal_references_by_chart.json')['by_chart'].get(chart_no, {})
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        entry, legal_status = {}, 'unavailable'
    try:
        case = next((item for item in read_data('accident_cases.json')
                     if item['chart_no'] == chart_no), {})
    except (OSError, ValueError, KeyError, TypeError):
        case = {}
    ratio = validated_ratio(case.get('fault_ratio', {}))
    return {
        'session_id': context['session_id'],
        'revision': context['revision'],
        'chart_no': chart_no,
        'accident_type': entry.get('accident_type') or case.get('accident_type', ''),
        'summary': context.get('search_summary', ''),
        'laws': entry.get('laws', []),
        'precedents': entry.get('precedents', []),
        'law_status': entry.get('law_status', legal_status),
        'precedent_status': entry.get('precedent_status', legal_status),
        'fault': {
            'status': 'found' if ratio else 'unavailable',
            'basis': 'stored_knia',
            'ratio': ratio,
            'explanation': case.get('basic_fault_explanation', ''),
            'accident_situation': case.get('accident_situation', ''),
            'application_criteria': case.get('application_criteria', ''),
            'source_url': case.get('url', ''),
            'source_label': '손해보험협회 저장 자료',
        },
    }


def validated_ratio(raw):
    try:
        if any(isinstance(raw[key], bool) for key in ('A', 'B')):
            return None
        a, b = (float(raw[key]) for key in ('A', 'B'))
        if not all(math.isfinite(v) and 0 <= v <= 100 for v in (a, b)) or a + b != 100:
            return None
        return {'A': a, 'B': b}
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
