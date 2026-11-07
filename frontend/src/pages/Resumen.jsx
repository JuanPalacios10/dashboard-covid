import AgeBars from '../components/charts/AgeBars.jsx';
import Heatmap from '../components/charts/Heatmap.jsx';
import SexDonut from '../components/charts/SexDonut.jsx';
import TerritorialBars from '../components/charts/TerritorialBars.jsx';
import TrendCard from '../components/charts/TrendCard.jsx';
import Card from '../components/ui/Card.jsx';

export default function Resumen({ data, loading, error, terr, terrName }) {
  if (!data && loading) {
    return (
      <div className="main">
        <Card className="span2" title="Cargando tablero">
          <p className="note">Consultando agregados precalculados en MongoDB…</p>
        </Card>
      </div>
    );
  }

  if (!data && error) {
    return (
      <div className="main">
        <Card className="span2" title="Tablero no disponible">
          <p className="note" role="alert">
            {error}
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="main" aria-busy={loading}>
      {loading && <p className="note span2">Actualizando período…</p>}
      <TrendCard
        series={data.series}
        periodo={data.periodo}
        anio={data.anio}
        terrName={terrName}
      />
      <div className="grid2">
        <TerritorialBars
          territorios={data.territorios}
          periodo={data.periodo}
          terr={terr}
        />
        <Heatmap heatmap={data.heatmap} periodo={data.periodo} terr={terr} />
      </div>
      <div className="grid3">
        <SexDonut demografia={data.demografia} periodo={data.periodo} anio={data.anio} />
        <AgeBars demografia={data.demografia} periodo={data.periodo} anio={data.anio} />
      </div>
    </div>
  );
}
