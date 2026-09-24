"""Bind decoded events to their exact, successfully executed instruction."""
import base64
from .cpi import instruction_trace, execution_evidence, committed
from .decoder import unbase58


class EventScope:
    def __init__(self, tx):
        if tx['meta']['err'] is not None:
            raise ValueError('FAILED_TRANSACTION')
        self.tx = tx
        self.nodes = instruction_trace(tx)
        self.parents = execution_evidence(self.nodes, tx['meta']['logMessages'])
        if any(committed(self.nodes, n['position']) is not True for n in self.nodes):
            raise ValueError('UNPROVEN_INSTRUCTION_EXECUTION')
        if any('Log truncated' in s for s in tx['meta']['logMessages']):
            raise ValueError('TRUNCATED_SCOPE_LOGS')

    def bind(self, event, decoder, wanted):
        log_index = event['event_index']
        node = self.nodes[self.parents[log_index]]
        if event['program'] != decoder.program or node['program'] != decoder.program:
            raise ValueError('EVENT_PROGRAM_DIFFERS')
        log = self.tx['meta']['logMessages'][log_index]
        name, payload = decoder.decode(base64.b64decode(log[14:], validate=True))
        if (name, payload) != (event['name'], event['payload']):
            raise ValueError('EVENT_LOG_PAYLOAD_DIFFERS')
        spec = decoder.instructions.get(unbase58(node['instruction']['data'])[:8])
        if not spec or spec['name'] not in wanted:
            raise ValueError('EVENT_INSTRUCTION_DIFFERS')
        if len(node['accounts']) < len(spec['accounts']):
            raise ValueError('MISSING_INSTRUCTION_ACCOUNTS')
        accounts = {a['name']:node['accounts'][i] for i,a in enumerate(spec['accounts'])}
        return node, accounts, spec

    def end(self, node):
        end = node['position']+1
        while end < len(self.nodes) and self.nodes[end]['depth'] > node['depth']:
            end += 1
        return end

    def descendants(self, node):
        return {(n['outer_index'],n['inner_index']) for n in self.nodes[node['position']+1:self.end(node)]}
