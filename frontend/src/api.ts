// Cliente tipado de la API de WillCarlo.

export interface Team {
  id: string;
  name: string;
}

export interface Outcome {
  home_win: number;
  draw: number;
  away_win: number;
}

export interface Prediction {
  predictor_name: string;
  predictor_priority: number;
  outcome: Outcome;
  top_pick: string;
  expected_home_goals: number | null;
  expected_away_goals: number | null;
  most_likely_score: [number, number] | null;
  explanation: string;
  drivers: string[];
  features_used: string[];
  features_missing: string[];
  sources: string[];
  degraded: boolean;
}

export interface LabResponse {
  home: Team;
  away: Team;
  ladder: Prediction[];
  final: Prediction;
}

export interface TournamentTeam {
  team_id: string;
  name: string;
  group: string;
  win_group: number;
  qualify: number;
  reach_round_of_16: number;
  reach_quarter_final: number;
  reach_semi_final: number;
  reach_final: number;
  win_tournament: number;
  expected_group_points: number;
}

export interface TournamentResponse {
  simulations: number;
  seed: number | null;
  elapsed_ms: number;
  teams: TournamentTeam[];
}

export interface BracketTeamSlot {
  team_id: string;
  name: string;
  label: string; // procedencia: 1A, 2B, 3C, W73...
}

export interface BracketTie {
  tie_id: number;
  stage: string;
  home: BracketTeamSlot;
  away: BracketTeamSlot;
  home_score: number | null;
  away_score: number | null;
  winner_id: string;
  winner_name: string;
  penalties: boolean;
  win_prob?: number; // presente en el cuadro "más probable": prob. de que el ganador pase
}

export interface BracketStanding {
  position: number;
  team_id: string;
  name: string;
  points: number;
  goals_for: number;
  goals_against: number;
  goal_diff: number;
}

export interface BracketResponse {
  seed?: number | null;
  simulations?: number;
  elapsed_ms: number;
  champion: { team_id: string; name: string };
  groups: { name: string; standings: BracketStanding[] }[];
  knockout: {
    round_of_32: BracketTie[];
    round_of_16: BracketTie[];
    quarter_finals: BracketTie[];
    semi_finals: BracketTie[];
    final: BracketTie;
  };
}

export interface MatchFixture {
  id: string;
  group: string;
  home: Team;
  away: Team;
  is_played: boolean;
  home_goals: number | null;
  away_goals: number | null;
  status: string | null; // "final" | "live" | null
}

export interface MatchPrediction {
  id: string;
  home_win: number;
  draw: number;
  away_win: number;
  expected_home_goals: number | null;
  expected_away_goals: number | null;
  most_likely_score: [number, number] | null;
}

export interface GroupProjTeam {
  team_id: string;
  name: string;
  p_pos: number[]; // prob. de terminar 1º, 2º, 3º, 4º
  exp_points: number;
  exp_position: number;
}

export interface GroupRoute {
  tie_id: number;
  opponent: string;
}

export interface ThirdSlot {
  by_group: { group: string; p: number }[];
  by_team: { team_id: string; name: string; p: number }[];
}

export interface GroupSimResponse {
  simulations: number;
  groups: { name: string; teams: GroupProjTeam[]; routes?: { first?: GroupRoute; second?: GroupRoute } }[];
  third_slots: Record<string, ThirdSlot>; // tie_id -> distribución del tercero
}

export interface RefreshSummary {
  updated: string[];
  live: string[];
  skipped: number;
  unmatched: string[];
}

export interface RealSlot {
  team_id: string | null;
  name: string | null;
  label: string; // 1A, 2B, 3C, W73...
}

export interface RealTie {
  tie_id: number;
  stage: string;
  home: RealSlot;
  away: RealSlot;
  playable: boolean;
  home_goals: number | null;
  away_goals: number | null;
  penalty_winner: "home" | "away" | null;
  winner_id: string | null;
  winner_name: string | null;
}

export interface RealGroup {
  name: string;
  complete: boolean;
  standings: BracketStanding[];
}

export interface RealBracketResponse {
  groups_complete: boolean;
  champion: { team_id: string; name: string } | null;
  groups: RealGroup[];
  knockout: {
    round_of_32: RealTie[];
    round_of_16: RealTie[];
    quarter_finals: RealTie[];
    semi_finals: RealTie[];
    final: RealTie;
  };
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  teams: () => fetch("/api/teams").then((r) => json<Team[]>(r)),

  lab: (homeId: string, awayId: string, neutralVenue = true) =>
    fetch("/api/lab", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ home_id: homeId, away_id: awayId, neutral_venue: neutralVenue }),
    }).then((r) => json<LabResponse>(r)),

  runTournament: (simulations: number | null, seed: number | null) =>
    fetch("/api/tournament/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ simulations, seed, save_snapshot: true }),
    }).then((r) => json<TournamentResponse>(r)),

  playBracket: (seed: number | null) =>
    fetch("/api/tournament/bracket", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ seed }),
    }).then((r) => json<BracketResponse>(r)),

  likelyBracket: (simulations: number | null) =>
    fetch("/api/tournament/bracket/likely", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ simulations }),
    }).then((r) => json<BracketResponse>(r)),

  matches: () => fetch("/api/matches").then((r) => json<MatchFixture[]>(r)),

  matchPredictions: () => fetch("/api/matches/predictions").then((r) => json<MatchPrediction[]>(r)),

  simulateGroups: (simulations: number | null, seed: number | null) =>
    fetch("/api/groups/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ simulations, seed }),
    }).then((r) => json<GroupSimResponse>(r)),

  refreshResults: () =>
    fetch("/api/results/refresh", { method: "POST" }).then((r) => json<RefreshSummary>(r)),

  setMatchResult: (fixtureId: string, homeGoals: number, awayGoals: number) =>
    fetch(`/api/matches/${encodeURIComponent(fixtureId)}/result`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ home_goals: homeGoals, away_goals: awayGoals }),
    }).then((r) => json<unknown>(r)),

  realBracket: () => fetch("/api/bracket/real").then((r) => json<RealBracketResponse>(r)),

  setKnockoutResult: (
    tieId: number,
    homeGoals: number,
    awayGoals: number,
    penaltyWinner: "home" | "away" | null
  ) =>
    fetch(`/api/knockout/${tieId}/result`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ home_goals: homeGoals, away_goals: awayGoals, penalty_winner: penaltyWinner }),
    }).then((r) => json<RealBracketResponse>(r)),

  clearKnockoutResult: (tieId: number) =>
    fetch(`/api/knockout/${tieId}/result`, { method: "DELETE" }).then((r) => json<RealBracketResponse>(r)),
};
