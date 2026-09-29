import React from 'react';
import {Composition} from 'remotion';
import {BrollVideo} from './Video';
import {defaultLayout} from './default-layout';
import type {LayoutRecord} from './types';

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="BrollLayout"
      component={BrollVideo}
      durationInFrames={defaultLayout.durationInFrames ?? 150}
      fps={defaultLayout.fps ?? 30}
      width={defaultLayout.width ?? 1920}
      height={defaultLayout.height ?? 1080}
      defaultProps={defaultLayout}
      calculateMetadata={({props}: {props: LayoutRecord}) => ({
        durationInFrames: props.durationInFrames ?? 150,
        fps: props.fps ?? 30,
        width: props.width ?? 1920,
        height: props.height ?? 1080,
      })}
    />
  );
};

