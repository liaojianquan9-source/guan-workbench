"""Local, pinned MDX separator. Output samples stay on the input clip clock."""
import json
import logging
from pathlib import Path
import sys
import time
import numpy as np
import soundfile as sf
from audio_separator.separator import Separator

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'UVR-MDX-NET-Inst_HQ_3.onnx'

def main():
    source, output = Path(sys.argv[1]), Path(sys.argv[2])
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    separator = Separator(model_file_dir=str(ROOT / 'runtime/models/separation'), output_dir=str(output),
                          output_format='WAV', use_soundfile=True, normalization_threshold=1.0,
                          amplification_threshold=0.0, log_level=logging.INFO)
    if '--cpu' in sys.argv[3:]:
        import torch
        separator.torch_device = torch.device('cpu')
        separator.torch_device_mps = None
        separator.onnx_execution_provider = ['CPUExecutionProvider']
    separator.load_model(model_filename=MODEL)
    paths = separator.separate(str(source), custom_output_names={'Vocals':'vocals', 'Instrumental':'background'})
    info = sf.info(source)
    for stem in ['vocals', 'background']:
        path = output / (stem + '.wav')
        audio, rate = sf.read(path, dtype='float32', always_2d=True)
        if rate != info.samplerate or abs(len(audio)-info.frames) > rate * .025:
            raise ValueError('Separated samples do not match source clock; output rejected')
        # Only remove/pad <=25 ms of container/model tail; never rescale or shift content.
        audio = audio[:info.frames]
        if len(audio) < info.frames:
            audio = np.pad(audio, ((0, info.frames-len(audio)),(0,0)))
        sf.write(path, audio, rate, subtype='PCM_16')
    (output / 'result.json').write_text(json.dumps({'model':MODEL,'elapsed_seconds':time.monotonic()-started,
        'device':str(separator.torch_device),'providers':separator.onnx_execution_provider,'sample_rate':info.samplerate,'frames':info.frames,'files':paths},ensure_ascii=False))

if __name__ == '__main__':
    main()
