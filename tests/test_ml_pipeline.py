import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml_pipeline import pipeline as p
from model.probability import (DelayProbability, InsufficientProbabilityData, event_target,
                               fit_probability, validate_bundle)


class LabelTests(unittest.TestCase):
    def setUp(self):
        self.schedule = pd.DataFrame({
            'tr_id':[1,1,1], 'tt_action_item_id':[10,11,12],
            'time_begin':['2026-01-01 12:00','2026-01-01 12:12','2026-01-01 12:14'],
            'time_fact_begin':['2026-01-01 12:05','2026-01-01 12:15','2026-01-01 12:16']})
        self.labels = pd.DataFrame({'sample_id':['a'], 'tr_id':[1], 'T':['2026-01-01 12:00'],
            'target_stop_id':[11], 'target_time_begin':['2026-01-01 12:12'], 'target_delay_s':[180], 'cur_dev_s':[0]})

    def test_arrival_not_plan_and_T(self):
        for cutoff, count in [('12:12',0), ('12:14',0), ('12:15',1)]:
            labels, _ = p.available_labels(self.labels,self.schedule,pd.Timestamp('2026-01-01 '+cutoff))
            self.assertEqual(len(labels),count)
        self.labels['T']='2026-01-01 12:20'
        self.assertTrue(p.available_labels(self.labels,self.schedule,pd.Timestamp('2026-01-01 12:16'))[0].empty)

    def test_invalid_unmatched_and_ambiguous(self):
        schedule=pd.concat([self.schedule,self.schedule.iloc[[1]]])
        labels, report=p.available_labels(self.labels,schedule,pd.Timestamp('2026-01-02'))
        self.assertTrue(labels.empty)
        self.assertEqual(report['ambiguous'],1)
        self.labels['target_stop_id']=99
        self.assertEqual(p.available_labels(self.labels,self.schedule,pd.Timestamp('2026-01-02'))[1]['unmatched'],1)
        self.labels['T']='invalid'
        self.assertEqual(p.available_labels(self.labels,self.schedule,pd.Timestamp('2026-01-02'))[1]['invalid'],1)

    def test_causal_generation_uses_full_plan_and_known_departures(self):
        s=self.schedule.copy()
        s['time_begin']=pd.to_datetime(s.time_begin)
        s['time_fact_begin']=pd.to_datetime(s.time_fact_begin)
        cutoff=pd.Timestamp('2026-01-01 12:16')
        generated=p.generate_causal_points({1:s},cutoff)
        row=generated[generated['T']==pd.Timestamp('2026-01-01 12:00')].iloc[0]
        self.assertEqual(row.target_stop_id,11)
        self.assertEqual(row.cur_dev_s,0) # 12:00 stop is not yet actually passed
        self.assertEqual(row.target_delay_s,180)
        s.loc[1,'time_fact_begin']=pd.NaT
        generated=p.generate_causal_points({1:s},cutoff)
        # Must not silently select the second planned target when the first lacks a fact.
        self.assertTrue(generated[generated['T']==pd.Timestamp('2026-01-01 12:00')].empty)


    def test_generated_points_exclude_ambiguous_facts(self):
        s=self.schedule.copy()
        s['time_begin']=pd.to_datetime(s.time_begin)
        s['time_fact_begin']=pd.to_datetime(s.time_fact_begin)
        s=pd.concat([s,s.iloc[[1]]]).sort_values('time_begin').reset_index(drop=True)
        generated=p.generate_causal_points({1:s},pd.Timestamp('2026-01-02'))
        self.assertFalse((generated.target_stop_id==11).any())


class ProbabilityTests(unittest.TestCase):
    def test_threshold_and_insufficient_data(self):
        np.testing.assert_array_equal(event_target([-1,120,121]),[0,0,1])
        with self.assertRaises(InsufficientProbabilityData):
            fit_probability(pd.DataFrame({'x':[1,2]}),[0,121],[1,1],[True,True])

    def test_grouped_fit_roundtrip_and_legacy(self):
        X=pd.DataFrame({'x':np.tile(np.arange(12),4).astype(float)})
        y=np.tile([0,0,0,0,0,0,180,180,180,180,180,180],4)
        groups=np.repeat(np.arange(4),12)
        mask=np.tile([True]*10+[False]*2,4)
        prob=fit_probability(X,y,groups,mask,params={'min_data_in_leaf':2,'num_leaves':3,'num_threads':1},rounds=4)
        values=prob.predict(X)
        self.assertTrue(np.isfinite(values).all())
        self.assertTrue(((values>=0)&(values<=1)).all())
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(DelayProbability.load(d))
            prob.save(d)
            np.testing.assert_allclose(values,DelayProbability.load(d).predict(X))
            Path(d,'calibrator.json').unlink()
            with self.assertRaises(FileNotFoundError): DelayProbability.load(d)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.models=self.root/'models';self.work=self.root/'candidate';self.work.mkdir()
        self.default=self.root/'bundled';self.default.mkdir()
        X=pd.DataFrame({'x':np.arange(40,dtype=float)})
        model=lgb.train({'objective':'regression','verbose':-1,'num_threads':1,'min_data_in_leaf':2},lgb.Dataset(X,label=np.arange(40)),num_boost_round=2)
        model.save_model(str(self.default/'model.txt'))
        model.save_model(str(self.work/'model.txt'))
        probability=fit_probability(X,np.tile([0,180],20),np.repeat(np.arange(4),10),np.ones(40,bool),params={'num_threads':1,'min_data_in_leaf':2},rounds=2)
        probability.save(self.work)
        self.patch=patch.multiple(p,ARTIFACTS=self.models,DEFAULT_MODEL=self.default/'model.txt')
        self.patch.start();self.addCleanup(self.patch.stop)
        self.identity=p.reference_identity(self.models,self.default/'model.txt')[1]

    def report(self,eligible=True):
        p.write_json(self.work/'evaluation.json',{'eligible':eligible,'reference':self.identity,'candidate_mae':1,'reference_mae':2})

    def test_publish_bundle_and_rollback(self):
        self.report()
        self.assertTrue(p.publish(str(self.work)))
        meta=json.loads((self.models/'active.json').read_text())
        self.assertEqual(meta['bundle_version'],2)
        validate_bundle(self.models/meta['version'],required=True)
        from ml_pipeline.rollback import main
        with patch.dict('os.environ',{'MODEL_DIR':str(self.models)}), patch('sys.argv',['rollback','candidate']):main()
        self.assertEqual(json.loads((self.models/'active.json').read_text())['version'],'candidate')

    def test_rejection_and_incomplete(self):
        self.report(False)
        self.assertFalse(p.publish(str(self.work)))
        self.assertFalse((self.models/'active.json').exists())
        self.report()
        (self.work/'calibrator.json').unlink()
        with self.assertRaises(FileNotFoundError):p.publish(str(self.work))
        self.assertFalse((self.models/'active.json').exists())

    def test_changed_reference_re_evaluated(self):
        self.report()
        metrics=json.loads((self.work/'evaluation.json').read_text())
        metrics['reference']['fingerprint']='stale'
        p.write_json(self.work/'evaluation.json',metrics)
        def rescore(path): self.report(False);return path
        with patch.object(p,'evaluate',side_effect=rescore) as evaluate:
            self.assertFalse(p.publish(str(self.work)))
            evaluate.assert_called_once()

    def test_evaluation_compares_actual_bundled_and_rejects_equal(self):
        p.write_json(self.work/'training.json',{'status':'ready'})
        pd.DataFrame({'target_delay_s':[0,200]}).to_csv(self.work/'test-labels.csv',index=False)
        X=pd.DataFrame({'x':[0.,1.],'cur_dev_s':[0.,0.]})
        with patch.object(p.ml,'load_schedule',return_value={}), patch.object(p.ml,'load_traffic',return_value={}), patch.object(p.ml,'build',return_value=X):
            p.evaluate(str(self.work))
        report=json.loads((self.work/'evaluation.json').read_text())
        self.assertEqual(report['reference']['version'],'bundled')
        self.assertEqual(report['candidate_mae'],report['reference_mae'])
        self.assertFalse(report['eligible'])

    def test_probability_regression_and_nonfinite_gate(self):
        import shutil
        for name in ['classifier.txt','calibrator.json']:
            shutil.copyfile(self.work/name,self.default/name)
        p.write_json(self.work/'training.json',{'status':'ready'})
        pd.DataFrame({'target_delay_s':[0,200]}).to_csv(self.work/'test-labels.csv',index=False)
        X=pd.DataFrame({'x':[0.,1.],'cur_dev_s':[0.,0.]})
        with patch.object(p.ml,'load_schedule',return_value={}), patch.object(p.ml,'load_traffic',return_value={}), patch.object(p.ml,'build',return_value=X):
            with patch.object(p.ml,'predict',side_effect=[np.array([0.,200.]),np.array([20.,180.])]), patch.object(p,'probability_metrics',side_effect=[{'brier':.4,'log_loss':1.},{'brier':.1,'log_loss':.3}]):
                p.evaluate(str(self.work))
            report=json.loads((self.work/'evaluation.json').read_text())
            self.assertFalse(report['eligible'])
            self.assertLess(report['candidate_mae'],report['reference_mae'])
            with patch.object(p.ml,'predict',side_effect=[np.array([np.nan,200.]),np.array([20.,180.])]):
                p.evaluate(str(self.work))
            self.assertFalse(json.loads((self.work/'evaluation.json').read_text())['eligible'])

    def test_rollback_rejects_incomplete_bundle_without_changing_pointer(self):
        self.report();p.publish(str(self.work))
        previous=(self.models/'active.json').read_bytes()
        (self.models/'candidate'/'calibrator.json').unlink()
        from ml_pipeline.rollback import main
        with patch.dict('os.environ',{'MODEL_DIR':str(self.models)}), patch('sys.argv',['rollback','candidate']):
            with self.assertRaises(FileNotFoundError):main()
        self.assertEqual(previous,(self.models/'active.json').read_bytes())


if __name__=='__main__': unittest.main()
