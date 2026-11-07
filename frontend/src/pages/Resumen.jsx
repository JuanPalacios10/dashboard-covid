import AgeBars from '../components/charts/AgeBars.jsx';
import Heatmap from '../components/charts/Heatmap.jsx';
import SexDonut from '../components/charts/SexDonut.jsx';
import TerritorialBars from '../components/charts/TerritorialBars.jsx';
import TrendCard from '../components/charts/TrendCard.jsx';

export default function Resumen({ view, range, terr }) {
  return (
    <div className="main">
      <TrendCard view={view} range={range} />
      <div className="grid2">
        <TerritorialBars range={range} terr={terr} />
        <Heatmap terr={terr} />
      </div>
      <div className="grid3">
        <SexDonut view={view} range={range} />
        <AgeBars view={view} range={range} />
      </div>
    </div>
  );
}
