export type SessionStatus =
  | "LOBBY"
  | "COLLECTING"
  | "SWIPING"
  | "SCHEDULING"
  | "AVAILABILITY"
  | "ASSIGNMENT"
  | "CALENDAR"
  | "CLOSED";

export type Role = "HOST" | "ADMIN" | "GUEST";

export type PersonView = {
  id: number;
  displayName: string;
  connected: boolean;
  /** Tylko w snapshocie hosta i admina. */
  role?: Role;
  isVoting?: boolean;
};

export type IdeaView = {
  id: number;
  title: string;
  description: string | null;
  /** Wpis admina, którego nie da się odrzucić — pomija etap 2. */
  isSpecial: boolean;
  authorId: number;
  authorName: string;
  createdAt: string;
};

export type SwipeCard = {
  id: number;
  title: string;
  description: string | null;
};

export type BoardEntry = SwipeCard & {
  right: number;
  left: number;
  voted: number;
  /** null = host jeszcze nie rozstrzygnął. */
  decision: boolean | null;
};

export type SwipingState = {
  poolSize: number;
  votersExpected: number;
  /** Karty, które zostały temu uczestnikowi. Host dostaje pustą listę. */
  cards: SwipeCard[];
  yourDone: number;
  yourTotal: number;
  youAreDone: boolean;
  /** Tylko dla hosta, admina i widza — uczestnik nie widzi liczników. */
  board?: BoardEntry[];
  decided?: number;
  accepted?: number;
};

export type ScheduleKind = "EXACT_DATE" | "WEEK" | "RANGE" | "MONTH";

export type ScheduleView = {
  kind: ScheduleKind;
  /** Cztery rodzaje terminu, zawsze ten sam kształt: przedział dat. */
  dateFrom: string;
  dateTo: string;
  /** Gotowy opis po polsku — buduje go serwer, żeby wszędzie brzmiał tak samo. */
  label: string;
  isPast: boolean;
};

export type AgendaItem = {
  ideaId: number;
  title: string;
  description: string | null;
  isSpecial: boolean;
  schedule: ScheduleView | null;
};

export type SchedulingState = {
  total: number;
  scheduled: number;
  missing: number;
  /** Tylko dla hosta i widza — uczestnik dostaje sam postęp. */
  items?: AgendaItem[];
};

export type AnswerValue = "WANT" | "CAN" | "DONT_WANT" | "ABSOLUTELY_NOT";

export type EventView = {
  ideaId: number;
  title: string;
  description: string | null;
  isSpecial: boolean;
  schedule: ScheduleView | null;
};

export type AvailabilityState = {
  total: number;
  index: number;
  remaining: number;
  allPresented: boolean;
  expected: number;
  current: EventView | null;
  options: { value: AnswerValue; label: string }[];
  yourAnswer: AnswerValue | null;
  canAnswer: boolean;
  /** Tylko dla hosta i widza — uczestnik nie widzi rozkładu w trakcie rundy. */
  tally?: Record<AnswerValue, number>;
  answered?: number;
};

/** Poziom ostrzeżenia dla wydarzenia — sygnał dla człowieka, nie automat. */
export type EventLevel = "ok" | "warn" | "blocked" | "empty";

export type CalendarDay = {
  date: string;
  day: number;
  inMonth: boolean;
  isToday: boolean;
  isWeekend: boolean;
};

/** Kawałek wydarzenia przypadający na jeden tydzień siatki. */
export type CalendarBand = {
  ideaId: number;
  title: string;
  startCol: number;
  span: number;
  lane: number;
  continuesLeft: boolean;
  continuesRight: boolean;
  isSpecial: boolean;
  level: EventLevel;
  colorIndex: number;
};

export type CalendarMonth = {
  year: number;
  month: number;
  label: string;
  weeks: { days: CalendarDay[]; bands: CalendarBand[]; lanes: number }[];
};

export type CalendarEvent = {
  ideaId: number;
  title: string;
  description: string | null;
  isSpecial: boolean;
  schedule: ScheduleView | null;
  tally: Record<AnswerValue, number>;
  people: Record<AnswerValue, string[]>;
  answered: number;
  attending: number;
  level: EventLevel;
  assigned: AssignedPerson[];
};

export type CalendarState = {
  months: CalendarMonth[];
  events: CalendarEvent[];
  conflicts: {
    a: { ideaId: number; title: string };
    b: { ideaId: number; title: string };
    label: string;
  }[];
  weekdays: string[];
  answerLabels: Record<AnswerValue, string>;
  truncated: boolean;
};

export type AssignedPerson = {
  id: number;
  name: string;
  /** false = osoba spoza sesji, wpisana ręcznie. */
  isParticipant: boolean;
};

export type ReviewEvent = {
  ideaId: number;
  title: string;
  description: string | null;
  isSpecial: boolean;
  schedule: ScheduleView | null;
  tally: Record<AnswerValue, number>;
  people: Record<AnswerValue, string[]>;
  answered: number;
  assigned: AssignedPerson[];
  /** null = host jeszcze nie rozstrzygnął. */
  decision: boolean | null;
};

export type AssignmentState = {
  total: number;
  index: number;
  decided: number;
  confirmed: number;
  remaining: number;
  isLast: boolean;
  current: ReviewEvent | null;
  roster: { id: number; displayName: string }[];
  answerLabels: Record<AnswerValue, string>;
  canEdit: boolean;
  maxPeople: number;
};

export type ExportsState = {
  /** Wspólny przedrostek adresów pobierania. */
  base: string;
  /** Ile pomysłów odpadło — odrzuconych na dowolnym etapie. */
  rejectedCount: number;
};

export type AdminUserRow = {
  login: string;
  isSuperadmin: boolean;
  isActive: boolean;
  createdAt: string;
  lastLoginAt: string | null;
};

export type ArchiveEntry = {
  code: string;
  name: string;
  status: SessionStatus;
  statusLabel: string;
  isActive: boolean;
  createdAt: string;
  closedAt: string | null;
  /** Login konta, które założyło sesję. */
  createdBy: string | null;
  participants: number;
  ideas: number;
};

export type ArchiveDetail = {
  code: string;
  name: string;
  statusLabel: string;
  isActive: boolean;
  createdAt: string;
  closedAt: string | null;
  createdBy: string | null;
  participants: { displayName: string; role: Role; isVoting: boolean; joinedAt: string }[];
  ideas: {
    id: number;
    title: string;
    description: string | null;
    isSpecial: boolean;
    /** null, gdy autor został usunięty z sesji — treść zostaje. */
    author: string | null;
    swipeDecision: boolean | null;
    planDecision: boolean | null;
    schedule: string | null;
    assigned: string[];
  }[];
  rejected: { title: string; reason: string }[];
  canExport: boolean;
  exportBase: string;
};

export type AdminAnswerRow = {
  participantId: number;
  displayName: string;
  answer: AnswerValue | null;
  wasEdited: boolean;
  originalAnswer: AnswerValue | null;
};

export type AdminState = {
  /** Wydarzenie, którego odpowiedzi da się teraz poprawić. */
  currentIdeaId: number | null;
  answers: AdminAnswerRow[];
  options: { value: AnswerValue; label: string }[];
  canDeleteIdeas: boolean;
};

export type Snapshot = {
  session: {
    code: string;
    name: string;
    status: SessionStatus;
    statusLabel: string;
    isActive: boolean;
    createdAt: string;
    closedAt: string | null;
  };
  counts: {
    /** Mianownik liczników postępu — wyłącznie głosujący goście. */
    voting: number;
    votingConnected: number;
    connected: number;
    total: number;
    /** Podglądający — nie są uczestnikami i nie liczą się do niczego innego. */
    spectators: number;
  };
  you: {
    id: number;
    displayName: string;
    role: Role;
    isVoting: boolean;
    ideaCount: number;
    canAddIdeas: boolean;
    canAddSpecial: boolean;
  } | null;
  participants: PersonView[];
  ideas: IdeaView[];
  ideaCounts: {
    total: number;
    special: number;
  };
  /** Obecne tylko na etapie 2. */
  swiping?: SwipingState;
  /** Obecne tylko na etapie 3. */
  scheduling?: SchedulingState;
  /** Obecne tylko na etapie 4. */
  availability?: AvailabilityState;
  /** Obecne tylko na etapie 5. */
  assignment?: AssignmentState;
  /** Obecne na etapie 6 i po zamknięciu sesji. */
  exports?: ExportsState;
  /** Wyłącznie dla roli ADMIN. */
  admin?: AdminState;
  /** Obecne tylko na etapie 5. */
  calendar?: CalendarState;
  /** Limity walidacji — płyną z serwera, żeby nie trzymać drugiej kopii. */
  limits: {
    maxTitle: number;
    maxDescription: number;
    maxPerParticipant: number;
  };
  /** Obecne wyłącznie w snapshocie hosta. */
  host?: {
    canAdvance: boolean;
    nextStatus: SessionStatus | null;
    nextLabel: string | null;
    joinUrl: string | null;
    joinUrlSuspicious: boolean;
    qrUrl: string;
  };
};

export type Identity = {
  code: string;
  token: string;
  participant_id: number;
  display_name: string;
  role: Role;
  is_voting: boolean;
};

export type ConnectionState = "connecting" | "open" | "reconnecting" | "closed";
