"""Non-destructive background-audio sections, with independent song lookup."""
import copy
import json
import math
import threading
import uuid
from pathlib import Path


def new_section(start, end, origin='manual'):
    return dict(id=uuid.uuid4().hex, start=start, end=end, origin=origin,
                recognition={'status': 'idle', 'tracks': []})


def split_section(sections, at, minimum):
    result = copy.deepcopy(sections)
    index = next((i for i, s in enumerate(result) if s['start'] < at < s['end']), None)
    if index is None or min(at-result[index]['start'], result[index]['end']-at) < minimum-1e-7:
        raise ValueError('切点太靠近边界，请移动播放头后再切。')
    old = result[index]
    result[index:index+1] = [new_section(old['start'], at), new_section(at, old['end'])]
    return result


class MusicSections:
    def __init__(self, store, error, number, root):
        self.store, self.Error, self.number, self.root = store, error, number, root
        self.lookup_slot = threading.Semaphore(1)

    def state(self, project):
        return project.setdefault('music_sections', dict(status='idle', revision=0, sections=[new_section(0, project['duration'])]))

    def dispatch(self, pid, body):
        action = body.get('action', 'analyze')
        with self.store.lock(pid):
            p = self.store.read(pid)
            if not p.get('has_audio'):
                raise self.Error(422, '这个视频没有声音。')
            state = self.state(p)
            if action == 'analyze':
                # Entering the workspace never replaces existing or manually adjusted cuts.
                if state['status'] != 'idle':
                    return p
                state.update(status='processing', message='正在查找背景音乐的变化位置…')
                self.store.write(p)
                self.launch('music-sections:'+pid, self.analyze_job, pid, state['revision'])
                return p
            if action == 'retry':
                if state['status'] != 'error':
                    return p
                state['status'] = 'idle'
                self.store.write(p)
                return self.dispatch(pid, {'action':'analyze'})
            if action == 'recognize':
                selected = next((s for s in state['sections'] if s['id'] == body.get('id')), None)
                if not selected:
                    raise self.Error(404, '这段声音已调整，请重新选择。')
                if selected['recognition']['status'] in {'queued','processing'}:
                    return p
                selected['recognition'].update(status='queued', message='等待识别这段音乐…', token=uuid.uuid4().hex)
                self.store.write(p)
                self.launch('section-song:'+pid+':'+selected['id'], self.recognize_job, pid, copy.deepcopy(selected))
                return p
            if body.get('expected_revision') != state['revision'] or isinstance(body.get('expected_revision'), bool):
                raise self.Error(409, '音乐分段已变化，请重新核对后操作。')
            sections = copy.deepcopy(state['sections'])
            minimum = max(1/p['fps'], .1)
            try:
                if action == 'split':
                    at = round(self.number(body.get('time'), '切点')*p['fps'])/p['fps']
                    sections = split_section(sections, at, minimum)
                elif action in {'boundary','merge'}:
                    index = next((i for i,s in enumerate(sections) if s['id'] == body.get('id')), -1)
                    if index < 1:
                        raise ValueError('请选择第二段以后的分界。')
                    left, right = sections[index-1:index+1]
                    if action == 'merge':
                        sections[index-1:index+1] = [new_section(left['start'], right['end'])]
                    else:
                        at = round(self.number(body.get('time'), '切点')*p['fps'])/p['fps']
                        if not left['start']+minimum <= at <= right['end']-minimum:
                            raise ValueError('切点需要位于相邻两段内部。')
                        sections[index-1:index+1] = [new_section(left['start'], at), new_section(at, right['end'])]
                elif action == 'undo':
                    if not state.get('history'):
                        raise ValueError('没有可以撤销的分段调整。')
                    sections = state['history'].pop()
                    for section in sections:
                        if section['recognition']['status'] in {'queued','processing'}:
                            section['recognition'] = {'status':'idle','tracks':[]}
                else:
                    raise ValueError('不支持这个音乐分段操作。')
            except ValueError as error:
                raise self.Error(400, str(error)) from None
            if action != 'undo':
                state['history'] = (state.get('history', [])+[state['sections']])[-20:]
            state.update(sections=sections, revision=state['revision']+1, status='ready', message='已按时间分段；可分别识别歌曲。')
            self.store.write(p)
            return p

    def after_source(self, pid):
        """Continue only the music analysis explicitly requested by the user."""
        with self.store.lock(pid):
            p = self.store.read(pid)
            state = p.get('music_sections', {})
            if state.get('status') != 'waiting_audio':
                return p
            state['status'] = 'idle'
            self.store.write(p)
            return self.dispatch(pid, {'action': 'analyze'})

    def launch(self, key, target, *args):
        thread = threading.Thread(target=target, args=args, daemon=True)
        self.store.jobs[key] = thread
        thread.start()

    def source(self, p):
        source = p.get('source_audio', {})
        file = source.get('sound', {}).get('files', {}).get('background')
        if file:
            return self.store.research.file(p['id'], source['id'], file['id'])
        return self.store.directory(p['id'])/'source.mp4'

    def analyze_job(self, pid, revision):
        try:
            p = self.store.read(pid)
            result = self.store.run([str(self.root/'.venv-separation/bin/python'), str(self.root/'tools/detect_music_sections.py'), str(self.source(p)), str(p['duration'])], timeout=180)
            if result.returncode:
                raise self.Error(422, '自动分段未完成，可重试或在播放头手动切开。')
            data = json.loads(result.stdout)
            cuts = sorted(set(round(float(t)*p['fps'])/p['fps'] for t in data['cuts'] if math.isfinite(float(t)) and .1 < float(t) < p['duration']-.1))
            edges = [0, *cuts, p['duration']]
            with self.store.lock(pid):
                latest = self.store.read(pid); state = self.state(latest)
                if state['revision'] != revision:
                    return
                state.update(status='ready', revision=revision+1,
                             sections=[new_section(a,b,'suggested') for a,b in zip(edges,edges[1:])],
                             message='建议切点来自声音变化，请回听确认；也可手动调整。', method=data.get('method'))
                self.store.write(latest)
        except Exception as error:
            with self.store.lock(pid):
                p = self.store.read(pid); state = self.state(p)
                if state['revision'] == revision:
                    state.update(status='error', message=getattr(error,'message','自动分段未完成，可重试或手动切开。'))
                    self.store.write(p)

    def recognize_job(self, pid, snapshot):
        acquired = False
        try:
            while not acquired:
                if self.store.stopping:
                    return
                acquired = self.lookup_slot.acquire(timeout=.25)
            with self.store.lock(pid):
                p = self.store.read(pid)
                section = next((s for s in self.state(p)['sections'] if s['id'] == snapshot['id']), None)
                if not section or section['recognition'].get('token') != snapshot['recognition'].get('token'):
                    return
                section['recognition'].update(status='processing', message='正在识别这段音乐…')
                self.store.write(p)
            result = self.store.run([str(self.root/'.venv-music/bin/python'), str(self.root/'tools/recognize_music.py'), str(self.store.directory(pid)/'source.mp4'), str(snapshot['end']-snapshot['start']), str(snapshot['start'])], timeout=150)
            tracks, done, error = {}, False, ''
            for line in result.stdout.splitlines():
                try: event = json.loads(line)
                except ValueError: continue
                if event.get('type') == 'found':
                    track = event['track']; tracks[track['key']] = track
                elif event.get('type') == 'done': done=True
                elif event.get('type') == 'error': error=event.get('message','识别失败。')
            status = 'ready' if done and not result.returncode else 'error'
            recognition = dict(status=status, tracks=list(tracks.values()), message=error or ('识曲服务未完成响应，请重试。' if status == 'error' else '未匹配到歌曲，可换一个范围重试。' if not tracks else '已找到歌曲；可打开歌曲资料。'))
        except Exception:
            recognition = dict(status='error', tracks=[], message='识曲服务未完成响应，请重试。')
        finally:
            if acquired:
                self.lookup_slot.release()
        with self.store.lock(pid):
            p = self.store.read(pid)
            section = next((s for s in self.state(p)['sections'] if s['id'] == snapshot['id'] and s['start']==snapshot['start'] and s['end']==snapshot['end']), None)
            if section and section['recognition'].get('token') == snapshot['recognition'].get('token'):
                section['recognition'] = recognition
                self.store.write(p)
