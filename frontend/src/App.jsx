import { useEffect, useState } from "react";
import { Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const gw = (v, d = 1) => (v == null ? "–" : (v / 1000).toFixed(d) + " GW");
const sgw = (v) => (v > 0 ? "+" : v < 0 ? "−" : "") + gw(Math.abs(v));
const tick = (v) => v / 1000;
const GRID = "var(--grid)";

function useApi(url) {
  const [s, setS] = useState({});
  useEffect(() => {
    let live = true;
    setS((p) => ({ data: p.data, loading: true }));
    fetch(url).then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((data) => live && setS({ data }))
      .catch(() => live && setS({ error: true }));
    return () => { live = false; };
  }, [url]);
  return s;
}

const Kpi = ({ v, label }) => <div className="kpi"><b>{v}</b><small>{label}</small></div>;
const Skeleton = () => <><div className="skel" /><div className="skel" /></>;
const Failed = () => <div className="card err">Couldn’t load data. Check your connection and try again.</div>;
const Legend = ({ items }) => (
  <div className="legend">{items.map(([c, n]) => <span key={n}><i style={{ background: c }} />{n}</span>)}</div>
);
const Tip = ({ active, payload, label, rows }) =>
  active && payload?.length ? (
    <div className="tip"><b>{label}</b>{rows(payload[0].payload).map(([k, v]) => <div key={k}>{k}: {v}</div>)}</div>
  ) : null;
const axes = (x, xfmt, interval) => (
  <>
    <CartesianGrid stroke={GRID} vertical={false} />
    <XAxis dataKey={x} tickFormatter={xfmt} interval={interval} tickLine={false} axisLine={false} />
    <YAxis width={36} tickFormatter={tick} tickLine={false} axisLine={false} />
  </>
);

function Controls({ days, day, setDay, cutoff, setCutoff }) {
  const i = days?.indexOf(day) ?? 0;
  return (
    <div className="card controls">
      {days && (
        <label className="field"><span>Delivery day</span>
          <div className="row">
            <button className="step" aria-label="Previous day" disabled={i <= 0} onClick={() => setDay(days[i - 1])}>‹</button>
            <select value={day} onChange={(e) => setDay(e.target.value)}>
              {days.map((x) => <option key={x} value={x}>{new Date(x + "T12:00Z").toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" })}</option>)}
            </select>
            <button className="step" aria-label="Next day" disabled={i >= days.length - 1} onClick={() => setDay(days[i + 1])}>›</button>
          </div>
        </label>
      )}
      <div className="field"><span>Decide by (day before, UK time)</span>
        <div className="seg">{["05:00", "08:00", "09:50", "12:00"].map((t) => (
          <button key={t} aria-pressed={cutoff === t} className={cutoff === t ? "on" : ""} onClick={() => setCutoff(t)}>{t}</button>
        ))}</div>
        <p className="sub" style={{ margin: "6px 0 0" }}>09:50 is the N2EX day-ahead auction gate closure. Others are what-if scenarios; each picks up a different forecast run (published 04:30, 07:30, 09:30, 11:30).</p>
      </div>
    </div>
  );
}

function Decision({ day, cutoff }) {
  const { data: d, error } = useApi(`/api/decision?day=${day}&cutoff=${cutoff}`);
  if (error) return <Failed />;
  if (!d) return <Skeleton />;
  const pts = d.points.map((p) => ({ ...p, label: p.t.slice(11, 16), band: p.low == null ? null : [p.low, p.high] }));
  const fs = pts.map((p) => p.forecast).filter((v) => v != null);
  const pub = d.forecast_published?.map((x) => x.slice(11, 16));
  const h = d.history;
  return (
    <>
      <div className="card">
        <p className="headline">
          The forecast available at decision time averaged <b>{gw(d.mean_forecast)}</b> of wind.{" "}
          {h.n ? <>Over the {h.days} {h.days === 1 ? "day" : "days"} already settled before this decision, 9 in 10 hours missed by less than <b>{gw(h.p90_abs)}</b>,
            and forecasts ran <em>{gw(Math.abs(h.bias))} too {h.bias > 0 ? "high" : "low"}</em> on average{h.bias > 0 ? ", which points to a shortfall risk." : "."}</>
            : <>There is no settled history in this period yet, so no error range is shown.</>}
        </p>
      </div>
      <div className="kpis">
        <Kpi v={gw(Math.max(...fs))} label="Peak forecast" />
        <Kpi v={gw(Math.min(...fs))} label="Lowest forecast" />
        <Kpi v={pub ? (pub[0] === pub[1] ? pub[0] : pub.join("–")) : "–"} label="Forecast published (UTC, day before)" />
      </div>
      <div className="card">
        <h2>Forecast vs what happened</h2>
        <p className="sub">Hourly wind generation on the delivery day (GW, UTC).</p>
        <Legend items={[["var(--fc)", "Forecast you had"], ["var(--act)", "Actual"], ["var(--band)", "Likely range"]]} />
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart data={pts} margin={{ left: -8, right: 8 }}>
            {axes("label", null, 5)}
            <Tooltip content={<Tip rows={(p) => [["Forecast", gw(p.forecast)], ["Actual", gw(p.actual)], ["Range", `${gw(p.low)} to ${gw(p.high)}`]]} />} />
            <Area dataKey="band" stroke="none" fill="var(--band)" isAnimationActive={false} />
            <Line dataKey="forecast" stroke="var(--fc)" strokeWidth={2.5} dot={false} isAnimationActive={false} />
            <Line dataKey="actual" stroke="var(--act)" strokeWidth={2.5} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
        <p className="sub" style={{ marginTop: 8 }}>Range = forecast ± the 90th-percentile miss from delivery days settled before the decision (no later data is used). Actual = mean of the two half-hour readings in each hour.</p>
      </div>
    </>
  );
}

function Accuracy({ a }) {
  const o = a.overall;
  return (
    <>
      <div className="card">
        <p className="headline">
          Looking back over all January decisions (deliveries 2 Jan – 1 Feb), the forecast available at the cut-off missed by <b>{gw(o.mae)}</b> in a typical hour, and ran <em>{gw(o.bias)} {o.bias > 0 ? "too high" : "too low"}</em> on average.
        </p>
      </div>
      <div className="kpis">
        <Kpi v={gw(o.mae)} label="Typical miss (mean absolute error)" />
        <Kpi v={gw(o.rmse)} label="Big misses weigh more (RMSE)" />
        <Kpi v={sgw(o.bias)} label="Bias: forecast minus actual" />
        <Kpi v={o.mape == null ? "–" : o.mape.toFixed(0) + "%"} label="Miss as share of actual (MAPE)" />
        <Kpi v={gw(o.p90_abs)} label="9 in 10 hours missed by less than" />
      </div>
      <div className="card">
        <h2>Which days were hardest</h2>
        <p className="sub">Typical miss per delivery day (GW).</p>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={a.daily} margin={{ left: -8, right: 8 }}>
            {axes("day", (x) => x.slice(8), 2)}
            <Tooltip cursor={{ fill: "var(--band)" }} content={<Tip rows={(p) => [["Typical miss", gw(p.mae)], ["Bias", sgw(p.bias)]]} />} />
            <Bar dataKey="mae" fill="var(--fc)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="card">
        <h2>Over- or under-forecast by hour</h2>
        <p className="sub">Above zero = forecast too high (risk of under-buying). GW, by hour of delivery day (UTC).</p>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={a.by_hour} margin={{ left: -8, right: 8 }}>
            {axes("hour", null, 3)}
            <ReferenceLine y={0} stroke="var(--mute)" />
            <Tooltip cursor={{ fill: "var(--band)" }} content={<Tip rows={(p) => [["Bias", sgw(p.bias)], ["Typical miss", gw(p.mae)]]} />} />
            <Bar dataKey="bias" radius={[3, 3, 0, 0]} isAnimationActive={false}>
              {a.by_hour.map((p) => <Cell key={p.hour} fill={p.bias > 0 ? "var(--act)" : "var(--fc)"} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="card">
        <h2>Does an earlier forecast do worse?</h2>
        <p className="sub">Typical miss by hours between publish time and target time. Uses every published forecast, not just the one available at the cut-off, so it answers a different question from the charts above.</p>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={a.by_horizon} margin={{ left: -8, right: 8 }}>
            {axes("horizon_h", (h) => (h === 72 ? "72h+" : h + "h"), 0)}
            <Tooltip cursor={{ fill: "var(--band)" }} content={<Tip rows={(p) => [["Typical miss", gw(p.mae)], ["Forecasts", p.n]]} />} />
            <Bar dataKey="mae" fill="var(--fc)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

export default function App() {
  const [tab, setTab] = useState("decision");
  const [cutoff, setCutoff] = useState("09:50");
  const [day, setDay] = useState("2026-01-15");
  const [dark, setDark] = useState(() => { try { return localStorage.getItem("theme") === "dark"; } catch { return false; } });
  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    try { localStorage.setItem("theme", dark ? "dark" : "light"); } catch {}
  }, [dark]);
  const { data: days } = useApi("/api/days");
  const { data: acc, error } = useApi(`/api/accuracy?cutoff=${cutoff}`);
  return (
    <>
      <header className="top">
        <div className="head"><div><h1>Wind Forecast Desk</h1><p>GB day-ahead · January 2026</p></div>
          <button className="theme" aria-label={dark ? "Switch to light theme" : "Switch to dark theme"} onClick={() => setDark(!dark)}>{dark ? "☀" : "☾"}</button></div>
        <nav>
          {[["decision", "Plan a day"], ["accuracy", "How accurate"]].map(([k, n]) => (
            <button key={k} aria-pressed={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{n}</button>
          ))}
        </nav>
      </header>
      <main>
        <Controls days={tab === "decision" ? days : null} day={day} setDay={setDay} cutoff={cutoff} setCutoff={setCutoff} />
        {tab === "decision" ? <Decision day={day} cutoff={cutoff} /> : error ? <Failed /> : acc ? <Accuracy a={acc} /> : <Skeleton />}
      </main>
    </>
  );
}
