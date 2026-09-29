import React from 'react';
import {
  AbsoluteFill,
  Img,
  Loop,
  OffthreadVideo,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import type {
  Box,
  ChapterMediaElement,
  DialogElement,
  FullFrameArollElement,
  KineticArollBrollElement,
  LayoutRecord,
  StructureImageElement,
  TableElement,
  TitleVideoElement,
} from './types';

const defaultTheme = {
  background: '#080B16',
  surface: '#151B2E',
  foreground: '#F3F6FF',
  muted: '#8994AD',
  accent: '#66E3FF',
  accent2: '#8E76FF',
};

const boxStyle = ([x, y, width, height]: Box): React.CSSProperties => ({
  position: 'absolute',
  left: `${x}%`,
  top: `${y}%`,
  width: `${width}%`,
  height: `${height}%`,
});

const Background: React.FC<{theme: typeof defaultTheme}> = ({theme}) => {
  return (
    <AbsoluteFill
      style={{
        backgroundColor: theme.background,
        backgroundImage: `radial-gradient(circle at 18% 24%, ${theme.accent2}33 0, transparent 30%), radial-gradient(circle at 84% 72%, ${theme.accent}25 0, transparent 34%)`,
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 40,
          border: `1px solid ${theme.muted}2E`,
        }}
      />
    </AbsoluteFill>
  );
};

const TableScene: React.FC<{layout: LayoutRecord; theme: typeof defaultTheme}> = ({layout, theme}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const table = layout.elements.find((element): element is TableElement => element.type === 'table');

  if (!table) {
    return null;
  }

  const titleIn = spring({frame, fps, config: {damping: 16, stiffness: 120}});
  const highlight = interpolate(frame, [82, 108], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <>
      <Background theme={theme} />
      <div
        style={{
          position: 'absolute',
          left: '12%',
          top: '8%',
          color: theme.foreground,
          opacity: titleIn,
          transform: `translateY(${(1 - titleIn) * 24}px)`,
          fontFamily: 'Arial, sans-serif',
        }}
      >
        <div style={{fontSize: 26, letterSpacing: 5, color: theme.accent}}>DATA COMPARISON</div>
        <div style={{fontSize: 56, fontWeight: 700, marginTop: 8}}>关键数据如何变化？</div>
      </div>

      <div
        style={{
          ...boxStyle(table.box),
          display: 'grid',
          gridTemplateRows: `repeat(${table.rows.length + 1}, 1fr)`,
          overflow: 'hidden',
          border: `1px solid ${theme.muted}66`,
          borderRadius: 24,
          backgroundColor: `${theme.surface}E6`,
          boxShadow: `0 24px 80px ${theme.background}A8`,
          fontFamily: 'Arial, sans-serif',
        }}
      >
        {[table.columns, ...table.rows].map((row, rowIndex) => {
          const rowProgress = spring({
            frame: frame - 18 - rowIndex * 7,
            fps,
            config: {damping: 18, stiffness: 150},
          });
          const isHeader = rowIndex === 0;
          const dataIndex = rowIndex - 1;
          const isResult = dataIndex === table.resultRow;
          const resultStrength = isResult ? highlight : 0;
          const nonResultOpacity = isHeader || isResult ? 1 : 1 - highlight * 0.42;
          const accentA = Math.round(resultStrength * 150).toString(16).padStart(2, '0');
          const accentB = Math.round(resultStrength * 115).toString(16).padStart(2, '0');

          return (
            <div
              key={`${rowIndex}-${row.join('-')}`}
              style={{
                display: 'grid',
                gridTemplateColumns: `repeat(${row.length}, 1fr)`,
                alignItems: 'center',
                opacity: rowProgress * nonResultOpacity,
                transform: `translateX(${(1 - rowProgress) * 70}px) scale(${1 + resultStrength * 0.018})`,
                transformOrigin: 'center',
                color: theme.foreground,
                background: isHeader
                  ? `${theme.foreground}0D`
                  : isResult
                    ? `linear-gradient(90deg, ${theme.accent2}${accentA}, ${theme.accent}${accentB})`
                    : 'transparent',
                borderTop: rowIndex === 0 ? 'none' : `1px solid ${theme.muted}35`,
                fontSize: isHeader ? 24 : isResult ? 36 : 30,
                fontWeight: isHeader || isResult ? 700 : 500,
              }}
            >
              {row.map((cell, cellIndex) => (
                <div
                  key={`${cellIndex}-${cell}`}
                  style={{
                    padding: '0 30px',
                    textAlign: cellIndex === 0 ? 'left' : 'right',
                    color: isHeader ? theme.muted : theme.foreground,
                  }}
                >
                  {cell}
                </div>
              ))}
            </div>
          );
        })}
      </div>

      <div
        style={{
          position: 'absolute',
          right: '7%',
          bottom: '8%',
          color: theme.accent,
          fontFamily: 'Arial, sans-serif',
          fontSize: 24,
          opacity: highlight,
          transform: `translateX(${(1 - highlight) * 20}px)`,
        }}
      >
        结论已锁定 →
      </div>
    </>
  );
};

const DialogScene: React.FC<{layout: LayoutRecord; theme: typeof defaultTheme}> = ({layout, theme}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const dialog = layout.elements.find((element): element is DialogElement => element.type === 'dialog');

  if (!dialog) {
    return null;
  }

  const entrance = spring({frame, fps, config: {damping: 18, stiffness: 120}});
  const reframe = interpolate(frame, [36, 112], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const scale = interpolate(reframe, [0, 1], [1.62, 1]);
  const translateX = interpolate(reframe, [0, 1], [-19, 0]);
  const translateY = interpolate(reframe, [0, 1], [-16, 0]);

  return (
    <>
      <Background theme={theme} />
      <div
        style={{
          position: 'absolute',
          left: '7%',
          top: '8%',
          color: theme.foreground,
          fontFamily: 'Arial, sans-serif',
          opacity: entrance,
        }}
      >
        <div style={{fontSize: 26, color: theme.accent, letterSpacing: 5}}>PROMPT DETAIL</div>
        <div style={{fontSize: 48, fontWeight: 700, marginTop: 8}}>从局部重点回到完整语境</div>
      </div>

      <div
        style={{
          ...boxStyle(dialog.box),
          transform: `translate(${translateX}%, ${translateY}%) scale(${scale})`,
          transformOrigin: '24% 25%',
          opacity: entrance,
        }}
      >
        <div
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: 38,
            border: `1px solid ${theme.muted}66`,
            backgroundColor: `${theme.surface}F2`,
            boxShadow: `0 30px 100px ${theme.background}B5`,
            padding: '54px 64px',
            color: theme.foreground,
            fontFamily: 'Arial, sans-serif',
          }}
        >
          <div style={{fontSize: 22, letterSpacing: 4, color: theme.muted}}>{dialog.kicker ?? 'CONTEXT'}</div>
          <div style={{fontSize: 50, fontWeight: 700, marginTop: 18}}>{dialog.title}</div>
          <div style={{marginTop: 34, display: 'grid', gap: 18}}>
            {dialog.lines.map((line, index) => {
              const lineIn = spring({
                frame: frame - 10 - index * 7,
                fps,
                config: {damping: 18, stiffness: 140},
              });
              const emphasized = dialog.emphasis && line.includes(dialog.emphasis);
              return (
                <div
                  key={line}
                  style={{
                    fontSize: emphasized ? 38 : 31,
                    lineHeight: 1.35,
                    color: emphasized ? theme.accent : theme.foreground,
                    opacity: lineIn,
                    transform: `translateY(${(1 - lineIn) * 14}px)`,
                  }}
                >
                  {line}
                </div>
              );
            })}
          </div>
          <div
            style={{
              position: 'absolute',
              left: 64,
              right: 64,
              bottom: 40,
              height: 4,
              backgroundColor: `${theme.muted}38`,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${reframe * 100}%`,
                height: '100%',
                background: `linear-gradient(90deg, ${theme.accent2}, ${theme.accent})`,
              }}
            />
          </div>
        </div>
      </div>

      <div
        style={{
          position: 'absolute',
          right: '7%',
          bottom: '7%',
          fontFamily: 'Arial, sans-serif',
          color: theme.muted,
          fontSize: 23,
        }}
      >
        {reframe < 0.55 ? '聚焦局部' : '建立整体理解'}
      </div>
    </>
  );
};

const TitleOverVideoScene: React.FC<{layout: LayoutRecord; theme: typeof defaultTheme}> = ({
  layout,
  theme,
}) => {
  const frame = useCurrentFrame();
  const {durationInFrames, fps} = useVideoConfig();
  const titleVideo = layout.elements.find(
    (element): element is TitleVideoElement => element.type === 'title-video',
  );

  if (!titleVideo) {
    return null;
  }

  const kickerIn = spring({
    frame: frame - 3,
    fps,
    config: {damping: 18, stiffness: 110, mass: 0.7},
  });
  const titleIn = spring({
    frame: frame - 8,
    fps,
    config: {damping: 15, stiffness: 125, mass: 0.72},
  });
  const subtitleIn = spring({
    frame: frame - 17,
    fps,
    config: {damping: 18, stiffness: 105, mass: 0.75},
  });
  const exit = interpolate(frame, [durationInFrames - 14, durationInFrames - 1], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const backgroundScale = interpolate(frame, [0, durationInFrames], [1.23, 1.17], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const backgroundBlur = interpolate(frame, [0, 24], [11, 5.5], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const titleScale = interpolate(titleIn, [0, 1], [0.78, 1]);
  const titleBlur = interpolate(titleIn, [0, 1], [12, 0]);
  const scan = interpolate(frame, [8, 38], [-12, 112], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill style={{overflow: 'hidden', backgroundColor: '#090A0D'}}>
      <OffthreadVideo
        src={staticFile(titleVideo.videoSrc)}
        playbackRate={titleVideo.playbackRate ?? 1}
        muted
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          objectPosition: '50% 47%',
          transform: `scale(${backgroundScale})`,
          filter: `blur(${backgroundBlur}px) brightness(0.42) saturate(0.58)`,
          opacity: exit,
        }}
      />

      <AbsoluteFill
        style={{
          background:
            'radial-gradient(circle at 50% 46%, rgba(31,36,43,0.06) 0%, rgba(4,5,8,0.54) 62%, rgba(0,0,0,0.78) 100%)',
          opacity: exit,
        }}
      />
      <AbsoluteFill
        style={{
          background:
            'linear-gradient(180deg, rgba(0,0,0,0.34) 0%, rgba(0,0,0,0.04) 34%, rgba(0,0,0,0.08) 63%, rgba(0,0,0,0.48) 100%)',
          opacity: exit,
        }}
      />

      <div
        style={{
          position: 'absolute',
          left: '10%',
          right: '10%',
          top: '29%',
          bottom: '21%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'PingFang SC, Heiti SC, Helvetica Neue, Arial, sans-serif',
          color: theme.foreground,
          opacity: exit,
        }}
      >
        <div
          style={{
            fontSize: 24,
            fontWeight: 500,
            letterSpacing: 18,
            paddingLeft: 18,
            color: 'rgba(239,242,246,0.72)',
            opacity: kickerIn,
            transform: `translateY(${(1 - kickerIn) * 18}px)`,
          }}
        >
          {titleVideo.kicker}
        </div>

        <div
          style={{
            position: 'relative',
            marginTop: 18,
            fontSize: 150,
            lineHeight: 0.96,
            fontWeight: 900,
            letterSpacing: -7,
            whiteSpace: 'nowrap',
            backgroundImage:
              'linear-gradient(180deg, #FFFFFF 0%, #E8EBEF 38%, #AEB5BE 58%, #F7F8FA 74%, #B8BEC6 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            filter: `blur(${titleBlur}px) drop-shadow(0 16px 30px rgba(0,0,0,0.65))`,
            opacity: titleIn,
            transform: `translateY(${(1 - titleIn) * 34}px) scale(${titleScale})`,
          }}
        >
          {titleVideo.title}
          <div
            style={{
              position: 'absolute',
              left: `${scan}%`,
              top: '49%',
              width: '18%',
              height: 2,
              background:
                'linear-gradient(90deg, transparent, rgba(255,255,255,0.72), transparent)',
              boxShadow: '0 0 12px rgba(255,255,255,0.34)',
            }}
          />
        </div>

        <div
          style={{
            marginTop: 30,
            fontSize: 22,
            fontWeight: 500,
            letterSpacing: 13,
            paddingLeft: 13,
            color: 'rgba(237,240,244,0.78)',
            opacity: subtitleIn,
            transform: `translateY(${(1 - subtitleIn) * 20}px)`,
          }}
        >
          {titleVideo.subtitle}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const StructureImageScene: React.FC<{layout: LayoutRecord}> = ({layout}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const structure = layout.elements.find(
    (element): element is StructureImageElement => element.type === 'structure-image',
  );

  if (!structure) {
    return null;
  }

  const progress = interpolate(frame, [0, Math.max(1, durationInFrames - 1)], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const backgroundScale = interpolate(
    progress,
    [0, 1],
    [structure.scaleFrom ?? 1.045, structure.scaleTo ?? 1.015],
  );
  const backgroundX = interpolate(progress, [0, 1], [0.45, -0.25]);
  const backgroundY = interpolate(progress, [0, 1], [0.2, -0.15]);
  return (
    <AbsoluteFill style={{overflow: 'hidden', backgroundColor: '#151515'}}>
      <Img
        src={staticFile(structure.imageSrc)}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          transform: `translate(${backgroundX}%, ${backgroundY}%) scale(${backgroundScale})`,
          filter: 'grayscale(1) brightness(0.96) contrast(0.98)',
        }}
      />

      <AbsoluteFill
        style={{
          background:
            'radial-gradient(circle at 50% 47%, transparent 0%, rgba(8,8,8,0.02) 64%, rgba(2,2,2,0.16) 100%)',
        }}
      />
    </AbsoluteFill>
  );
};

const ChapterSubjectMediaScene: React.FC<{layout: LayoutRecord}> = ({layout}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const scene = layout.elements.find(
    (element): element is ChapterMediaElement => element.type === 'chapter-media',
  );

  if (!scene) {
    return null;
  }

  const subjectMove = spring({
    frame: frame - 1,
    fps,
    config: {damping: 16, stiffness: 118, mass: 0.68},
  });
  const titleReveal = spring({
    frame: frame - 5,
    fps,
    config: {damping: 17, stiffness: 126, mass: 0.66},
  });
  const mediaIn = spring({
    frame: frame - 44,
    fps,
    config: {damping: 15, stiffness: 112, mass: 0.72},
  });
  const baseExit = interpolate(frame, [43, 57], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const subjectLeft = interpolate(subjectMove, [0, 1], [7, 70]);
  const subjectScale = interpolate(subjectMove, [0, 1], [0.92, 1]);
  const titleShift = interpolate(baseExit, [0, 1], [-80, 0]);
  const mediaX = interpolate(mediaIn, [0, 1], [-980, 0]);
  const mediaY = interpolate(mediaIn, [0, 1], [180, 0]);
  const mediaScale = interpolate(mediaIn, [0, 1], [0.34, 1.54]);
  const mediaRotate = interpolate(mediaIn, [0, 1], [-16, 0]);
  const mediaRadius = interpolate(mediaIn, [0, 1], [38, 0]);

  return (
    <AbsoluteFill
      style={{
        overflow: 'hidden',
        backgroundColor: '#04120F',
        fontFamily: 'PingFang SC, Heiti SC, Helvetica Neue, Arial, sans-serif',
      }}
    >
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(circle at 74% 34%, rgba(63,219,178,0.16) 0%, transparent 32%), radial-gradient(circle at 18% 82%, rgba(44,131,112,0.14) 0%, transparent 34%), linear-gradient(135deg, #061513 0%, #020807 56%, #06140F 100%)',
        }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.13,
          backgroundImage:
            'linear-gradient(rgba(126,210,190,0.18) 1px, transparent 1px), linear-gradient(90deg, rgba(126,210,190,0.18) 1px, transparent 1px)',
          backgroundSize: '72px 72px',
          transform: 'perspective(900px) rotateX(62deg) scale(1.35) translateY(25%)',
          transformOrigin: 'center bottom',
        }}
      />

      <div
        style={{
          position: 'absolute',
          left: '8%',
          top: '32%',
          width: '58%',
          color: '#F1F7F5',
          opacity: baseExit,
          transform: `translateX(${titleShift}px)`,
          zIndex: 1,
        }}
      >
        <div
          style={{
            fontSize: 28,
            letterSpacing: 9,
            color: '#7BE3C3',
            opacity: titleReveal,
            transform: `translateY(${(1 - titleReveal) * 24}px)`,
          }}
        >
          {scene.eyebrow ?? 'CHAPTER / AI'}
        </div>
        <div
          style={{
            marginTop: 18,
            fontSize: 116,
            lineHeight: 0.98,
            letterSpacing: -5,
            fontWeight: 850,
            whiteSpace: 'nowrap',
            clipPath: `inset(0 ${(1 - titleReveal) * 100}% 0 0)`,
            transform: `translateX(${(1 - titleReveal) * 90}px)`,
            textShadow: '12px 12px 0 rgba(81,103,98,0.46), 0 18px 46px rgba(0,0,0,0.58)',
          }}
        >
          {scene.titleLines.map((line) => (
            <div key={line}>{line}</div>
          ))}
        </div>
      </div>

      <div
        style={{
          position: 'absolute',
          left: `${subjectLeft}%`,
          top: '14%',
          width: '23%',
          height: '72%',
          opacity: baseExit,
          transform: `translateX(-50%) scale(${subjectScale})`,
          zIndex: 2,
        }}
      >
        <div
          style={{
            position: 'absolute',
            inset: -20,
            borderRadius: 70,
            background: 'rgba(73,232,188,0.16)',
            filter: 'blur(36px)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            inset: 0,
            overflow: 'hidden',
            clipPath: 'polygon(17% 0, 83% 0, 100% 100%, 0 100%)',
            border: '1px solid rgba(151,245,219,0.38)',
            background: '#07110F',
          }}
        >
          <OffthreadVideo
            src={staticFile(scene.subjectVideoSrc)}
            muted
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              objectPosition: '50% 47%',
              transform: 'scale(1.08)',
              filter: 'saturate(0.72) contrast(1.08) brightness(0.83)',
            }}
          />
          <AbsoluteFill
            style={{
              background:
                'linear-gradient(180deg, rgba(4,15,12,0.02) 0%, rgba(3,13,10,0.04) 52%, rgba(2,10,8,0.93) 82%, #020A08 100%)',
            }}
          />
        </div>
      </div>

      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: '50%',
          width: 1280,
          height: 720,
          borderRadius: mediaRadius,
          overflow: 'hidden',
          opacity: frame < 43 ? 0 : 1,
          transform: `translate(-50%, -50%) translate(${mediaX}px, ${mediaY}px) rotate(${mediaRotate}deg) scale(${mediaScale})`,
          boxShadow:
            '0 0 0 1px rgba(155,239,218,0.46), 0 40px 120px rgba(0,0,0,0.72), 0 0 70px rgba(58,213,174,0.22)',
          zIndex: 4,
        }}
      >
        <Img
          src={staticFile(scene.mediaImageSrc)}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
          }}
        />
        <AbsoluteFill
          style={{
            boxShadow: 'inset 0 0 60px rgba(0,0,0,0.26)',
          }}
        />
      </div>
    </AbsoluteFill>
  );
};

const FullFrameArollScene: React.FC<{layout: LayoutRecord}> = ({layout}) => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const arroll = layout.elements.find(
    (element): element is FullFrameArollElement => element.type === 'full-frame-aroll',
  );

  if (!arroll) {
    return null;
  }

  const fadeInFrames = Math.max(0, arroll.fadeInFrames ?? 0);
  const fadeOutFrames = Math.max(0, arroll.fadeOutFrames ?? 0);
  const fadeIn = fadeInFrames === 0
    ? 1
    : interpolate(frame, [0, fadeInFrames], [0, 1], {
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
      });
  const fadeOut = fadeOutFrames === 0
    ? 1
    : interpolate(
        frame,
        [Math.max(0, durationInFrames - fadeOutFrames), durationInFrames - 1],
        [1, 0],
        {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        },
      );
  const scale = interpolate(
    frame,
    [0, Math.max(1, durationInFrames - 1)],
    [arroll.scaleFrom ?? 1, arroll.scaleTo ?? arroll.scaleFrom ?? 1],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    },
  );

  return (
    <AbsoluteFill style={{overflow: 'hidden', backgroundColor: '#000'}}>
      <Loop durationInFrames={Math.max(1, arroll.loopDurationInFrames)}>
        <OffthreadVideo
          src={staticFile(arroll.videoSrc)}
          trimBefore={arroll.trimBefore ?? 0}
          volume={arroll.volume ?? 1}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            objectPosition: arroll.objectPosition ?? '50% 50%',
            transform: `scale(${scale})`,
            opacity: Math.min(fadeIn, fadeOut),
          }}
        />
      </Loop>
    </AbsoluteFill>
  );
};

const KineticArollBrollScene: React.FC<{layout: LayoutRecord}> = ({layout}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const scene = layout.elements.find(
    (element): element is KineticArollBrollElement => element.type === 'kinetic-aroll-broll',
  );

  if (!scene) {
    return null;
  }

  const clamp = (input: number[], output: number[]) =>
    interpolate(frame, input, output, {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    });
  const reveal = (start: number, end: number) => clamp([start, end], [0, 1]);

  const leadExit = clamp([94, 104], [1, 0]);
  const leadTop = spring({frame, fps, config: {damping: 18, stiffness: 160, mass: 0.72}});
  const leadSmall = spring({frame: frame - 7, fps, config: {damping: 17, stiffness: 150, mass: 0.7}});
  const leadBottom = spring({frame: frame - 11, fps, config: {damping: 16, stiffness: 145, mass: 0.72}});
  const leadRight = spring({frame: frame - 22, fps, config: {damping: 17, stiffness: 145, mass: 0.72}});

  const numberLocal = frame - 96;
  const numberOpacity = reveal(96, 104) * (frame < 172 ? 1 : 0);
  const numberScale = interpolate(numberLocal, [0, 8, 18, 54, 76], [3.05, 1.9, 1.14, 1.02, 0.84], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const numberShiftX = interpolate(numberLocal, [0, 18, 76], [-210, 0, -28], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const numberFill = interpolate(numberLocal, [5, 16], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const unitIn = interpolate(numberLocal, [10, 22], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const metricDetails = interpolate(numberLocal, [20, 34], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const kimiLocal = frame - 172;
  const kimiExit = clamp([294, 304], [1, 0]);
  const kimiOpacity = frame < 172 ? 0 : kimiExit;
  const kimiIn = spring({frame: kimiLocal, fps, config: {damping: 16, stiffness: 116, mass: 0.82}});
  const kimiDetails = interpolate(kimiLocal, [8, 28], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const kimiBlur = interpolate(kimiLocal, [0, 24], [16, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const kimiScale = interpolate(kimiLocal, [0, 24, 120], [0.72, 1, 1.025], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const moonDrift = interpolate(kimiLocal, [0, 132], [0, 9], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <AbsoluteFill
      style={{
        overflow: 'hidden',
        backgroundColor: '#05070B',
        fontFamily: 'PingFang SC, Heiti SC, Helvetica Neue, Arial, sans-serif',
      }}
    >
      <Loop durationInFrames={Math.max(1, scene.loopDurationInFrames)}>
        <OffthreadVideo
          src={staticFile(scene.videoSrc)}
          volume={scene.volume ?? 1}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            objectPosition: '50% 50%',
            filter: 'contrast(1.02) saturate(0.9) brightness(0.92)',
          }}
        />
      </Loop>

      <AbsoluteFill
        style={{
          background: 'linear-gradient(90deg, rgba(5,12,17,0.15), transparent 48%, rgba(4,8,12,0.12))',
          opacity: leadExit,
        }}
      />

      <div
        style={{
          position: 'absolute',
          left: '6.2%',
          top: '14.8%',
          color: '#E9EEF0',
          fontFamily: 'Songti SC, STSong, serif',
          fontSize: 128,
          fontWeight: 800,
          lineHeight: 0.92,
          letterSpacing: -8,
          opacity: leadTop * leadExit,
          clipPath: `inset(0 ${(1 - leadTop) * 100}% 0 0)`,
          transform: `translateX(${(1 - leadTop) * -70}px) scaleX(0.94)`,
          transformOrigin: 'left center',
          textShadow: '6px 8px 0 rgba(21,37,43,0.58), 0 8px 22px rgba(0,0,0,0.44)',
          zIndex: 2,
        }}
      >
        {scene.leadTop}
      </div>

      <div
        style={{
          position: 'absolute',
          left: '16.8%',
          top: '45.5%',
          color: '#DDE9EA',
          fontFamily: 'Songti SC, STSong, serif',
          fontSize: 46,
          fontWeight: 700,
          letterSpacing: -3,
          opacity: leadSmall * leadExit,
          transform: `translateY(${(1 - leadSmall) * 28}px)`,
          textShadow: '3px 5px 0 rgba(18,48,58,0.62)',
          zIndex: 3,
        }}
      >
        {scene.leadSmall}
      </div>

      <div
        style={{
          position: 'absolute',
          left: '5.5%',
          top: '50.5%',
          fontFamily: 'Songti SC, STSong, serif',
          fontSize: 270,
          fontWeight: 800,
          lineHeight: 0.9,
          opacity: leadBottom * leadExit,
          transform: `translateY(${(1 - leadBottom) * 100}px) scaleX(0.78)`,
          transformOrigin: 'left center',
          backgroundImage: 'linear-gradient(180deg, #ECF1F0 0%, #8DD6E7 48%, #44A0BC 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          filter: 'drop-shadow(7px 10px 0 rgba(19,48,59,0.62))',
          zIndex: 1,
        }}
      >
        {scene.leadBottom}
      </div>

      <div
        style={{
          position: 'absolute',
          left: '59%',
          top: '29%',
          width: '50%',
          fontFamily: 'Songti SC, STSong, serif',
          fontSize: 184,
          fontWeight: 800,
          lineHeight: 1,
          whiteSpace: 'nowrap',
          letterSpacing: -11,
          opacity: leadRight * leadExit,
          clipPath: `inset(0 ${(1 - leadRight) * 100}% 0 0)`,
          transform: `translateX(${(1 - leadRight) * 130}px) scaleX(0.76)`,
          transformOrigin: 'left center',
          backgroundImage: 'linear-gradient(90deg, #E8EFF1 0%, #B2D9E5 45%, #62AFC8 100%)',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          filter: 'drop-shadow(7px 10px 0 rgba(19,46,57,0.68)) drop-shadow(0 8px 22px rgba(0,0,0,0.4))',
          zIndex: 3,
        }}
      >
        {scene.leadRight}
      </div>

      <AbsoluteFill
        style={{
          opacity: numberOpacity,
          overflow: 'hidden',
          backgroundColor: '#050B14',
          background:
            'radial-gradient(circle at 51% 49%, #10283A 0%, #070E19 48%, #03070D 100%)',
          zIndex: 5,
        }}
      >
        <AbsoluteFill
          style={{
            opacity: 0.17,
            backgroundImage:
              'linear-gradient(rgba(76,143,176,0.2) 1px, transparent 1px), linear-gradient(90deg, rgba(76,143,176,0.2) 1px, transparent 1px)',
            backgroundSize: '82px 82px',
          }}
        />
        <div
          style={{
            position: 'absolute',
            inset: 18,
            border: '1px solid rgba(111,173,201,0.22)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            left: '-12%',
            top: '3%',
            fontFamily: 'Impact, Arial Narrow, sans-serif',
            fontSize: 410,
            letterSpacing: -18,
            color: 'transparent',
            WebkitTextStroke: '3px rgba(74,154,194,0.35)',
            opacity: Math.max(0, 1 - numberFill) * 0.95,
            transform: `translateX(${numberShiftX * 0.28}px) scaleX(0.77)`,
          }}
        >
          {scene.metricNumber}
        </div>
        <div
          style={{
            position: 'absolute',
            left: '11%',
            top: '17%',
            width: '91%',
            height: '61%',
            display: 'flex',
            alignItems: 'center',
            transform: `translateX(${numberShiftX}px) scale(${numberScale})`,
            transformOrigin: '43% 51%',
          }}
        >
          <div
            style={{
              fontFamily: 'Impact, Arial Narrow, sans-serif',
              fontSize: 300,
              lineHeight: 0.82,
              letterSpacing: -9,
              transform: 'translateY(28px) scaleX(0.7) scaleY(1.25)',
              transformOrigin: 'left center',
              backgroundImage: 'linear-gradient(180deg, #A7E5F0 0%, #4B9BC2 51%, #174F8A 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              opacity: numberFill,
              filter: 'drop-shadow(0 16px 26px rgba(20,94,142,0.35))',
            }}
          >
            {scene.metricNumber}
          </div>
          <div
            style={{
              marginLeft: -220,
              marginTop: 4,
              fontFamily: 'Songti SC, STSong, serif',
              fontSize: 280,
              fontWeight: 800,
              lineHeight: 0.9,
              color: '#BFEAF3',
              opacity: unitIn,
              transform: `translateY(${28 + (1 - unitIn) * -115}px) rotate(${(1 - unitIn) * 8}deg) scaleX(0.82) scaleY(1.35)`,
              textShadow: '0 15px 30px rgba(23,89,130,0.42)',
            }}
          >
            {scene.metricUnit}
          </div>
          <div
            style={{
              marginLeft: -18,
              marginTop: 260,
              fontFamily: 'Songti SC, STSong, serif',
              fontSize: 82,
              fontWeight: 700,
              whiteSpace: 'nowrap',
              color: '#D7D7D2',
              opacity: unitIn,
              transform: `translateX(${(1 - unitIn) * 90}px)`,
              textShadow: '0 0 16px rgba(225,220,195,0.55)',
            }}
          >
            {scene.metricLabel}
          </div>
          <div
            style={{
              position: 'absolute',
              left: '69%',
              top: '23%',
              width: '20%',
              height: '28%',
              borderTop: '1px solid rgba(137,188,209,0.62)',
              borderRight: '1px solid rgba(137,188,209,0.62)',
              opacity: metricDetails,
            }}
          >
            <div style={{position: 'absolute', right: 5, top: 12, fontSize: 11, color: '#A9BEC7', letterSpacing: 2}}>
              PARAMETER&nbsp;&nbsp;SCALE
            </div>
            <div style={{position: 'absolute', right: 5, top: 31, fontSize: 9, color: '#6D8B9A', letterSpacing: 3}}>
              BILLION&nbsp;&nbsp;MODEL
            </div>
          </div>
          <div
            style={{
              position: 'absolute',
              left: '64%',
              top: '47%',
              color: '#577BE9',
              fontFamily: 'Georgia, serif',
              fontStyle: 'italic',
              fontSize: 28,
              opacity: metricDetails,
              transform: 'rotate(-7deg)',
            }}
          >
            Model scale
          </div>
        </div>
      </AbsoluteFill>

      <AbsoluteFill
        style={{
          opacity: kimiOpacity,
          overflow: 'hidden',
          backgroundColor: '#08090C',
          background:
            'radial-gradient(circle at 50% 47%, #161A20 0%, #090A0D 52%, #030406 100%)',
          zIndex: 6,
        }}
      >
        <AbsoluteFill
          style={{
            opacity: 0.16 * kimiDetails,
            backgroundImage:
              'linear-gradient(rgba(102,123,134,0.13) 1px, transparent 1px), linear-gradient(90deg, rgba(102,123,134,0.13) 1px, transparent 1px)',
            backgroundSize: '88px 88px',
          }}
        />
        <div
          style={{
            position: 'absolute',
            left: '6%',
            top: '-4%',
            width: '88%',
            color: 'transparent',
            WebkitTextStroke: '2px rgba(97,105,110,0.25)',
            fontFamily: 'Songti SC, STSong, serif',
            fontSize: 208,
            fontWeight: 900,
            letterSpacing: -22,
            lineHeight: 1,
            opacity: kimiDetails,
            transform: 'scaleX(0.86)',
            transformOrigin: 'left top',
          }}
        >
          国产模型
        </div>
        <div
          style={{
            position: 'absolute',
            left: '23%',
            bottom: '-5%',
            color: 'rgba(107,111,111,0.24)',
            fontFamily: 'Songti SC, STSong, serif',
            fontSize: 192,
            fontWeight: 900,
            letterSpacing: -20,
            opacity: kimiDetails,
            transform: 'scaleX(0.9)',
            transformOrigin: 'left bottom',
          }}
        >
          月面模型
        </div>
        <Img
          src={staticFile(scene.moonTopRightSrc)}
          style={{
            position: 'absolute',
            right: '-1.2%',
            top: '-4%',
            width: '27%',
            height: '42%',
            objectFit: 'cover',
            mixBlendMode: 'screen',
            opacity: 0.9,
            transform: `translate(${moonDrift * 0.35}px, ${moonDrift * -0.2}px) scale(1.1)`,
            filter: 'brightness(0.92) contrast(1.15) saturate(0.48)',
          }}
        />
        <Img
          src={staticFile(scene.moonBottomLeftSrc)}
          style={{
            position: 'absolute',
            left: '-2%',
            bottom: '-7%',
            width: '25%',
            height: '35%',
            objectFit: 'cover',
            mixBlendMode: 'screen',
            opacity: 0.83,
            transform: `translate(${moonDrift * -0.25}px, ${moonDrift * 0.15}px) scale(1.18)`,
            filter: 'brightness(0.84) contrast(1.12) saturate(0.44)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            left: '24.5%',
            top: '36.5%',
            width: '51%',
            height: '27%',
            border: '1px solid rgba(110,142,156,0.27)',
            opacity: kimiDetails,
          }}
        >
          <div style={{position: 'absolute', left: -4, top: -4, width: 8, height: 8, background: '#A8E8F1'}} />
          <div style={{position: 'absolute', right: -4, bottom: -4, width: 8, height: 8, background: '#A8E8F1'}} />
        </div>
        <div
          style={{
            position: 'absolute',
            left: '50%',
            top: '49%',
            display: 'flex',
            alignItems: 'center',
            whiteSpace: 'nowrap',
            transform: `translate(-50%, -50%) scale(${kimiScale})`,
            opacity: kimiIn,
            filter: `blur(${kimiBlur}px) drop-shadow(0 11px 18px rgba(0,0,0,0.72))`,
            fontFamily: 'Arial Black, Helvetica Neue, Arial, sans-serif',
            fontSize: 113,
            fontWeight: 950,
            lineHeight: 1,
            letterSpacing: -7,
          }}
        >
          <span
            style={{
              backgroundImage: 'linear-gradient(180deg, #FFFFFF 0%, #D8DADD 46%, #8B9097 58%, #F2F3F4 78%, #A7ACB2 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}
          >
            {scene.productTitle.split('·')[0]}
          </span>
          <span style={{fontSize: 70, color: '#A9E8F0', padding: '0 15px 7px 18px'}}>◇</span>
          <span
            style={{
              backgroundImage: 'linear-gradient(180deg, #D9F1F4 0%, #7CB8E9 42%, #3556C8 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}
          >
            {scene.productTitle.split('·')[1] ?? ''}
          </span>
        </div>
        <div
          style={{
            position: 'absolute',
            left: '50%',
            top: '70%',
            transform: 'translateX(-50%)',
            color: 'rgba(229,233,236,0.66)',
            fontSize: 17,
            letterSpacing: 10,
            opacity: kimiDetails,
          }}
        >
          {scene.productSubtitle}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

export const BrollVideo: React.FC<LayoutRecord> = (layout) => {
  const theme = {...defaultTheme, ...layout.theme};

  return (
    <AbsoluteFill style={{backgroundColor: theme.background}}>
      {layout.type === 'data-table' ? (
        <TableScene layout={layout} theme={theme} />
      ) : layout.type === 'title-over-video' ? (
        <TitleOverVideoScene layout={layout} theme={theme} />
      ) : layout.type === 'structure-image-motion' ? (
        <StructureImageScene layout={layout} />
      ) : layout.type === 'chapter-subject-media' ? (
        <ChapterSubjectMediaScene layout={layout} />
      ) : layout.type === 'full-frame-aroll' ? (
        <FullFrameArollScene layout={layout} />
      ) : layout.type === 'kinetic-aroll-broll' ? (
        <KineticArollBrollScene layout={layout} />
      ) : (
        <DialogScene layout={layout} theme={theme} />
      )}
    </AbsoluteFill>
  );
};
