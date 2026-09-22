import http.client
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock

from meme_quant.buffer_replay import BufferReplay,history_rows,read_hashed
from meme_quant.decoder import ZERO,unbase58
from meme_quant.domain import IntegrityError
from meme_quant.regimes import LOADER
from meme_quant.rpc import RPC,read_response
from meme_quant.storage import store_raw,json_bytes

class UploadReplay(unittest.TestCase):
    def setUp(self):
        self.r=BufferReplay('buffer','program','programdata')
        self.payload=b'\x7fELFtest-binary-data'
        raw=bytes(4)+(100).to_bytes(8,'little')+(len(self.payload)+37).to_bytes(8,'little')+unbase58(LOADER)
        self.alloc=raw
        self.r.apply(ZERO,['payer','buffer'],raw)
        self.r.apply(LOADER,['buffer','authority'],bytes(4))

    def write(self,offset,payload):
        return (1).to_bytes(4,'little')+offset.to_bytes(4,'little')+len(payload).to_bytes(8,'little')+payload

    def upgrade(self):
        self.r.apply(LOADER,['programdata','program','buffer','spill','rent','clock','authority'],(3).to_bytes(4,'little'))

    def test_exact_bytes_recovered_from_out_of_offset_order_chunks(self):
        for offset,payload in [(8,self.payload[8:]),(0,self.payload[:8])]:
            self.r.apply(LOADER,['buffer','authority'],self.write(offset,payload))
        self.upgrade()
        self.assertEqual(self.r.finish(),self.payload)
        self.assertTrue(self.r.upgraded)

    def test_hole_blocks_upgrade(self):
        self.r.apply(LOADER,['buffer','authority'],self.write(0,self.payload[:-1]))
        with self.assertRaisesRegex(IntegrityError,'coverage'):self.upgrade()

    def test_later_writes_replace_previous_bytes(self):
        self.r.apply(LOADER,['buffer','authority'],self.write(0,self.payload))
        self.r.apply(LOADER,['buffer','authority'],self.write(4,b'EDIT'))
        self.upgrade();self.assertEqual(self.r.finish(),self.payload[:4]+b'EDIT'+self.payload[8:])
        self.assertEqual(self.r.overwritten_bytes,4)

    def test_out_of_bounds_write_rejected(self):
        with self.assertRaises(IntegrityError):self.r.apply(LOADER,['buffer','authority'],self.write(5,self.payload))

    def test_wrong_write_authority_rejected(self):
        with self.assertRaises(IntegrityError):self.r.apply(LOADER,['buffer','wrong'],self.write(0,self.payload))

    def test_bad_declared_write_size_rejected(self):
        with self.assertRaises(IntegrityError):self.r.apply(LOADER,['buffer','authority'],self.write(0,self.payload)+b'x')

    def test_account_reuse_rejected(self):
        with self.assertRaises(IntegrityError):self.r.apply(ZERO,['payer','buffer'],self.alloc)

    def test_wrong_upgrade_target_rejected(self):
        self.r.apply(LOADER,['buffer','authority'],self.write(0,self.payload))
        with self.assertRaises(IntegrityError):
            self.r.apply(LOADER,['wrong','program','buffer','spill','rent','clock','authority'],(3).to_bytes(4,'little'))

    def test_authority_transition_preserved(self):
        self.r.apply(LOADER,['buffer','authority','new'],(4).to_bytes(4,'little'))
        with self.assertRaises(IntegrityError):self.r.apply(LOADER,['buffer','authority'],self.write(0,self.payload))
        self.r.apply(LOADER,['buffer','new'],self.write(0,self.payload))
        self.r.apply(LOADER,['programdata','program','buffer','spill','rent','clock','new'],(3).to_bytes(4,'little'))
        self.assertTrue(self.r.upgraded)

    def test_write_after_upgrade_rejected(self):
        self.r.apply(LOADER,['buffer','authority'],self.write(0,self.payload));self.upgrade()
        with self.assertRaises(IntegrityError):self.r.apply(LOADER,['buffer','authority'],self.write(0,self.payload))

    def test_non_elf_bytes_not_promoted(self):
        self.r.apply(LOADER,['buffer','authority'],self.write(0,b'x'*len(self.payload)))
        with self.assertRaisesRegex(IntegrityError,'ELF'):self.upgrade()

    def test_missing_allocation_or_initialization_rejected(self):
        r=BufferReplay('buffer','program','programdata')
        with self.assertRaises(IntegrityError):r.apply(LOADER,['buffer','authority'],self.write(0,self.payload))
        r.apply(ZERO,['payer','buffer'],self.alloc)
        with self.assertRaises(IntegrityError):r.apply(LOADER,['buffer','authority'],self.write(0,self.payload))


class HistoryIntegrity(unittest.TestCase):
    def page(self,root,rows,limit=2,before=None):
        h,_=store_raw(root,json_bytes({'result':rows}));options={'limit':limit,'commitment':'finalized'}
        if before is not None:options['before']=before
        return {'method':'getSignaturesForAddress','params':['buffer',options],'raw_sha256':h}

    def rows(self):return [{'slot':3,'signature':'a','confirmationStatus':'finalized'},{'slot':2,'signature':'b','confirmationStatus':'finalized'}]

    def test_exhausted_contiguous_pages_required(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p=self.page(root,self.rows());tail=self.page(root,[],before='b')
            self.assertEqual(len(history_rows([p,tail],root,'buffer')),2)
            with self.assertRaises(IntegrityError):history_rows([p],root,'buffer')
            tail['params'][1]['before']='a'
            with self.assertRaises(IntegrityError):history_rows([p,tail],root,'buffer')

    def test_duplicate_or_unfinalized_history_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for rows in [[self.rows()[0]]*2,[{**self.rows()[0],'confirmationStatus':'confirmed'}]]:
                p=self.page(root,rows,limit=3)
                with self.assertRaises(IntegrityError):history_rows([p],root,'buffer')

    def test_corrupt_raw_payload_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);p=self.page(root,self.rows(),limit=3);h=p['raw_sha256']
            (root/'objects'/h[:2]/f'{h}.json').write_text('{}')
            with self.assertRaisesRegex(IntegrityError,'SHA256'):read_hashed(root,h)

    def test_partial_http_response_is_retried_without_becoming_raw_data(self):
        broken=MagicMock();broken.__enter__.return_value.read1.side_effect=http.client.IncompleteRead(b'partial',10)
        good=MagicMock();good.__enter__.return_value.read1.side_effect=[b'{"result":42}',b''];good.__enter__.return_value.headers.get.return_value=None
        with patch('urllib.request.urlopen',side_effect=[broken,good]) as call,patch('time.sleep'):
            envelope,raw=RPC('https://example.invalid',attempts=2).call('getSlot',[])
        self.assertEqual(envelope,{'result':42});self.assertEqual(call.call_count,2)
        self.assertEqual(raw,b'{"result":42}')

    def test_trickling_body_cannot_reset_request_deadline(self):
        response=MagicMock();response.read1.return_value=b'x'
        with patch('time.monotonic',side_effect=[1,6]),self.assertRaises(TimeoutError):
            read_response(response,5)

    def test_premature_eof_fails_content_length_check(self):
        response=MagicMock();response.read1.side_effect=[b'part',b'']
        response.headers.get.return_value='10'
        with self.assertRaises(http.client.IncompleteRead):
            read_response(response,float('inf'))

if __name__=='__main__':unittest.main()
