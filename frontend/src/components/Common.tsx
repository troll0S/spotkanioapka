import type { ConnectionState, PersonView, Role } from "../lib/types";

const ROLE_LABEL: Record<Role, string> = {
  HOST: "host",
  ADMIN: "admin",
  GUEST: "gość",
};

export function ConnectionBadge({ state }: { state: ConnectionState }) {
  const label = {
    connecting: "łączę…",
    open: "połączono",
    reconnecting: "wznawiam połączenie…",
    closed: "rozłączono",
  }[state];

  const tone = state === "open" ? "ok" : state === "closed" ? "bad" : "wait";

  return (
    <span className="badge" title={label}>
      <span className={`dot ${tone}`} />
      {label}
    </span>
  );
}

export function RoleChip({ role }: { role: Role }) {
  return <span className={`chip chip-${role.toLowerCase()}`}>{ROLE_LABEL[role]}</span>;
}

export function PeopleList({
  people,
  emptyText = "Jeszcze nikogo tu nie ma.",
}: {
  people: PersonView[];
  emptyText?: string;
}) {
  if (people.length === 0) return <p className="muted">{emptyText}</p>;

  return (
    <ul className="people">
      {people.map((person) => (
        <li key={person.id}>
          <span className={`dot ${person.connected ? "ok" : "off"}`} />
          <span className="person-name">{person.displayName}</span>
          {person.role && person.role !== "GUEST" && <RoleChip role={person.role} />}
          {person.role && person.isVoting === false && person.role === "GUEST" && (
            <span className="chip">bez głosu</span>
          )}
        </li>
      ))}
    </ul>
  );
}

export function Stage({ label, hint }: { label: string; hint?: string }) {
  return (
    <div className="stage">
      <div className="stage-label">{label}</div>
      {hint && <p className="muted">{hint}</p>}
    </div>
  );
}

/**
 * Ekran zastępczy dla etapów, które dochodzą w kolejnych kamieniach.
 * Lepiej powiedzieć wprost „tego jeszcze nie ma" niż pokazać pustą stronę.
 */
export function NotYet({ stage, milestone }: { stage: string; milestone: string }) {
  return (
    <div className="stage">
      <div className="stage-label">{stage}</div>
      <p className="muted">Ten etap powstaje w kamieniu {milestone}.</p>
    </div>
  );
}
