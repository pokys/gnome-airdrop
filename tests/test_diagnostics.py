import json
import unittest
from unittest.mock import patch
import diagnostics


class DiagnosticTests(unittest.TestCase):
    def test_export_excludes_paths_names_identifiers_and_raw_errors(self):
        sensitive='PRIVATE-SENTINEL'
        state={'installed':True,'state':'active','receiving':True,
            'download_dir':'/private/'+sensitive,'receipt':{'id':sensitive,'files':[sensitive]},
            'preferences':{'receiver_name':sensitive},
            'session':{'receiver_name':sensitive,'download_dir':sensitive,'duration_seconds':300},
            'transfer':{'id':sensitive,'filename':sensitive,'phase':'error','error':'timeout',
                'last_result':{'filename':sensitive,'download_dir':sensitive},'wire_bytes':1024,'bytes_per_second':20,'file_count':1},
            'log':sensitive,'addresses':[sensitive]}
        with patch('platform.release',return_value='6.12.4-private-machine'), \
             patch('platform.freedesktop_os_release',return_value={'ID':'fedora','VERSION_ID':'44','PRETTY_NAME':sensitive}):
            result=diagnostics.report(state)
        self.assertNotIn(sensitive,json.dumps(result))
        self.assertEqual(result['system']['kernel'],'6.12.4')
        self.assertEqual(result['transfer']['error'],'timeout')
        self.assertEqual(result['service']['duration_seconds'],300)

    def test_unknown_untrusted_values_are_not_echoed(self):
        result=diagnostics.report({'state':'PRIVATE','transfer':{
            'phase':'PRIVATE','error':'PRIVATE','file_count':True,
            'wire_bytes':-1,'bytes_per_second':float('inf')}})
        self.assertNotIn('PRIVATE',json.dumps(result))
        self.assertIsNone(result['transfer']['wire_bytes'])
        self.assertIsNone(result['transfer']['bytes_per_second'])
        self.assertIsNone(result['transfer']['file_count'])


if __name__=='__main__':unittest.main(verbosity=2)
