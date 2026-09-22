"""Instruction-first launch audit. Internal agreement never proves a full census."""
import json
import subprocess
from collections import Counter
from pathlib import Path

from solders.pubkey import Pubkey

from .cpi import EVENT_IX_TAG, committed, execution_evidence, instruction_trace
from .decoder import IDLDecoder, PUMP, Reader, decode_block, unbase58
from .domain import IntegrityError
from .pipeline import load_manifest
from .storage import immutable_write, json_bytes

OPTIONAL_CREATE_FIELDS = {'is_cashback_enabled', 'creator_fee_bps', 'is_holder_reward'}


def create_arguments(raw, spec, decoder):
    """Preserve EOF omissions as unknown, never apply today's defaults to history."""
    reader = Reader(raw[8:], decoder.types)
    args, omitted = {}, []
    for field in spec['args']:
        name = field['name']
        if reader.pos == len(reader.data) and name in OPTIONAL_CREATE_FIELDS:
            omitted.append(name)
            continue
        value = reader.read(field['type'])
        # Pump's EOF-tolerant wrappers are one-field tuple structs, not Option<T>.
        args[name] = value[0] if name in OPTIONAL_CREATE_FIELDS else value
    if reader.pos != len(reader.data):
        raise IntegrityError('Unknown trailing instruction bytes')
    return args, omitted


def holder_creator(mint):
    address, _ = Pubkey.find_program_address(
        [b'holder-rewards', bytes(Pubkey.from_string(mint))], Pubkey.from_string(PUMP))
    return str(address)


def audit_block(block, slot, raw_hash, decoder):
    decoded, _ = decode_block(block, slot, raw_hash, {PUMP:decoder})
    records, issues, inventory = [], [], Counter()
    for tx_index, tx in enumerate(block['transactions']):
        meta = tx.get('meta')
        if not meta or meta.get('err') is not None:
            continue
        sig = tx['transaction']['signatures'][0]
        message = tx['transaction']['message']
        keys = [k['pubkey'] if isinstance(k,dict) else k for k in message['accountKeys']]
        loaded = meta.get('loadedAddresses') or {}
        keys += loaded.get('writable',[]) + loaded.get('readonly',[])
        if PUMP not in keys:
            continue
        tx_events = [r for r in decoded if r['tx_index']==tx_index and r['name']=='CreateEvent']
        evidence = {'slot':slot,'signature':sig,'raw_sha256':raw_hash}
        try:
            nodes = instruction_trace(tx)
            creates = []
            for n in nodes:
                if n['program'] != PUMP:
                    continue
                raw = unbase58(n['instruction']['data'])
                spec = decoder.instructions.get(raw[:8])
                name = spec['name'] if spec else ('event_cpi' if raw.startswith(EVENT_IX_TAG) else 'UNKNOWN')
                inventory[name] += 1
                if name == 'UNKNOWN':
                    issues.append({**evidence,'reason':'UNKNOWN_PUMP_INSTRUCTION','discriminator':raw[:8].hex()})
                if name.startswith('create') and name not in {'create','create_v2'}:
                    issues.append({**evidence,'reason':'UNSUPPORTED_CREATE_VARIANT','instruction':name})
                if name in {'create','create_v2'}:
                    creates.append((n,raw,spec))
            if not creates and not tx_events:
                continue
            parents = execution_evidence(nodes, meta.get('logMessages') or [])
        except (ValueError,KeyError,IndexError,TypeError) as exc:
            issues.append({**evidence,'reason':'CENSUS_TRACE_UNPROVEN','detail':str(exc)})
            continue
        matched = set()
        for n,raw,spec in creates:
            path = [n['outer_index'],n['inner_index']]
            state = committed(nodes,n['position'])
            if state is False:
                inventory['rolled_back_create'] += 1
                continue
            record = {**evidence,'tx_index':tx_index,'instruction_path':path,
                      'instruction':spec['name'],'decoder_hash':decoder.hash,
                      'execution_status':'CONFIRMED' if state is True else 'UNPROVEN',
                      'historical_program_version':'UNVALIDATED','status':'FAIL'}
            records.append(record)
            try:
                args, omitted = create_arguments(raw,spec,decoder)
                accounts = {a['name']:n['accounts'][i] for i,a in enumerate(spec['accounts'])}
                record.update(mint=accounts['mint'],input_creator=args['creator'],arguments=args,
                              omitted_arguments=omitted)
                for a in spec['accounts']:
                    if a.get('address') and accounts[a['name']] != a['address']:
                        raise IntegrityError('Fixed instruction account mismatch: '+a['name'])
                candidates = [r for r in tx_events if parents.get(r['event_index'])==n['position']]
                if len(candidates)!=1:
                    raise IntegrityError('Expected exactly one CreateEvent in the create invocation')
                event = candidates[0]; matched.add(event['event_index']); p=event['payload']
                if p.get('_missing_trailing_fields'):
                    raise IntegrityError('Unversioned legacy CreateEvent')
                expected = {k:accounts[k] for k in ('mint','bonding_curve','user','token_program')}
                expected.update({k:args[k] for k in ('name','symbol','uri')})
                for k in ('is_mayhem_mode','is_cashback_enabled','is_holder_reward'):
                    if k in args: expected[k]=args[k]
                reward = p.get('is_holder_reward')
                expected['creator'] = holder_creator(accounts['mint']) if reward is True else args['creator']
                different = [k for k,v in expected.items() if p.get(k)!=v]
                if different:
                    raise IntegrityError('Create instruction/event mismatch: '+','.join(different))
                if state is not True:
                    raise IntegrityError('Create execution is unproven')
                record.update(status='PASS',event_index=event['event_index'],event_creator=p['creator'],
                              creator_role='holder_rewards_pda' if reward else 'creator',
                              regime_observed={k:p[k] for k in ('is_mayhem_mode','is_cashback_enabled',
                                               'is_holder_reward','token_program','quote_mint','creator_fee_bps')})
            except (ValueError,KeyError,IndexError,TypeError) as exc:
                issues.append({**evidence,'instruction_path':path,'reason':'CREATE_RECONCILIATION_FAILED','detail':str(exc)})
        for event in tx_events:
            if event['event_index'] not in matched:
                issues.append({**evidence,'reason':'ORPHAN_CREATE_EVENT','event_index':event['event_index']})
    return records, issues, dict(inventory)


def audit_manifests(paths, raw_root, vendor):
    decoder = IDLDecoder(vendor/'pump.json')
    records, issues, inventory, provenance, seen = [], [], Counter(), [], set()
    for path in paths:
        # Reuse the normal integrity checks on hashes, finalized provenance and enumeration.
        _, info, _, decode_issues = load_manifest(path, raw_root, vendor)
        manifest = json.loads(path.read_text())
        provenance.append(info)
        if not info['enumeration_complete']:
            issues.append({'reason':'INCOMPLETE_BLOCK_ENUMERATION','manifest':str(path)})
        for b in manifest['blocks']:
            if b['slot'] in seen:
                raise IntegrityError('Overlapping manifest slots would duplicate the census')
            seen.add(b['slot'])
            h=b['raw_sha256']
            block=json.loads((raw_root/'objects'/h[:2]/f'{h}.json').read_text())['result']
            rows, errors, counts = audit_block(block,b['slot'],h,decoder)
            records.extend(rows); issues.extend(errors); inventory.update(counts)
        info['pipeline_issue_counts']=dict(Counter(i['reason'] for i in decode_issues))
    mints=Counter(r.get('mint') for r in records if r['status']=='PASS')
    for mint,count in mints.items():
        if count>1:issues.append({'reason':'DUPLICATE_LAUNCH_MINT','mint':mint,'count':count})
    git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip())
    return {'experiment_id':'MEME-EXP-000','audit':'launch_census_and_regimes','git_commit':git_commit,
            'code_dirty':dirty,'status':'FAIL','continue_to_exp001':False,
            'gates':{'local_create_instruction_event_agreement':'PASS' if records and not issues else 'FAIL',
                     'independent_launch_census':'UNPROVEN','full_pilot_day_population':'UNPROVEN',
                     'historical_program_binary_idl_mapping':'UNPROVEN'},
            'counts':{'blocks':len(seen),'create_instructions':len(records),
                      'matched_creates':sum(r['status']=='PASS' for r in records),'issues':len(issues)},
            'instruction_inventory':dict(inventory),'provenance':provenance,'launches':records,'issues':issues,
            'warning':'Same-response instruction/log agreement is not an independent census. Observed regime flags are not deployment evidence.'}


def save_audit(report, out):
    immutable_write(out,json_bytes(report))
