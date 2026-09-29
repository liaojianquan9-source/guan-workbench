import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_engine import AgentEngine, card_fingerprint, normalize_cards
from application import Application
from asset_store import AssetStore
from project_store import ProjectRepository, segments_from_input
from project_store import dumps
from provider import CodexProvider, ModelError, run_process


class ScriptedProvider:
    model = 'test-fixture-not-live-model'
    def __init__(self, actions=()): self.actions = iter(actions); self.prompts = []
    def status(self): return {'provider': 'test', 'model': self.model, 'available': True}
    def decide(self, prompt, images=(), cancel=None):
        self.prompts.append(prompt)
        value = next(self.actions)
        if isinstance(value, Exception): raise value
        return {'action': value[0], 'arguments': value[1], 'rationale': '测试中的受控动作，不作为真实模型证据。'}


class FakeRenderer:
    def __init__(self, root): self.root = Path(root); self.calls = []
    def render(self, style, fields, output_dir, duration=None):
        self.calls.append(copy.deepcopy(fields))
        p = self.root / f'render-{len(self.calls)}'; p.mkdir()
        (p/'v.mp4').write_bytes(b'test video'); (p/'p.jpg').write_bytes(b'test poster')
        return {'video': str(p/'v.mp4'), 'poster': str(p/'p.jpg'), 'report': {'status': 'passed', 'fields': fields,'layout':{'status':'passed','issues':[]}}}
    def compose(self, source, cards, output):
        Path(output).write_bytes(b'composed test')
        return {'video': str(output), 'report': {'status': 'passed'}}


class AgentDomainTests(unittest.TestCase):
    def test_default_effects_keep_previously_rendered_preview_fingerprint(self):
        card={'style':{'asset_id':'moon','revision':1},'fields':{'title':'复用'},'start':2,'end':5,'decision':'broll'}
        previous=hashlib.sha256(dumps(card).encode()).hexdigest()
        self.assertEqual(card_fingerprint(card),previous)
        self.assertNotEqual(card_fingerprint({**card,'crop_mode':'cover'}),previous)
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.assets = AssetStore(self.root/'assets')
        self.styles = [self.assets.create_asset('style', title, {'renderer_id': renderer, 'technical_status': 'passed'}, asset_id=identity)
                       for title, renderer, identity in [('月球标题', 'kimi-moon-v1', 'moon'), ('图片标题', 'problem-photo-v1', 'photo')]]
        self.renderer = FakeRenderer(self.root)
        self.app = Application(self.root/'projects', self.assets, ScriptedProvider(), self.renderer)
        self.p = self.app.create_project({'name': '真实合同测试', 'segments': [
            {'start': 0, 'end': 2, 'text': '我想和你谈谈今天的感受'},
            {'start': 2, 'end': 5, 'text': '这个项目终于可以反复复用'},
            {'start': 5, 'end': 8, 'text': '这里需要展示实际操作画面'}]})
        self.cards = [
            {'id':'c1','segment_ids':['s001'],'decision':'keep','reason':'开场第一人称感受需要保留表情','evidence':['transcript:s001'],'style':None,'fields':{},'alternatives':[],'missing':[]},
            {'id':'c2','segment_ids':['s002'],'decision':'broll','reason':'概念短标题可以强化复用这个观点','evidence':['transcript:s002','asset:moon@1'],
             'style':{'asset_id':'moon','revision':1},'fields':{'title':'复用','subtitle':'新项目','texture_text':'可编辑'},
             'alternatives':[{'style_id':'moon','reason':'单一概念标题适合'},{'style_id':'photo','reason':'缺少相关照片'}],'missing':[]},
            {'id':'c3','segment_ids':['s003'],'decision':'gap','reason':'现有样式不能代替真实操作证据','evidence':['transcript:s003'],'style':None,'fields':{},'alternatives':[],'missing':['实际操作录屏']}]
    def tearDown(self): self.temp.cleanup()
    def save_cards(self):
        cards = normalize_cards(self.cards, self.p, self.assets)
        self.p = self.app.repo.update(self.p['id'], self.p['revision'], lambda p:p.update(cards=cards))
        return self.p

    def test_agent_executes_inspection_search_history_render_then_finishes(self):
        provider = ScriptedProvider([('finish',{}), ('inspect_video',{}), ('search_assets',{'kind':'style','query':''}),
            ('inspect_style',{'asset_ids':['moon','photo']}), ('read_history',{}), ('propose_draft',{'cards':self.cards}),
            ('check_draft',{}), ('finish',{'summary':'已看过替换预览，仍保留用户审看'})])
        engine = AgentEngine(self.app.repo,self.assets,self.renderer,provider,self.app.preview)
        run = self.app.repo.create('run',{'project_id':self.p['id'],'status':'queued'})
        result = engine.execute(run['id'])
        self.assertEqual(result['status'],'awaiting_review')
        events=self.app.repo.events(run['id'])
        self.assertTrue(any(e['data'].get('error') for e in events if e['type']=='observation'))
        final=self.app.repo.get(self.p['id'])
        self.assertEqual([c['decision'] for c in final['cards']],['keep','broll','gap'])
        self.assertTrue(all(c['status']=='draft' for c in final['cards']))
        self.assertEqual(self.renderer.calls[0]['title'],'复用')
        self.assertEqual(final['cards'][1]['render_fingerprint'],card_fingerprint(final['cards'][1]))
        self.assertIn('reports',provider.prompts[-1])

    def test_failed_model_keeps_draft_and_can_resume_durable_trace(self):
        self.save_cards()
        run=self.app.repo.create('run',{'project_id':self.p['id'],'status':'queued'})
        engine=AgentEngine(self.app.repo,self.assets,self.renderer,ScriptedProvider([ModelError('模型离线')]),self.app.preview)
        self.assertEqual(engine.execute(run['id'])['status'],'failed')
        self.assertEqual(self.app.repo.get(self.p['id'])['cards'][1]['fields']['title'],'复用')
        reopened=ProjectRepository(self.root/'projects')
        self.assertTrue(reopened.get(run['id'])['events'])
        self.assertIn('模型离线',reopened.get(run['id'])['error'])

    def test_replacing_approved_content_invalidates_preview_and_approval(self):
        self.save_cards(); p=self.app.preview(self.p['id'],['c2'])
        p=self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2'],'action':'approve'})
        old_revision=p['revision']
        p=self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2'],'action':'replace','fields':{'title':'新版'}})
        c=p['cards'][1]; self.assertEqual(c['status'],'draft'); self.assertNotIn('preview_url',c)
        with self.assertRaises(ValueError): self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2'],'action':'approve'})
        with self.assertRaises(ValueError): self.app.batch(p['id'],{'revision':old_revision,'card_ids':['c2'],'action':'reject'})

    def test_timeline_edit_persists_and_invalidates_old_preview(self):
        self.save_cards()
        source=self.assets.create_asset('source','真实口播',{'media':{'duration':8}})
        p=self.app.repo.update(self.p['id'],self.app.repo.get(self.p['id'])['revision'],lambda v:v.update(source={'asset_id':source['id'],'revision':1}))
        old=copy.deepcopy(p['cards'][1]); old['preview_url']='/api/files/stale.mp4';old['render_fingerprint']='stale'
        def setup(v):
            v['cards'][1]=old
            v['cards'][2]['decision']='broll'
        p=self.app.repo.update(p['id'],p['revision'],setup)
        with self.assertRaisesRegex(ValueError,'重叠'):
            self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2'],'action':'retime','start':5.5,'end':8})
        with self.assertRaisesRegex(ValueError,'原视频范围'):
            self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2'],'action':'retime','start':7,'end':9})
        self.assertEqual(self.app.repo.get(p['id'])['revision'],p['revision'])
        p=self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2'],'action':'retime','start':2.3,'end':4.5})
        card=p['cards'][1]
        self.assertEqual((card['start'],card['end']),(2.3,4.5))
        self.assertTrue(card['timing_adjusted']);self.assertEqual(card['status'],'draft')
        self.assertNotIn('preview_url',card)
        with self.assertRaisesRegex(ValueError,'预览'):
            self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2'],'action':'approve'})
        old_fingerprint=card_fingerprint(card)
        p=self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2'],'action':'effect','crop_mode':'cover','transition':'dissolve'})
        card=p['cards'][1];self.assertNotEqual(card_fingerprint(card),old_fingerprint)
        self.assertEqual((card['crop_mode'],card['transition']),('cover','dissolve'))
        with self.assertRaisesRegex(ValueError,'未知画幅'):
            self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2'],'action':'effect','crop_mode':'../../x','transition':'cut'})

    def test_cover_crop_preview_is_visible_but_blocks_confirmation_when_most_text_is_cut(self):
        self.save_cards()
        style=self.assets.create_asset('style','横版标题',{'renderer_id':'kimi-moon-v1','technical_status':'passed','dimensions':[1280,720]})
        source=self.assets.create_asset('source','竖屏口播',{'media':{'duration':8,'width':1080,'height':1920}})
        p=self.app.repo.update(self.p['id'],self.app.repo.get(self.p['id'])['revision'],
            lambda v:v.update(source={'asset_id':source['id'],'revision':1}))
        p=self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2'],'action':'replace','style_id':style['id']})
        p=self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2'],'action':'effect',
            'crop_mode':'cover','transition':'cut'})
        with patch.object(self.app,'context_preview',return_value={'review_only':True}):
            p=self.app.preview(p['id'],['c2'])
        card=p['cards'][1]
        self.assertTrue(card['preview_url'])
        self.assertEqual(card['render_report']['layout']['status'],'needs_revision')
        self.assertIn('文字或主体可能被截断',card['render_report']['layout']['issues'][-1]['message'])
        with self.assertRaisesRegex(ValueError,'版式检查'):
            self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2'],'action':'approve'})

    def test_batch_is_atomic_and_unknown_field_or_gap_never_approved(self):
        self.save_cards(); p=self.app.preview(self.p['id'],['c2'])
        with self.assertRaises(ValueError): self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2','c3'],'action':'approve'})
        self.assertEqual(self.app.repo.get(p['id'])['cards'][1]['status'],'draft')
        with self.assertRaises(ValueError): self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2'],'action':'replace','fields':{'arbitrary_code':'x'}})

    def test_approved_cards_survive_agent_replanning_and_memory_is_scoped(self):
        self.save_cards(); p=self.app.preview(self.p['id'],['c2'])
        p=self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2'],'action':'approve'})
        changed=copy.deepcopy(self.cards); changed[1]['fields']['title']='模型试图改写'
        new=normalize_cards(changed,p,self.assets)
        self.assertEqual(new[1]['fields']['title'],'复用')
        self.assertEqual(new[1]['status'],'approved')
        memory=self.app.repo.memory()
        self.assertEqual(memory[0]['project_id'],p['id'])
        self.assertEqual(memory[0]['decisions'][0]['action'],'approve')

    def test_evidence_and_segment_contract_rejects_fabrication(self):
        with self.assertRaises(ValueError): normalize_cards(self.cards,self.p,self.assets,known_evidence=set(),observed_styles={'moon','photo'})
        with self.assertRaises(ValueError): normalize_cards(self.cards[:2],self.p,self.assets)
        invalid=copy.deepcopy(self.cards); invalid[1]['style']['revision']=999
        with self.assertRaises(KeyError): normalize_cards(invalid,self.p,self.assets)
        invalid=copy.deepcopy(self.cards); invalid[1]['fields']['title']='字'*30
        with self.assertRaises(ValueError): normalize_cards(invalid,self.p,self.assets)

    def test_inspecting_only_one_candidate_cannot_bypass_comparison(self):
        evidence={'transcript:s001','transcript:s002','transcript:s003','asset:moon@1'}
        with self.assertRaises(ValueError): normalize_cards(self.cards,self.p,self.assets,known_evidence=evidence,observed_styles={'moon':1})
        with self.assertRaises(ValueError): normalize_cards(self.cards,self.p,self.assets,known_evidence=evidence,observed_styles={'moon':2,'photo':1})

    def test_workbench_import_accepts_other_products_provenance_shape(self):
        from unittest.mock import patch
        self.assets.create_asset('source','其他产品的参考',{'provenance':'已有相对路径'})
        image=self.root/'input';image.write_bytes(b'fake')
        source=self.assets.create_asset('source','source',{'media':{'duration':8}})
        with patch('application.read_workbench',return_value=({'name':'口播.mov','transcript':{'segments':self.p['segments']}},image)), patch.object(self.app,'ingest',return_value=source):
            p=self.app.import_workbench('validated-by-adapter')
        self.assertEqual(len(p['segments']),3)

    def test_estimated_timing_is_explicit_and_invalid_ranges_rejected(self):
        self.assertTrue(segments_from_input(transcript='第一句。第二句。')[0]['estimated'])
        for segments in [[{'start':0,'end':float('nan'),'text':'x'}],[{'start':-1,'end':1,'text':'x'}],
                         [{'start':0,'end':2,'text':'x'},{'start':1,'end':3,'text':'y'}]]:
            with self.assertRaises(ValueError): segments_from_input(segments)

    def test_unapproved_or_estimated_card_cannot_enter_final_render(self):
        from unittest.mock import patch
        self.save_cards()
        with self.assertRaises(ValueError): self.app.compose(self.p['id'])
        blob_file=self.root/'source';blob_file.write_bytes(b'source')
        source=self.assets.create_asset('source','source',{},self.assets.put_blob(blob_file)['sha256'])
        p=self.app.repo.get(self.p['id'])
        p=self.app.repo.update(p['id'],p['revision'],lambda v:v.update(source={'asset_id':source['id'],'revision':1}))
        with self.assertRaises(ValueError): self.app.compose(p['id'])
        with patch.object(self.app,'context_preview',return_value={'review_only':True}): p=self.app.preview(p['id'],['c2'])
        p=self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2'],'action':'approve'})
        self.app.repo.update(p['id'],p['revision'],lambda v:v['segments'][1].update(estimated=True))
        with self.assertRaises(ValueError): self.app.compose(p['id'])

    def test_interrupted_jobs_recover_without_losing_outputs(self):
        r=self.app.repo.create('run',{'status':'running','project_id':self.p['id']})
        self.app.repo.event(r['id'],'observation','已有检索结果',{'tool':'search_assets'})
        self.app.repo.recover()
        self.assertEqual(self.app.repo.get(r['id'])['status'],'interrupted')
        self.assertEqual(len(self.app.repo.get(r['id'])['events']),1)

    def test_process_timeout_is_bounded(self):
        with self.assertRaises(TimeoutError): run_process([sys.executable,'-c','import time;time.sleep(5)'],timeout=.2)

    def test_acceptance_test_approval_is_not_learned_as_user_taste(self):
        self.save_cards();p=self.app.preview(self.p['id'],['c2'])
        self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2'],'action':'approve','reviewer':'acceptance-test'})
        self.assertEqual(self.app.repo.memory(),[])

    def test_layout_revision_gate_blocks_approval_even_when_video_decodes(self):
        self.save_cards();p=self.app.preview(self.p['id'],['c2'])
        p=self.app.repo.update(p['id'],p['revision'],lambda v:v['cards'][1]['render_report'].update(layout={'status':'needs_revision','issues':[{'field':'subtitle'}]}))
        with self.assertRaises(ValueError):self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2'],'action':'approve'})

    def test_duplicate_pins_same_assets_but_does_not_inherit_approval_or_previews(self):
        self.save_cards();p=self.app.preview(self.p['id'],['c2'])
        p=self.app.batch(p['id'],{'revision':p['revision'],'card_ids':['c2'],'action':'approve'})
        duplicate=self.app.duplicate(p['id'],'另一个真实项目')
        self.assertNotEqual(duplicate['id'],p['id'])
        self.assertEqual(duplicate['cards'][1]['style'],p['cards'][1]['style'])
        self.assertNotIn('preview_url',duplicate['cards'][1]);self.assertEqual(duplicate['cards'][1]['status'],'draft')


if __name__=='__main__': unittest.main()
