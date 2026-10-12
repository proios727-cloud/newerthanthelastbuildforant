import io,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from credentials import load_odds_key,probe_odds_access

class CredentialsTests(unittest.TestCase):
    def setUp(self):
        self.patch=patch.dict(os.environ,{},clear=True);self.patch.start()
    def tearDown(self): self.patch.stop()
    def file(self,text):
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup);p=Path(d.name)/'.env';p.write_text(text);return p
    def test_literal_key_only_other_settings_not_imported(self):
        self.assertEqual(load_odds_key(self.file('ODDS_API_KEY="test_key_1234" # sample\nDATABASE_URL=secret\n')), 'specified_environment_file')
        self.assertEqual(os.environ['ODDS_API_KEY'],'test_key_1234');self.assertNotIn('DATABASE_URL',os.environ)
    def test_alias_and_existing_precedence(self):
        load_odds_key(self.file("export THE_ODDS_API_KEY='test_key_1234'\n"))
        self.assertEqual(load_odds_key('/does/not/exist'),'process_environment')
    def test_no_evaluation_or_conflicting_keys(self):
        for text in ('ODDS_API_KEY=${OTHER}', 'ODDS_API_KEY=$(cat secret)', 'ODDS_API_KEY=test_key_1234\nTHE_ODDS_API_KEY=other_key_5678'):
            with self.assertRaises(ValueError):load_odds_key(self.file(text))
            self.assertNotIn('ODDS_API_KEY',os.environ)
    def test_read_only_probe_and_quota(self):
        os.environ['ODDS_API_KEY']='test_key_1234'
        class Response(io.BytesIO):
            headers={'x-requests-remaining':'500','x-requests-used':'0'}
        def opener(request,timeout):
            self.assertIn('/v4/sports?',request.full_url);self.assertEqual(request.get_method(),'GET')
            return Response(json.dumps([{'key':'americanfootball_nfl'}]).encode())
        r=probe_odds_access(opener);self.assertTrue(r['connected']);self.assertNotIn('test_key_1234',str(r));self.assertFalse(r['trading_enabled'])
    def test_failure_never_echoes_secret(self):
        os.environ['ODDS_API_KEY']='test_key_1234'
        def fail(*a,**k):raise RuntimeError('secret test_key_1234 query URL')
        r=probe_odds_access(fail);self.assertFalse(r['connected']);self.assertNotIn('test_key_1234',str(r))
if __name__=='__main__':unittest.main()
