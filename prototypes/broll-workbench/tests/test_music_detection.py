"""Check acoustic suggestions with generated audio, using the installed NumPy runtime."""
import subprocess
from pathlib import Path
from unittest import TestCase,skipUnless
ROOT=Path(__file__).resolve().parents[1]
@skipUnless((ROOT/'.venv-separation/bin/python').exists(),'local audio runtime')
class DetectionTest(TestCase):
    def test_stable_music_silence_and_abrupt_change(self):
        code='''
import numpy as np
from tools.detect_music_sections import suggest_cuts
rate=8000;t=np.arange(30*rate)/rate
first=np.sin(2*np.pi*220*t)*.2
second=np.sin(2*np.pi*1700*t)*.2
assert suggest_cuts(np.zeros(len(t)))==[]
assert suggest_cuts(first)==[]
cuts=suggest_cuts(np.concatenate([first,second]))
assert len(cuts)==1 and abs(cuts[0]-30)<2,cuts
print(cuts)
'''
        result=subprocess.run([str(ROOT/'.venv-separation/bin/python'),'-c',code],cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
