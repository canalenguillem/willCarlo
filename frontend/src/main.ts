import "./style.css";
import {
  api,
  type BracketResponse,
  type BracketTie,
  type GroupProjTeam,
  type GroupRoute,
  type MatchFixture,
  type ThirdSlot,
  type MatchPrediction,
  type Prediction,
  type RealBracketResponse,
  type RealGroup,
  type RealSlot,
  type RealTie,
  type Team,
  type TournamentResponse,
  type TournamentTeam,
} from "./api";

// --------------------------------------------------------------------------- //
// Estado
// --------------------------------------------------------------------------- //
let teams: Team[] = [];
let view: "lab" | "tournament" | "bracket" | "real" = "real";
let realSub: "groups" | "bracket" | "forecast" | "projection" = "groups";
let realState: RealBracketResponse | null = null;
let realMatches: MatchFixture[] = [];
let realPredictions = new Map<string, MatchPrediction>();
let groupProj = new Map<string, GroupProjTeam[]>();
let groupRoutes = new Map<string, { first?: GroupRoute; second?: GroupRoute }>();
let thirdSlots: Record<string, ThirdSlot> = {};
let groupProjSims = 0;
let realForecast: TournamentResponse | null = null;
let realProjection: BracketResponse | null = null;

const app = document.querySelector<HTMLDivElement>("#app")!;

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;
const escape = (s: string) =>
  s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]!));

// --------------------------------------------------------------------------- //
// Layout
// --------------------------------------------------------------------------- //
function shell(inner: string): string {
  return `
    <header class="masthead">
      <div class="brand">
        <h1>WillCarlo<span class="dot">.</span></h1>
        <span class="sub">Mundial 2026 &middot; escalera de modelos</span>
      </div>
      <nav class="tabs">
        <button class="tab ${view === "real" ? "active" : ""}" data-view="real">Real</button>
      </nav>
    </header>
    <main>${inner}</main>`;
}

function render(inner: string) {
  app.innerHTML = shell(inner);
  app.querySelectorAll<HTMLButtonElement>(".tab").forEach((btn) =>
    btn.addEventListener("click", () => {
      view = btn.dataset.view as typeof view;
      if (view === "lab") renderLab();
      else if (view === "tournament") renderTournament();
      else if (view === "bracket") renderBracket();
      else renderReal();
    })
  );
}

// --------------------------------------------------------------------------- //
// Vista: Laboratorio (comparar dos equipos)
// --------------------------------------------------------------------------- //
function teamOptions(selected?: string): string {
  return teams
    .map((t) => `<option value="${t.id}" ${t.id === selected ? "selected" : ""}>${escape(t.name)}</option>`)
    .join("");
}

function renderLab() {
  const defaultHome = teams.find((t) => t.id === "argentina")?.id ?? teams[0]?.id;
  const defaultAway = teams.find((t) => t.id === "france")?.id ?? teams[1]?.id;
  render(`
    <section class="panel">
      <h2>Laboratorio</h2>
      <p class="hint">Compar&aacute; dos selecciones a trav&eacute;s de toda la escalera. El or&aacute;culo elige el escal&oacute;n usable m&aacute;s alto.</p>
      <div class="controls">
        <div class="field">
          <label>Equipo A (local)</label>
          <select id="home">${teamOptions(defaultHome)}</select>
        </div>
        <div class="field">
          <label>Equipo B (visitante)</label>
          <select id="away">${teamOptions(defaultAway)}</select>
        </div>
        <label class="checkbox"><input type="checkbox" id="neutral" checked /> Cancha neutral</label>
        <button class="go" id="run">Predecir</button>
      </div>
    </section>
    <div id="result"></div>`);

  app.querySelector<HTMLButtonElement>("#run")!.addEventListener("click", runLab);
}

async function runLab() {
  const home = app.querySelector<HTMLSelectElement>("#home")!.value;
  const away = app.querySelector<HTMLSelectElement>("#away")!.value;
  const neutral = app.querySelector<HTMLInputElement>("#neutral")!.checked;
  const slot = app.querySelector<HTMLDivElement>("#result")!;

  if (home === away) {
    slot.innerHTML = `<div class="panel"><p class="error">Eleg&iacute; dos equipos distintos.</p></div>`;
    return;
  }
  slot.innerHTML = `<div class="panel"><p class="empty">Consultando al or&aacute;culo&hellip;</p></div>`;

  try {
    const res = await api.lab(home, away, neutral);
    const f = res.final;
    const xg =
      f.expected_home_goals != null
        ? `<span class="xg">${f.expected_home_goals.toFixed(2)} : ${f.expected_away_goals!.toFixed(2)}</span>`
        : `<span class="vs">vs</span>`;

    slot.innerHTML = `
      <section class="panel">
        <div class="scoreline">
          <div class="team">${escape(res.home.name)}</div>
          ${xg}
          <div class="team away">${escape(res.away.name)}</div>
        </div>
        ${outcomeBar(f)}
        <div class="ladder">
          ${res.ladder.map((p) => rung(p)).join("")}
          ${rung(f, true)}
        </div>
        <p class="explain">${escape(f.explanation)}</p>
      </section>`;
  } catch (e) {
    slot.innerHTML = `<div class="panel"><p class="error">No se pudo predecir: ${escape(String(e))}</p></div>`;
  }
}

function outcomeBar(p: Prediction): string {
  const o = p.outcome;
  return `
    <div class="bar">
      <div class="home" style="flex-basis:${o.home_win * 100}%">${o.home_win > 0.08 ? pct(o.home_win) : ""}</div>
      <div class="draw" style="flex-basis:${o.draw * 100}%">${o.draw > 0.08 ? pct(o.draw) : ""}</div>
      <div class="away" style="flex-basis:${o.away_win * 100}%">${o.away_win > 0.08 ? pct(o.away_win) : ""}</div>
    </div>
    <div class="bar-key"><span>Gana A</span><span>Empate</span><span>Gana B</span></div>`;
}

function rung(p: Prediction, isFinal = false): string {
  const o = p.outcome;
  const tag = p.degraded && !isFinal ? `<span class="tag">degradado</span>` : "";
  const idx = isFinal ? "&#9733;" : String(p.predictor_priority);
  return `
    <div class="rung ${p.degraded && !isFinal ? "degraded" : ""} ${isFinal ? "final" : ""}">
      <div class="idx">${idx}</div>
      <div class="name">${escape(p.predictor_name)}${tag}
        ${isFinal ? "" : `<small>${escape(p.explanation)}</small>`}
      </div>
      <div class="probs">
        <b>${pct(o.home_win)}</b> &middot; ${pct(o.draw)} &middot; ${pct(o.away_win)}
      </div>
    </div>`;
}

// --------------------------------------------------------------------------- //
// Vista: Torneo (simulaci&oacute;n Montecarlo)
// --------------------------------------------------------------------------- //
function renderTournament() {
  render(`
    <section class="panel">
      <h2>Simulaci&oacute;n del torneo</h2>
      <p class="hint">Corre el Mundial completo muchas veces (fase de grupos + eliminaci&oacute;n con el cuadro real de 2026) y promedia los resultados.</p>
      <div class="controls">
        <div class="field">
          <label>Simulaciones</label>
          <input type="number" id="sims" value="5000" min="100" max="50000" step="500" />
        </div>
        <div class="field">
          <label>Semilla</label>
          <input type="number" id="seed" value="2026" />
        </div>
        <button class="go" id="run">Correr</button>
      </div>
    </section>
    <div id="result"></div>`);

  app.querySelector<HTMLButtonElement>("#run")!.addEventListener("click", runTournament);
}

async function runTournament() {
  const sims = parseInt(app.querySelector<HTMLInputElement>("#sims")!.value, 10);
  const seed = parseInt(app.querySelector<HTMLInputElement>("#seed")!.value, 10);
  const slot = app.querySelector<HTMLDivElement>("#result")!;
  const btn = app.querySelector<HTMLButtonElement>("#run")!;

  btn.disabled = true;
  slot.innerHTML = `<div class="panel"><p class="empty">Simulando ${sims.toLocaleString("es")} torneos&hellip; (puede tardar unos segundos)</p></div>`;

  try {
    const res = await api.runTournament(sims, Number.isNaN(seed) ? null : seed);
    slot.innerHTML = `
      <section class="panel">
        <table>
          <thead>
            <tr>
              <th class="rank">#</th>
              <th class="team">Equipo</th>
              <th>Gr.</th>
              <th>Campe&oacute;n</th>
              <th class="hide">Final</th>
              <th class="hide">Semis</th>
              <th>Clasifica</th>
              <th class="hide">Pts grupo</th>
            </tr>
          </thead>
          <tbody>${res.teams.map(row).join("")}</tbody>
        </table>
        <p class="meta">${res.simulations.toLocaleString("es")} simulaciones &middot; semilla ${res.seed ?? "&mdash;"} &middot; ${res.elapsed_ms} ms</p>
      </section>`;
  } catch (e) {
    slot.innerHTML = `<div class="panel"><p class="error">No se pudo simular: ${escape(String(e))}</p></div>`;
  } finally {
    btn.disabled = false;
  }
}

function row(t: TournamentTeam, i: number): string {
  return `
    <tr>
      <td class="rank">${i + 1}</td>
      <td class="team">${escape(t.name)}</td>
      <td><span class="grp">${t.group}</span></td>
      <td class="champ">${pct(t.win_tournament)}</td>
      <td class="hide">${pct(t.reach_final)}</td>
      <td class="hide">${pct(t.reach_semi_final)}</td>
      <td>${pct(t.qualify)}</td>
      <td class="hide">${t.expected_group_points.toFixed(2)}</td>
    </tr>`;
}

// --------------------------------------------------------------------------- //
// Vista: Cuadro (una corrida jugada, árbol de llaves)
// --------------------------------------------------------------------------- //
function renderBracket() {
  render(`
    <section class="panel">
      <h2>Cuadro m&aacute;s probable</h2>
      <p class="hint">Proyecci&oacute;n del cuadro completo a partir de lo ya jugado: los clasificados m&aacute;s probables de cada grupo y, en cada llave, el <b>favorito</b> con su probabilidad de pasar. No es una tirada al azar (para eso, Real &rarr; Proyecci&oacute;n).</p>
      <div class="controls">
        <div class="field">
          <label>Simulaciones</label>
          <input type="number" id="bsims" value="5000" min="500" max="50000" step="500" />
        </div>
        <button class="go" id="run">Calcular</button>
      </div>
    </section>
    <div id="result"><div class="panel"><p class="empty">Calculando el cuadro m&aacute;s probable&hellip;</p></div></div>`);

  app.querySelector<HTMLButtonElement>("#run")!.addEventListener("click", playBracket);
  playBracket();
}

async function playBracket() {
  const sims = parseInt(app.querySelector<HTMLInputElement>("#bsims")!.value, 10);
  const slot = app.querySelector<HTMLDivElement>("#result")!;
  const btn = app.querySelector<HTMLButtonElement>("#run")!;

  btn.disabled = true;
  slot.innerHTML = `<div class="panel"><p class="empty">Calculando el cuadro m&aacute;s probable&hellip;</p></div>`;

  try {
    const res = await api.likelyBracket(Number.isNaN(sims) ? null : sims);
    slot.innerHTML = renderCuadro(res);
  } catch (e) {
    slot.innerHTML = `<div class="panel"><p class="error">No se pudo calcular el cuadro: ${escape(String(e))}</p></div>`;
  } finally {
    btn.disabled = false;
  }
}

// Ordena cada ronda siguiendo el árbol desde la final (DFS local-luego-visitante),
// para que las llaves de columnas contiguas queden alineadas verticalmente.
function bracketColumns(res: BracketResponse): BracketTie[][] {
  const ko = res.knockout;
  const byId = new Map<number, BracketTie>();
  [...ko.round_of_32, ...ko.round_of_16, ...ko.quarter_finals, ...ko.semi_finals, ko.final].forEach((t) =>
    byId.set(t.tie_id, t)
  );
  const rounds: BracketTie[][] = [[], [], [], [], []]; // 0=final ... 4=R32
  const feederId = (label: string) => (label.startsWith("W") ? parseInt(label.slice(1), 10) : null);

  const walk = (tie: BracketTie, depth: number) => {
    rounds[depth].push(tie);
    for (const lab of [tie.home.label, tie.away.label]) {
      const id = feederId(lab);
      if (id != null && byId.has(id)) walk(byId.get(id)!, depth + 1);
    }
  };
  walk(ko.final, 0);
  return [rounds[4], rounds[3], rounds[2], rounds[1], rounds[0]]; // izq->der: R32..Final
}

const STAGE_TITLES: Record<string, string> = {
  RoundOf32: "Dieciseisavos",
  RoundOf16: "Octavos",
  QuarterFinal: "Cuartos",
  SemiFinal: "Semis",
  Final: "Final",
};

function tieCard(t: BracketTie): string {
  const homeWon = t.winner_id === t.home.team_id;
  // Marcador si es una corrida; si es el cuadro "más probable", la prob. del ganador.
  const cell = (score: number | null, won: boolean) =>
    score != null
      ? `${score}`
      : won && t.win_prob != null
      ? `<span class="bk-wp">${Math.round(t.win_prob * 100)}%</span>`
      : "";
  const slot = (s: BracketTie["home"], score: number | null, won: boolean) => `
    <div class="bk-slot ${won ? "win" : "out"}">
      <span class="bk-lab">${escape(s.label)}</span>
      <span class="bk-nm">${escape(s.name)}</span>
      <span class="bk-sc">${cell(score, won)}</span>
    </div>`;
  return `
    <div class="bk-tie">
      ${slot(t.home, t.home_score, homeWon)}
      ${slot(t.away, t.away_score, !homeWon)}
      ${t.penalties ? `<span class="bk-pen">pen.</span>` : ""}
    </div>`;
}

function renderCuadro(res: BracketResponse): string {
  const cols = bracketColumns(res);
  const columns = cols
    .map((ties) => {
      const stage = ties[0]?.stage ?? "";
      return `
        <div class="bk-col">
          <div class="bk-head">${STAGE_TITLES[stage] ?? stage}</div>
          <div class="bk-col-body">${ties.map(tieCard).join("")}</div>
        </div>`;
    })
    .join("");

  return `
    <section class="panel">
      <div class="bk-champ">
        <span class="bk-champ-lab">&#127942; Campe&oacute;n</span>
        <span class="bk-champ-name">${escape(res.champion.name)}</span>
      </div>
      <div class="bk-board">
        ${columns}
      </div>
      <p class="meta">${
        res.simulations != null
          ? `Cuadro m&aacute;s probable &middot; ${res.simulations.toLocaleString("es")} simulaciones`
          : `Una corrida &middot; semilla ${res.seed ?? "aleatoria"}`
      } &middot; ${res.elapsed_ms} ms</p>
    </section>`;
}

// --------------------------------------------------------------------------- //
// Vista: Real (carga manual de resultados -> cuadro real)
// --------------------------------------------------------------------------- //
function renderReal() {
  render(`
    <section class="panel">
      <h2>Seguimiento real</h2>
      <p class="hint">Carg&aacute; los marcadores reales o tra&eacute;los con un clic. Se actualiza solo cada minuto (finalizados y en vivo). La fase de grupos define las posiciones.</p>
      <div class="real-top">
        <nav class="subtabs">
          <button class="subtab ${realSub === "groups" ? "active" : ""}" data-sub="groups">Fase de grupos</button>
          <button class="subtab ${realSub === "bracket" ? "active" : ""}" data-sub="bracket">Cuadro real</button>
          <button class="subtab ${realSub === "forecast" ? "active" : ""}" data-sub="forecast">Pron&oacute;stico</button>
          <button class="subtab ${realSub === "projection" ? "active" : ""}" data-sub="projection">Cuadro probable</button>
        </nav>
        <button class="go" id="refresh">&#8635; Buscar resultados</button>
      </div>
      <p id="refresh-msg" class="meta"></p>
    </section>
    <div id="real-body"><div class="panel"><p class="empty">Cargando&hellip;</p></div></div>`);

  app.querySelectorAll<HTMLButtonElement>(".subtab").forEach((b) =>
    b.addEventListener("click", () => {
      realSub = b.dataset.sub as typeof realSub;
      paintReal();
    })
  );
  app.querySelector<HTMLButtonElement>("#refresh")!.addEventListener("click", refreshResults);
  loadReal();
  startAutoPoll();
}

// Refresco automático cada 60 s mientras se ve la pestaña Real, sin pisar al usuario
// si está escribiendo un marcador (foco en un input/select).
let autoPollStarted = false;
function startAutoPoll() {
  if (autoPollStarted) return;
  autoPollStarted = true;
  window.setInterval(() => {
    if (view !== "real") return;
    const ae = document.activeElement;
    if (ae && (ae.tagName === "INPUT" || ae.tagName === "SELECT")) return;
    loadReal();
  }, 60000);
}

async function refreshResults() {
  const btn = app.querySelector<HTMLButtonElement>("#refresh")!;
  const msg = app.querySelector<HTMLParagraphElement>("#refresh-msg")!;
  btn.disabled = true;
  msg.className = "meta";
  msg.textContent = "Consultando la fuente de resultados…";
  try {
    const r = await api.refreshResults();
    [realMatches, realState] = await Promise.all([api.matches(), api.realBracket()]);
    paintReal();
    const parts = [`${r.updated.length} finalizados`, `${r.live.length} en vivo`];
    if (r.unmatched.length) parts.push(`${r.unmatched.length} sin emparejar`);
    msg.textContent = `Actualizado: ${parts.join(" · ")}.${r.live.length ? " En vivo: " + r.live.join(", ") : ""}`;
  } catch (e) {
    msg.className = "error";
    msg.textContent = `No se pudo buscar: ${escape(String(e))}`;
  } finally {
    btn.disabled = false;
  }
}

async function loadReal() {
  try {
    await api.refreshResults().catch(() => {}); // trae lo último (finalizados/en vivo) de la fuente
    [realMatches, realState] = await Promise.all([api.matches(), api.realBracket()]);
    if (realPredictions.size === 0) {
      const preds = await api.matchPredictions();
      realPredictions = new Map(preds.map((p) => [p.id, p]));
    }
    paintReal();
  } catch (e) {
    const body = app.querySelector<HTMLDivElement>("#real-body");
    if (body) body.innerHTML = `<div class="panel"><p class="error">No se pudo cargar: ${escape(String(e))}</p></div>`;
  }
}

function paintReal() {
  app.querySelectorAll<HTMLButtonElement>(".subtab").forEach((b) =>
    b.classList.toggle("active", b.dataset.sub === realSub)
  );
  const body = app.querySelector<HTMLDivElement>("#real-body");
  if (!body || !realState) return;
  if (realSub === "groups") {
    body.innerHTML = groupsSection();
    wireGroupInputs();
  } else if (realSub === "bracket") {
    body.innerHTML = bracketSection(realState);
    wireBracketInputs();
  } else if (realSub === "forecast") {
    body.innerHTML = forecastSection();
    wireForecast();
  } else {
    body.innerHTML = projectionSection();
    wireProjection();
  }
}

function groupsSection(): string {
  const byGroup = new Map<string, MatchFixture[]>();
  for (const m of realMatches) {
    if (!byGroup.has(m.group)) byGroup.set(m.group, []);
    byGroup.get(m.group)!.push(m);
  }
  const cards = [...byGroup.keys()]
    .sort()
    .map((g) => {
      const standing = realState!.groups.find((x) => x.name === g);
      return `
        <section class="panel grp-card">
          <h3>Grupo ${g}${standing?.complete ? ` <span class="grp-done">completo</span>` : ""}</h3>
          <div class="grp-grid">
            <div class="fixtures">${byGroup.get(g)!.map(fixtureRow).join("")}</div>
            ${standing ? standTable(standing) : ""}
          </div>
          ${groupProjBlock(g)}
        </section>`;
    })
    .join("");

  return `
    <section class="panel">
      <div class="real-top">
        <p class="hint" style="margin:0">Proyect&aacute; la clasificaci&oacute;n final de cada grupo: fija lo ya jugado y simula los partidos que faltan.</p>
        <div class="gsim-ctl">
          <input type="number" id="gsims" value="3000" min="500" max="20000" step="500" class="fx-score" />
          <button class="go" id="gsim">Simular clasificaci&oacute;n</button>
        </div>
      </div>
    </section>
    ${cards}`;
}

function groupProjBlock(name: string): string {
  const teams = groupProj.get(name);
  if (!teams) return "";
  const seg = (w: number, cls: string, label: string) =>
    w > 0 ? `<span class="${cls}" style="width:${(w * 100).toFixed(1)}%" title="${label} ${pct(w)}"></span>` : "";
  const bars = teams
    .map(
      (t) => `
        <div class="proj-row">
          <span class="proj-nm">${escape(t.name)}</span>
          <div class="proj-bar">
            ${seg(t.p_pos[0], "p1", "1&ordm;")}${seg(t.p_pos[1], "p2", "2&ordm;")}${seg(t.p_pos[2], "p3", "3&ordm;")}${seg(t.p_pos[3] ?? 0, "p4", "4&ordm;")}
          </div>
          <span class="proj-q">${pct((t.p_pos[0] ?? 0) + (t.p_pos[1] ?? 0))}</span>
        </div>`
    )
    .join("");

  return `
    <div class="grp-proj">
      <div class="grp-proj-grid">
        <div class="grp-proj-bars">
          <div class="grp-proj-head">Clasificaci&oacute;n final proyectada &middot; ${groupProjSims.toLocaleString("es")} sims</div>
          ${bars}
          <div class="proj-legend"><i class="p1"></i>1&ordm; <i class="p2"></i>2&ordm; <i class="p3"></i>3&ordm; <i class="p4"></i>4&ordm; &middot; der.: clasifica directo</div>
        </div>
        ${routesBox(name, teams)}
      </div>
    </div>`;
}

// Caja de cruces de dieciseisavos: a qué llave van el 1º y el 2º proyectados.
function routesBox(name: string, teams: GroupProjTeam[]): string {
  const routes = groupRoutes.get(name);
  if (!routes) return "";
  const line = (posLabel: string, team: GroupProjTeam | undefined, route?: GroupRoute) =>
    team && route
      ? `
        <div class="route-row">
          <div class="route-side"><span class="route-pos">${posLabel}</span> <span class="route-team">${escape(team.name)}</span></div>
          <div class="route-vs">vs ${escape(resolveOpponent(route.opponent))}</div>
          <div class="route-tie">cruce ${route.tie_id}</div>
          ${thirdDist(route.tie_id)}
        </div>`
      : "";
  return `
    <div class="grp-routes">
      <div class="grp-proj-head">Dieciseisavos de final</div>
      ${line(`1&ordm; ${name}`, teams[0], routes.first)}
      ${line(`2&ordm; ${name}`, teams[1], routes.second)}
    </div>`;
}

// Distribución del tercero que caería en este cruce (solo cruces ganador-vs-3º).
function thirdDist(tieId: number): string {
  const d = thirdSlots[String(tieId)];
  if (!d) return "";
  const groups = d.by_group.map((x) => `3&ordm;${x.group} ${pct(x.p)}`).join(" &middot; ");
  const top = d.by_team[0];
  const topNote = top ? `<div class="route-top">m&aacute;s prob.: ${escape(top.name)} ${pct(top.p)}</div>` : "";
  return `<div class="route-dist">${groups}</div>${topNote}`;
}

// "2º B" -> "2º B (Canada)" usando la proyección de ese grupo, si está disponible.
function resolveOpponent(label: string): string {
  const m = label.match(/^([12])º\s+([A-L])$/);
  if (m) {
    const t = groupProj.get(m[2]);
    const team = t?.[m[1] === "1" ? 0 : 1];
    if (team) return `${label} (${team.name})`;
  }
  return label;
}

function fixtureRow(m: MatchFixture): string {
  const live = m.status === "live" ? `<span class="fx-live">vivo</span>` : "";
  return `
    <div class="fx-wrap">
      <div class="fx ${m.status === "live" ? "is-live" : ""}" data-fixture="${escape(m.id)}">
        <span class="fx-team home">${escape(m.home.name)}</span>
        <input class="fx-score" type="number" min="0" data-side="home" value="${m.home_goals ?? ""}" />
        <span class="fx-sep">:</span>
        <input class="fx-score" type="number" min="0" data-side="away" value="${m.away_goals ?? ""}" />
        <span class="fx-team away">${escape(m.away.name)} ${live}</span>
        <button class="fx-save" data-fixture="${escape(m.id)}">Guardar</button>
      </div>
      ${predLine(m)}
    </div>`;
}

// Línea de pronóstico del oráculo bajo cada partido: 1-X-2 + marcador probable.
function predLine(m: MatchFixture): string {
  const p = realPredictions.get(m.id);
  if (!p) return "";
  const sc = p.most_likely_score;
  const score = sc
    ? `${sc[0]}&ndash;${sc[1]}`
    : p.expected_home_goals != null
    ? `${Math.round(p.expected_home_goals)}&ndash;${Math.round(p.expected_away_goals!)}`
    : "&mdash;";
  const xg =
    p.expected_home_goals != null
      ? ` &middot; <span class="fx-xg">xg ${p.expected_home_goals.toFixed(2)}&ndash;${p.expected_away_goals!.toFixed(2)}</span>`
      : "";
  return `
    <div class="fx-pred" title="Probabilidad de que gane el local, empate, o gane el visitante (oráculo, cancha neutral)">
      <b>${pct(p.home_win)}</b> &middot; ${pct(p.draw)} &middot; <b>${pct(p.away_win)}</b>
      &middot; prob. <b>${score}</b>${xg}
    </div>`;
}

function standTable(g: RealGroup): string {
  return `
    <table class="stand">
      <thead><tr><th>#</th><th>Equipo</th><th>Pts</th><th>DG</th></tr></thead>
      <tbody>
        ${g.standings
          .map(
            (s) => `
          <tr class="${s.position <= 2 ? "qual" : s.position === 3 ? "third" : ""}">
            <td>${s.position}</td><td>${escape(s.name)}</td><td>${s.points}</td>
            <td>${s.goal_diff > 0 ? "+" : ""}${s.goal_diff}</td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>`;
}

function wireGroupInputs() {
  app.querySelectorAll<HTMLButtonElement>(".fx-save").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const row = btn.closest(".fx")!;
      const home = row.querySelector<HTMLInputElement>('input[data-side="home"]')!.value;
      const away = row.querySelector<HTMLInputElement>('input[data-side="away"]')!.value;
      if (home === "" || away === "") {
        btn.textContent = "marcador?";
        return;
      }
      btn.disabled = true;
      btn.textContent = "Guardando…";
      try {
        await api.setMatchResult(btn.dataset.fixture!, parseInt(home, 10), parseInt(away, 10));
        [realMatches, realState] = await Promise.all([api.matches(), api.realBracket()]);
        paintReal();
      } catch (e) {
        btn.textContent = "Error";
        btn.disabled = false;
      }
    })
  );

  const gbtn = app.querySelector<HTMLButtonElement>("#gsim");
  if (gbtn)
    gbtn.addEventListener("click", async () => {
      const sims = parseInt(app.querySelector<HTMLInputElement>("#gsims")!.value, 10);
      gbtn.disabled = true;
      gbtn.textContent = "Simulando…";
      try {
        const res = await api.simulateGroups(Number.isNaN(sims) ? null : sims, null);
        groupProj = new Map(res.groups.map((g) => [g.name, g.teams]));
        groupRoutes = new Map(res.groups.map((g) => [g.name, g.routes ?? {}]));
        thirdSlots = res.third_slots ?? {};
        groupProjSims = res.simulations;
        paintReal();
      } catch (e) {
        gbtn.textContent = "Error";
        gbtn.disabled = false;
      }
    });
}

// El cuadro real reusa la estética .bk-* del cuadro simulado, pero con ties
// editables (inputs de marcador) y huecos "pendientes" cuando faltan equipos.
function realColumns(res: RealBracketResponse): RealTie[][] {
  const ko = res.knockout;
  const byId = new Map<number, RealTie>();
  [...ko.round_of_32, ...ko.round_of_16, ...ko.quarter_finals, ...ko.semi_finals, ko.final].forEach((t) =>
    byId.set(t.tie_id, t)
  );
  const rounds: RealTie[][] = [[], [], [], [], []];
  const feederId = (label: string) => (label.startsWith("W") ? parseInt(label.slice(1), 10) : null);
  const walk = (tie: RealTie, depth: number) => {
    rounds[depth].push(tie);
    for (const lab of [tie.home.label, tie.away.label]) {
      const id = feederId(lab);
      if (id != null && byId.has(id)) walk(byId.get(id)!, depth + 1);
    }
  };
  walk(ko.final, 0);
  return [rounds[4], rounds[3], rounds[2], rounds[1], rounds[0]];
}

function realTieCard(t: RealTie): string {
  const slot = (s: RealSlot, won: boolean) => `
    <div class="bk-slot ${won ? "win" : ""} ${s.team_id ? "" : "empty"}">
      <span class="bk-lab">${escape(s.label)}</span>
      <span class="bk-nm">${s.name ? escape(s.name) : "&mdash;"}</span>
    </div>`;
  const homeWon = t.winner_id != null && t.winner_id === t.home.team_id;
  const awayWon = t.winner_id != null && t.winner_id === t.away.team_id;

  let foot = "";
  if (t.playable) {
    const loaded = t.home_goals != null;
    foot = `
      <div class="bk-edit" data-tie="${t.tie_id}">
        <input class="bk-in" type="number" min="0" data-side="home" value="${t.home_goals ?? ""}" />
        <span class="bk-colon">:</span>
        <input class="bk-in" type="number" min="0" data-side="away" value="${t.away_goals ?? ""}" />
        <select class="bk-pen" data-side="pen" title="Ganador por penales si hay empate">
          <option value="">pen</option>
          <option value="home" ${t.penalty_winner === "home" ? "selected" : ""}>&uarr;</option>
          <option value="away" ${t.penalty_winner === "away" ? "selected" : ""}>&darr;</option>
        </select>
        <button class="bk-go-mini" data-tie="${t.tie_id}">OK</button>
        ${loaded ? `<button class="bk-clear" data-tie="${t.tie_id}" title="Borrar resultado">&times;</button>` : ""}
      </div>`;
  } else {
    foot = `<div class="bk-pending">pendiente</div>`;
  }
  return `<div class="bk-tie ${t.playable ? "" : "bk-dim"}">${slot(t.home, homeWon)}${slot(t.away, awayWon)}${foot}</div>`;
}

function bracketSection(res: RealBracketResponse): string {
  const columns = realColumns(res)
    .map((ties) => {
      const stage = ties[0]?.stage ?? "";
      return `<div class="bk-col"><div class="bk-head">${STAGE_TITLES[stage] ?? stage}</div><div class="bk-col-body">${ties
        .map(realTieCard)
        .join("")}</div></div>`;
    })
    .join("");
  const champ = res.champion
    ? `<span class="bk-champ-name">${escape(res.champion.name)}</span>`
    : `<span class="bk-champ-pending">por definir</span>`;
  const note = res.groups_complete
    ? ""
    : `<p class="hint">Complet&aacute; los 12 grupos para que se asignen los mejores terceros y se habiliten todas las llaves.</p>`;
  return `
    <section class="panel">
      <div class="bk-champ"><span class="bk-champ-lab">Campe&oacute;n</span>${champ}</div>
      ${note}
      <div class="bk-board">${columns}</div>
    </section>`;
}

function wireBracketInputs() {
  app.querySelectorAll<HTMLButtonElement>(".bk-go-mini").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const wrap = btn.closest(".bk-edit")!;
      const h = wrap.querySelector<HTMLInputElement>('input[data-side="home"]')!.value;
      const a = wrap.querySelector<HTMLInputElement>('input[data-side="away"]')!.value;
      const pen = wrap.querySelector<HTMLSelectElement>('select[data-side="pen"]')!.value as "" | "home" | "away";
      if (h === "" || a === "") {
        btn.textContent = "?";
        return;
      }
      const hg = parseInt(h, 10);
      const ag = parseInt(a, 10);
      const penalty = hg === ag ? pen || null : null;
      if (hg === ag && !penalty) {
        btn.textContent = "pen?";
        return;
      }
      btn.disabled = true;
      try {
        realState = await api.setKnockoutResult(parseInt(btn.dataset.tie!, 10), hg, ag, penalty);
        paintReal();
      } catch (e) {
        btn.textContent = "Err";
        btn.disabled = false;
      }
    })
  );
  app.querySelectorAll<HTMLButtonElement>(".bk-clear").forEach((btn) =>
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try {
        realState = await api.clearKnockoutResult(parseInt(btn.dataset.tie!, 10));
        paintReal();
      } catch (e) {
        btn.disabled = false;
      }
    })
  );
}

// Pronóstico: Montecarlo condicionado a los resultados reales ya cargados.
function forecastSection(): string {
  const out = realForecast
    ? forecastTable(realForecast)
    : `<p class="empty">Puls&aacute; "Simular" para estimar el campe&oacute;n con los resultados actuales.</p>`;
  return `
    <section class="panel">
      <p class="hint">Simula el resto del torneo muchas veces tomando como <b>fijos</b> los resultados ya cargados (los partidos en vivo o sin jugar se simulan) y promedia qui&eacute;n sale campe&oacute;n.</p>
      <div class="controls">
        <div class="field">
          <label>Simulaciones</label>
          <input type="number" id="fsims" value="5000" min="500" max="50000" step="500" />
        </div>
        <button class="go" id="fsim">Simular</button>
      </div>
      <div id="forecast-out">${out}</div>
    </section>`;
}

function forecastTable(res: TournamentResponse): string {
  const top = res.teams.slice(0, 16);
  return `
    <table>
      <thead>
        <tr>
          <th class="rank">#</th><th class="team">Equipo</th><th>Campe&oacute;n</th>
          <th class="hide">Final</th><th class="hide">Semis</th><th class="hide">Clasifica</th>
        </tr>
      </thead>
      <tbody>
        ${top
          .map(
            (t, i) => `
          <tr>
            <td class="rank">${i + 1}</td>
            <td class="team">${escape(t.name)}</td>
            <td class="champ">${pct(t.win_tournament)}</td>
            <td class="hide">${pct(t.reach_final)}</td>
            <td class="hide">${pct(t.reach_semi_final)}</td>
            <td class="hide">${pct(t.qualify)}</td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>
    <p class="meta">${res.simulations.toLocaleString("es")} simulaciones &middot; ${res.elapsed_ms} ms &middot; resultados cargados fijados</p>`;
}

function wireForecast() {
  const btn = app.querySelector<HTMLButtonElement>("#fsim");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    const sims = parseInt(app.querySelector<HTMLInputElement>("#fsims")!.value, 10);
    const out = app.querySelector<HTMLDivElement>("#forecast-out")!;
    btn.disabled = true;
    out.innerHTML = `<p class="empty">Simulando ${sims.toLocaleString("es")} torneos&hellip;</p>`;
    try {
      realForecast = await api.runTournament(sims, null);
      out.innerHTML = forecastTable(realForecast);
    } catch (e) {
      out.innerHTML = `<p class="error">No se pudo simular: ${escape(String(e))}</p>`;
    } finally {
      btn.disabled = false;
    }
  });
}

// Proyección: un cuadro de 16avos -> final jugado una vez desde el estado real.
function projectionSection(): string {
  const board = realProjection
    ? renderCuadro(realProjection)
    : `<div class="panel"><p class="empty">Simulando el cuadro&hellip;</p></div>`;
  return `
    <section class="panel">
      <div class="real-top">
        <p class="hint" style="margin:0">El cuadro <b>m&aacute;s probable</b> de 16avos a la final partiendo de lo ya jugado: los clasificados m&aacute;s probables de cada grupo y, en cada llave, el favorito con su probabilidad de pasar.</p>
        <button class="go" id="reroll">&#8635; Recalcular</button>
      </div>
    </section>
    <div id="projection-board">${board}</div>`;
}

async function loadProjection() {
  const board = app.querySelector<HTMLDivElement>("#projection-board");
  if (!board) return;
  try {
    realProjection = await api.likelyBracket(5000);
    board.innerHTML = renderCuadro(realProjection);
  } catch (e) {
    board.innerHTML = `<div class="panel"><p class="error">No se pudo calcular: ${escape(String(e))}</p></div>`;
  }
}

function wireProjection() {
  const btn = app.querySelector<HTMLButtonElement>("#reroll");
  if (btn)
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      await loadProjection();
      btn.disabled = false;
    });
  if (!realProjection) loadProjection();
}

// --------------------------------------------------------------------------- //
// Arranque
// --------------------------------------------------------------------------- //
async function boot() {
  app.innerHTML = shell(`<div class="panel"><p class="empty">Cargando&hellip;</p></div>`);
  try {
    teams = await api.teams();
    teams.sort((a, b) => a.name.localeCompare(b.name));
    renderReal();
  } catch (e) {
    app.innerHTML = shell(
      `<div class="panel"><p class="error">No se pudo conectar con el backend: ${escape(String(e))}</p></div>`
    );
  }
}

boot();
