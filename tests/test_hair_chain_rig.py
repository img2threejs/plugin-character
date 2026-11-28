import unittest
import numpy as np
from tools.hair_chain_rig import weld_seams, classify_front_locks, chain_layout, hair_weights, validate_binding


class RigTests(unittest.TestCase):
    def test_weights_and_seams(self):
        p = np.array([[0,0,1],[0,0,.9],[0,0,.8],[0,0,.9]])
        unique,inv = weld_seams(p)
        names,w = hair_weights(unique,inv,np.zeros(len(unique),int),[1,0,-1],[[.85,.75]]*3,{-1:[.85],1:[.85]},[.7,1],[1,1],1,.1)
        np.testing.assert_allclose(w.sum(axis=1),1)
        np.testing.assert_allclose(w[1],w[3])
        self.assertLessEqual((w>0).sum(axis=1).max(),4)
        self.assertEqual(names[0],'Head')
        self.assertEqual(validate_binding(p,w,1)['roots'],1)

    def test_validator_counterexamples(self):
        p = np.array([[0,0,1],[0,0,.8],[0,0,.8]])
        good = np.array([[1,0,0,0,0],[0,1,0,0,0],[0,1,0,0,0]],float)
        for bad in (np.array([[.2]*5,good[1],good[2]]), good*.8,
                    np.array([good[0],good[1],[0,0,1,0,0]]),
                    np.array([[0,1,0,0,0],good[1],good[2]])):
            with self.assertRaises(ValueError): validate_binding(p,bad,1)
        with self.assertRaises(ValueError): validate_binding(p[1:],good[1:],1)

    def test_layout_and_classification(self):
        p = np.array([[0,0,1],[0,0,.9],[0,0,.8],[.2,-1,.9],[-.2,-1,.9]])
        s = classify_front_locks(p,np.array([[1,2]]),1)
        np.testing.assert_array_equal(s,[0,0,0,1,-1])
        layout = chain_layout(p[:3],np.ones(3),1,.8,2)
        self.assertEqual(layout.shape,(3,3))
        with self.assertRaises(ValueError): chain_layout(p[:3],np.ones(3),1,.99,2)
