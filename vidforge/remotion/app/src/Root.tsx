import { CalculateMetadataFunction, Composition } from "remotion";
import { BarChart, BarChartProps } from "./compositions/BarChart";
import { Timeline, TimelineProps } from "./compositions/Timeline";
import { TitleCard, TitleCardProps } from "./compositions/TitleCard";
import { Host, HostProps } from "./compositions/Host";
import { Vocab, VocabProps } from "./compositions/Vocab";
import { Base } from "./theme";

// vidforge passes durationInFrames/fps/width/height in the props file: the composition
// takes its length from the narration, never from a constant here.
const fromProps: CalculateMetadataFunction<Base> = ({ props }) => ({
  durationInFrames: Math.max(1, Math.round(props.durationInFrames)),
  fps: props.fps,
  width: props.width,
  height: props.height,
});

const base: Base = { durationInFrames: 150, fps: 30, width: 1920, height: 1080 };

const demoEnvelope = Array.from({ length: 150 }, (_, i) => Math.max(0, Math.sin(i / 3) * 0.6 + Math.sin(i / 7) * 0.4) * (i % 40 < 30 ? 1 : 0));

export const Root: React.FC = () => (
  <>
    <Composition<any, HostProps>
      id="Host"
      component={Host}
      calculateMetadata={fromProps}
      {...base}
      width={480}
      height={360}
      defaultProps={{ ...base, width: 480, height: 360, envelope: demoEnvelope, name: "Simon", style: { hairStyle: "side", glasses: true } }}
    />
    <Composition<any, VocabProps>
      id="Vocab"
      component={Vocab}
      calculateMetadata={fromProps}
      {...base}
      defaultProps={{ ...base, title: "Vocabulary", items: [
        { word: "eruption", ipa: "/ɪˈrʌpʃn/", meaning: "喷发", example: "The eruption cancelled summer in Europe." },
        { word: "harvest", ipa: "/ˈhɑːvɪst/", meaning: "收成", example: "The harvests of two continents failed." },
        { word: "stratosphere", ipa: "/ˈstrætəsfɪə/", meaning: "平流层", example: "Ash rose into the stratosphere." } ] }}
    />
    <Composition<any, TitleCardProps>
      id="TitleCard"
      component={TitleCard}
      calculateMetadata={fromProps}
      {...base}
      defaultProps={{ ...base, kicker: "Part 2", title: "The Year Without a Summer", subtitle: "1816" }}
    />
    <Composition<any, TimelineProps>
      id="Timeline"
      component={Timeline}
      calculateMetadata={fromProps}
      {...base}
      defaultProps={{
        ...base,
        title: "From eruption to famine",
        events: [
          { date: "Apr 1815", text: "Tambora erupts" },
          { date: "Jun 1816", text: "Snow in New England" },
          { date: "Jul 1816", text: "Crop failure in France" },
          { date: "1817", text: "Bread riots" },
        ],
      }}
    />
    <Composition<any, BarChartProps>
      id="BarChart"
      component={BarChart}
      calculateMetadata={fromProps}
      {...base}
      defaultProps={{
        ...base,
        title: "Volcanic Explosivity Index",
        items: [
          { label: "Tambora 1815", value: 7 },
          { label: "Krakatoa 1883", value: 6 },
          { label: "Pinatubo 1991", value: 6 },
          { label: "St. Helens 1980", value: 5 },
        ],
        max: 8,
        source: "Source: Global Volcanism Program",
      }}
    />
  </>
);
