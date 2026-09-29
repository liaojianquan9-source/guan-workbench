export type Box = [number, number, number, number];

export type TableElement = {
  id: string;
  type: 'table';
  role?: string;
  box: Box;
  columns: string[];
  rows: string[][];
  resultRow?: number;
};

export type DialogElement = {
  id: string;
  type: 'dialog';
  role?: string;
  box: Box;
  kicker?: string;
  title?: string;
  lines: string[];
  emphasis?: string;
};

export type TitleVideoElement = {
  id: string;
  type: 'title-video';
  role?: string;
  videoSrc: string;
  kicker: string;
  title: string;
  subtitle: string;
  playbackRate?: number;
};

export type StructureImageElement = {
  id: string;
  type: 'structure-image';
  role?: string;
  imageSrc: string;
  scaleFrom?: number;
  scaleTo?: number;
};

export type ChapterMediaElement = {
  id: string;
  type: 'chapter-media';
  role?: string;
  subjectVideoSrc: string;
  mediaImageSrc: string;
  eyebrow?: string;
  titleLines: string[];
};

export type FullFrameArollElement = {
  id: string;
  type: 'full-frame-aroll';
  role?: string;
  videoSrc: string;
  loopDurationInFrames: number;
  trimBefore?: number;
  objectPosition?: string;
  scaleFrom?: number;
  scaleTo?: number;
  volume?: number;
  fadeInFrames?: number;
  fadeOutFrames?: number;
};

export type KineticArollBrollElement = {
  id: string;
  type: 'kinetic-aroll-broll';
  role?: string;
  videoSrc: string;
  loopDurationInFrames: number;
  moonTopRightSrc: string;
  moonBottomLeftSrc: string;
  leadTop: string;
  leadSmall: string;
  leadBottom: string;
  leadRight: string;
  metricNumber: string;
  metricUnit: string;
  metricLabel: string;
  productTitle: string;
  productSubtitle: string;
  volume?: number;
};

export type LayoutElement =
  | TableElement
  | DialogElement
  | TitleVideoElement
  | StructureImageElement
  | ChapterMediaElement
  | FullFrameArollElement
  | KineticArollBrollElement;

export type MotionPreset = {
  target: string;
  preset: 'local-to-full';
  start?: number;
  end?: number;
};

export type LayoutRecord = {
  id: string;
  src?: string;
  type:
    | 'data-table'
    | 'dialog-focus'
    | 'title-over-video'
    | 'structure-image-motion'
    | 'chapter-subject-media'
    | 'full-frame-aroll'
    | 'kinetic-aroll-broll';
  durationInFrames?: number;
  fps?: number;
  width?: number;
  height?: number;
  elements: LayoutElement[];
  focus?: string[];
  groups?: Record<string, string[]>;
  motion?: MotionPreset[];
  must?: string[];
  prefer?: string[];
  theme?: {
    background?: string;
    surface?: string;
    foreground?: string;
    muted?: string;
    accent?: string;
    accent2?: string;
  };
};
