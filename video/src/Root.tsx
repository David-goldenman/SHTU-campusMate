import React from 'react';
import {Composition} from 'remotion';
import {Film} from './Film';
import film from './film.json';

export const Root: React.FC = () => <Composition id="CampusHub" component={Film}
  width={film.width} height={film.height} fps={film.fps}
  durationInFrames={film.scenes.reduce((n,s)=>n+s.seconds*film.fps,0)}/>;
