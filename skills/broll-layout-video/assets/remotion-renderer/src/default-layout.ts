import type {LayoutRecord} from './types';

export const defaultLayout: LayoutRecord = {
  id: 'broll-layout-preview',
  type: 'data-table',
  durationInFrames: 150,
  fps: 30,
  width: 1920,
  height: 1080,
  elements: [
    {
      id: 'table',
      type: 'table',
      role: 'comparison',
      box: [12, 20, 76, 60],
      columns: ['方案', '输入', '输出'],
      rows: [
        ['A', '24', '31'],
        ['B', '46', '58'],
        ['C', '72', '86'],
        ['结果', '94', '128'],
      ],
      resultRow: 3,
    },
  ],
  focus: ['table', 'result_row'],
};

