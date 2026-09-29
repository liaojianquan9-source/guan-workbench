#!/usr/bin/env python3
"""Local TransNetV2 adapter; originals remain untouched, stdout is JSON only."""
import argparse
import contextlib
import json
import sys
import time


def progress(value, message):
    print(json.dumps({'progress': value, 'message': message}, ensure_ascii=False), file=sys.stderr, flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('video')
    p.add_argument('--threshold', type=float, default=0.35)
    p.add_argument('--device', choices=['auto', 'cpu', 'mps'], default='auto')
    args = p.parse_args()
    if not 0.05 <= args.threshold <= 0.95:
        p.error('threshold must be between 0.05 and 0.95')
    progress(0.02, '正在载入本地镜头识别模型')
    with contextlib.redirect_stdout(sys.stderr):
        import torch
        from transnetv2_pytorch import TransNetV2
        torch.set_num_threads(4)

        class ReportingTransNet(TransNetV2):
            def predict_frames(self, frames, quiet=True):
                self.frame_total = len(frames)
                self.frame_done = 0
                self.last_report = 0
                return super().predict_frames(frames, quiet=True)

            def predict_raw(self, frames):
                result = super().predict_raw(frames)
                self.frame_done = min(self.frame_total, self.frame_done + 50)
                if time.monotonic() - self.last_report > 0.75:
                    fraction = self.frame_done / max(self.frame_total, 1)
                    progress(0.08 + 0.77 * fraction,
                             f'正在识别镜头 {self.frame_done}/{self.frame_total} 帧')
                    self.last_report = time.monotonic()
                return result

        model = ReportingTransNet(device=args.device)
        model.eval()
        progress(0.08, '正在逐帧寻找镜头切换')
        with torch.inference_mode():
            scenes = model.detect_scenes(args.video, threshold=args.threshold)
    cuts = sorted(set(float(s['start_time']) for s in scenes if float(s['start_time']) > 0))
    progress(0.86, '镜头切点识别完成，正在整理结果')
    print(json.dumps({'engine': 'transnetv2', 'threshold': args.threshold,
                      'device': str(model.device), 'cut_times': cuts,
                      'scene_count': len(scenes)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
