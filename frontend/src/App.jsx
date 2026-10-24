import { useEffect, useState } from "react";
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const MW = (v) => (v == null ? "–" : Math.round(v).toLocaleString() + " MW");
const hh = (t) => t.slice(11, 16);
const GW = (v) => v / 1000 + " GW";
const useApi = (url) => {
  const [d, setD] = useState();
  useEffect(() => { setD(undefined); fetch(url).then((r) => r.json()).then(setD); }, [url]);
  return d;
};
const Kpi = ({ v, label }) => <div className="kpi"><b>{v}</b><span>{label}</span></div>;
const Bars = ({ data, x, xfmt, bars, h = 240 }) => (
  <ResponsiveContainer width="100%" height={h}><BarChart data={data}>
    <CartesianGrid stroke="#e3e7ec" /><XAxis dataKey={x} tickFormatter={xfmt} /><YAxis width={60} tickFormatter={GW} /><Tooltip formatter={MW} />
    {bars.map(([k, name, fill]) => <Bar key={k} dataKey={k} name={name} fill={fill} />)}
  </BarChart></ResponsiveContainer>
);

function Decision({ cutoff }) {
  const days = useApi("/api/days");
  const [day, setDay] = useState("2026-01-15");
  const d = useApi(`/api/decision?day=${day}&cutoff_hour=${cutoff}`);
  const pts = d?.points.map((p) => ({ ...p, label: hh(p.t), band: p.low == null ? null : [p.low, p.high] }));
  const fs = pts?.map((p) => p.forecast).filter((v) => v != null) ?? [];
  return (
    <>
      <div className="card">
        <label>Delivery day
          <select value={day} onChange={(e) => setDay(e.target.value)}>{days?.map((x) => <option key={x}>{x}</option>)}</select>
        </label>
        {d && <p className="note">Decision made by {d.cutoff.replace("T", " ").replace("Z", " UTC")}.
          {d.forecast_published && ` Forecasts used were published ${d.forecast_published.map((x) => x.replace("T", " ").slice(0, 16)).join(" → ")} UTC.`}</p>}
      </div>
      {d && <>
        <div className="kpis">
          <Kpi v={MW(d.mean_forecast)} label="Avg forecast wind, delivery day" />
          <Kpi v={"± " + MW(d.p90_abs_error)} label="Error buffer (90% of past hours within)" />
          <Kpi v={MW(Math.max(...fs))} label="Peak forecast" />
          <Kpi v={MW(Math.min(...fs))} label="Lowest forecast" />
        </div>
        <div className="card"><h2>Latest available forecast vs actual</h2>
          <ResponsiveContainer width="100%" height={300}><ComposedChart data={pts}>
            <CartesianGrid stroke="#e3e7ec" /><XAxis dataKey="label" /><YAxis width={60} tickFormatter={GW} /><Tooltip />
            <Area dataKey="band" name="Forecast ± buffer" fill="#0b6e99" stroke="none" fillOpacity={0.15} />
            <Line dataKey="forecast" name="Forecast at decision time" stroke="#0b6e99" strokeWidth={2} dot={false} />
            <Line dataKey="actual" name="Actual (known after the fact)" stroke="#d1495b" strokeWidth={2} dot={false} />
          </ComposedChart></ResponsiveContainer>
          <p className="note">Plan thermal purchases against the lower edge of the band to cover wind under-delivery. The band is the 90th-percentile absolute error over all of January (in-sample).</p>
        </div>
      </>}
    </>
  );
}

function Accuracy({ cutoff }) {
  const a = useApi(`/api/accuracy?cutoff_hour=${cutoff}`);
  if (!a) return <p>Loading…</p>;
  const o = a.overall;
  return (
    <>
      <div className="kpis">
        <Kpi v={MW(o.mae)} label="MAE (mean absolute error)" />
        <Kpi v={MW(o.rmse)} label="RMSE" />
        <Kpi v={(o.bias > 0 ? "+" : "") + MW(o.bias)} label="Bias (forecast − actual)" />
        <Kpi v={o.mape.toFixed(1) + " %"} label="MAPE" />
        <Kpi v={MW(o.p90_abs)} label="P90 absolute error" />
      </div>
      <div className="card"><h2>Daily MAE</h2>
        <Bars data={a.daily} x="day" xfmt={(x) => x.slice(8)} bars={[["mae", "MAE", "#0b6e99"]]} /></div>
      <div className="card"><h2>Error by hour of delivery day</h2>
        <Bars data={a.by_hour} x="hour" bars={[["bias", "Bias", "#d1495b"], ["mae", "MAE", "#0b6e99"]]} />
        <p className="note">Positive bias = forecast above actual (over-forecasting wind, i.e. risk of under-buying).</p></div>
      <div className="card"><h2>MAE by forecast horizon (hours between publish and target)</h2>
        <Bars data={a.by_horizon} x="horizon_h" xfmt={(h) => (h === 72 ? "72+" : h + "–" + (h + 6))} bars={[["mae", "MAE", "#0b6e99"]]} /></div>
    </>
  );
}

export default function App() {
  const [tab, setTab] = useState("decision");
  const [cutoff, setCutoff] = useState(9);
  return (
    <>
      <header>
        <h1>Wind Forecast Desk · GB day-ahead</h1>
        {[["decision", "Decision view"], ["accuracy", "Forecast accuracy"]].map(([k, n]) => (
          <button key={k} className={"tab" + (tab === k ? " on" : "")} onClick={() => setTab(k)}>{n}</button>
        ))}
        <label style={{ marginLeft: "auto" }}>Decision cut-off (UTC hour, day before)
          <input type="number" min="0" max="23" value={cutoff} onChange={(e) => setCutoff(Math.min(23, Math.max(0, +e.target.value || 0)))} style={{ width: 56 }} />
        </label>
      </header>
      <main>{tab === "decision" ? <Decision cutoff={cutoff} /> : <Accuracy cutoff={cutoff} />}</main>
    </>
  );
}
