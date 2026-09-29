import React from 'react';
import {Composition, registerRoot} from 'remotion';
import {casePropsSchema} from './schema';
import {StaticCase} from './editable-case';

const Root: React.FC = () => <Composition
  id="LjqBrollCase"
  component={StaticCase}
  width={1280}
  height={720}
  fps={30}
  durationInFrames={428}
  schema={casePropsSchema}
  defaultProps={{
    motionEnabled: true,
    sceneId: 'auto',
    content: {},
    numbers: {},
    assets: {},
    fonts: {},
    colors: {},
    light: {},
    theme: {articleBackground:'#06121e',greenBackground:'#071b06',paper:'#efe1ae',ink:'#f0f3e9',accent:'#a4e49a',positive:'#6cf656',negative:'#ff4e47',metalLight:'#f2f5fa',metalDark:'#b7b7b4',secondaryInk:'#bcbac2'},
  }}
/>;
registerRoot(Root);
