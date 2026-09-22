"""Offline pilot readiness audit. It never starts an unbounded backfill."""
from datetime import datetime, timezone


def pilot_readiness(report: dict, plan: dict) -> dict:
    blockers = []
    if report['synthetic']:
        blockers.append('Synthetic data cannot qualify a real pilot')
    for name, status in report['gates'].items():
        if status != 'PASS':
            blockers.append(name)
    if report['counts']['sampled_launches'] < max(1000, plan['sample_size']):
        blockers.append('Insufficient real launches for the frozen 1000-launch sample')
    end = datetime.fromisoformat(plan['followup_through_utc'])
    if end > datetime.now(timezone.utc):
        blockers.append('Follow-up period has not elapsed')
    return {'plan_id': plan['plan_id'], 'dataset_version': report['dataset_version'],
            'status': 'BLOCKED' if blockers else 'READY', 'blockers': blockers,
            'bulk_download_started': False,
            'counts': report['counts'], 'gates': report['gates']}
