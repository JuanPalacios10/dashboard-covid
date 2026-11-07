import { useState } from 'react';
import Card from '../components/ui/Card.jsx';
import { useAuth } from '../context/auth.js';
import { informesApi } from '../utils/api.js';

export default function Informes({ anio, departamento, terrName, toast }) {
  const { token } = useAuth();
  const [dest, setDest] = useState('Consejo de gobierno');
  const [incl, setIncl] = useState(true);
  const [downloading, setDownloading] = useState(false);

  const handleExportPdf = async () => {
    if (!token) {
      toast('Debes iniciar sesión como ejecutivo para exportar el informe.');
      return;
    }

    try {
      setDownloading(true);
      const blob = await informesApi.exportPdf(token, {
        destino: dest,
        territorio: terrName,
        anio: anio ?? 'acumulado',
        departamento: departamento ?? null,
        incluir_proyeccion: incl,
      });

      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'informe-epidemiologico.pdf';
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      toast('Informe PDF descargado con éxito.');
    } catch (error) {
      console.error(error);
      toast('No se pudo generar el PDF. Verifica que el backend esté disponible y que tengas permisos.');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="rep">
      <Card title="Informe oficial" sub="Resumen gerencial en PDF">
        <div className="field">
          <label htmlFor="dest" className="flabel">
            Dirigido a
          </label>
          <select id="dest" value={dest} onChange={(e) => setDest(e.target.value)}>
            <option>Consejo de gobierno</option>
            <option>Comité de emergencia</option>
          </select>
        </div>
        <div className="field">
          <span className="flabel">Territorio</span>
          <span>{terrName}</span>
        </div>
        <label className="chk" htmlFor="incl">
          <input id="incl" type="checkbox" checked={incl} onChange={(e) => setIncl(e.target.checked)} />
          Incluir proyección a 30 días
        </label>
        <button className="btn" onClick={handleExportPdf} disabled={downloading}>
          {downloading ? 'Generando PDF…' : 'Exportar PDF'}
        </button>
        <p className="hint" style={{ marginTop: 10 }}>
          El PDF oficial se genera con el estado actual del dashboard y la firma institucional del
          backend.
        </p>
      </Card>
    </div>
  );
}
