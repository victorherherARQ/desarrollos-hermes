import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { WeightPoint } from '../types';

type Props = {
  data: WeightPoint[];
  periodDays: number;
};

export function WeightChart({ data, periodDays }: Props) {
  if (data.length === 0) {
    return <p className="empty">Sin datos en los últimos {periodDays} días.</p>;
  }

  const values = data.map((p) => p.value);
  const dataMin = Math.min(...values);
  const dataMax = Math.max(...values);
  const yDomain: [number, number] = [
    Math.floor(dataMin - 2),
    Math.ceil(dataMax + 2),
  ];

  return (
    <div>
      <h3>Peso (kg) — últimos {periodDays} días</h3>
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={data} margin={{ top: 16, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" />
          <YAxis domain={yDomain} />
          <Tooltip />
          <Line type="monotone" dataKey="value" stroke="#8884d8" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}